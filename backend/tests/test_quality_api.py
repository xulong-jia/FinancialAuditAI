from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_bad_case(status: str = "open") -> dict:
    response = client.post(
        "/api/v1/bad-cases",
        json={
            "case_type": "rule",
            "title": f"{status} rule sample",
            "input_payload": {"sample_id": status},
            "model_output": {"status": "pass"},
            "expected_output": {"status": "need_review"},
            "status": status,
            "severity": "high",
            "owner_name": "qa_owner",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def run_eval(eval_type: str) -> dict:
    response = client.post(
        "/api/v1/evaluations/run",
        json={
            "eval_type": eval_type,
            "dataset_name": "phase14_test_synthetic",
            "created_by": "qa_test",
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_bad_case_crud_and_filters() -> None:
    created = create_bad_case()

    listed = client.get("/api/v1/bad-cases?case_type=rule&status=open")
    assert listed.status_code == 200
    assert [case["id"] for case in listed.json()] == [created["id"]]

    detail = client.get(f"/api/v1/bad-cases/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["expected_output"]["status"] == "need_review"

    updated = client.patch(
        f"/api/v1/bad-cases/{created['id']}",
        json={"status": "fixed", "root_cause": "missing fixture", "fix_plan": "add regression sample"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "fixed"
    assert updated.json()["root_cause"] == "missing fixture"


def test_rule_evaluation_records_metrics_and_converts_failed_cases() -> None:
    result = run_eval("rule")

    assert result["eval_type"] == "rule"
    assert result["sample_count"] == 3
    assert result["metrics"]["rule_accuracy"] < 1.0
    assert result["metrics"]["false_negative_count"] == 1
    assert result["failed_cases"]

    cases = client.get("/api/v1/bad-cases?case_type=rule")
    assert cases.status_code == 200
    assert len(cases.json()) == len(result["failed_cases"])

    detail = client.get(f"/api/v1/evaluations/results/{result['id']}")
    assert detail.status_code == 200
    assert detail.json()["metrics"]["limitations"][0] == "Synthetic smoke dataset only."


def test_extraction_evaluation_compares_expected_json() -> None:
    result = run_eval("extraction")

    assert result["metrics"]["expected_json_match_rate"] == 0.5
    assert result["failed_cases"][0]["expected_output"]["value_normalized"]["value"] == "2026-01-11"


def test_rag_no_answer_evaluation_is_deterministic() -> None:
    result = run_eval("rag")

    assert result["metrics"]["no_answer_accuracy"] == 1.0
    assert result["metrics"]["citation_accuracy"] == 1.0
    assert result["failed_cases"] == []


def test_agent_state_validity_evaluation() -> None:
    result = run_eval("agent")

    assert result["metrics"]["state_transition_validity"] == 1.0
    assert result["metrics"]["rule_engine_required"] == 1.0
    assert result["metrics"]["high_risk_auto_confirm_rate"] == 0.0


def test_regression_evaluation_uses_open_and_fixed_bad_cases() -> None:
    open_case = create_bad_case("open")
    fixed_case = create_bad_case("fixed")

    result = run_eval("regression")

    assert result["sample_count"] == 2
    assert result["metrics"]["regression_pass_count"] == 1
    assert result["metrics"]["regression_fail_count"] == 1
    assert result["failed_cases"][0]["model_output"]["bad_case_id"] == open_case["id"]
    assert fixed_case["id"] not in str(result["failed_cases"])


def test_evaluation_results_list_filter() -> None:
    run_eval("classification")
    run_eval("ocr")

    response = client.get("/api/v1/evaluations/results?eval_type=classification")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["eval_type"] == "classification"
