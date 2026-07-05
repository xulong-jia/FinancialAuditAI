from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_bad_case(status: str = "open", *, in_regression: bool = False) -> dict:
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
            "in_regression": in_regression,
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
        json={
            "status": "fixed",
            "root_cause": "missing fixture",
            "fix_plan": "add regression sample",
            "in_regression": True,
            "validation_result": {"regression_passed": True},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "fixed"
    assert updated.json()["root_cause"] == "missing fixture"
    assert updated.json()["in_regression"] is True
    assert updated.json()["validation_result"]["regression_passed"] is True
    assert updated.json()["validated_at"]


def test_bad_case_type_contract_covers_required_types() -> None:
    required_types = ["ocr", "classification", "extraction", "rule", "rag", "agent", "review_dispute"]

    for case_type in required_types:
        response = client.post(
            "/api/v1/bad-cases",
            json={
                "case_type": case_type,
                "title": f"{case_type} bad case",
                "input_payload": {"sample": case_type},
                "model_output": {"actual": "bad"},
                "expected_output": {"expected": "good"},
                "root_cause": "pending",
                "fix_plan": "pending",
                "severity": "medium",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["case_type"] == case_type


def test_rule_evaluation_records_metrics_and_converts_failed_cases() -> None:
    result = run_eval("rule")

    assert result["eval_type"] == "rule"
    assert result["sample_count"] == 3
    assert result["metrics"]["rule_accuracy"] < 1.0
    assert result["metrics"]["false_negative_count"] == 1
    assert result["metrics"]["false_negative_rate"] > 0
    assert result["metrics"]["rule_coverage"] == 1.0
    assert result["metrics"]["explainability_rate"] == 1.0
    assert result["metrics"]["dataset_kind"] == "project_regression_sample"
    assert result["failed_cases"]

    cases = client.get("/api/v1/bad-cases?case_type=rule")
    assert cases.status_code == 200
    assert len(cases.json()) == len(result["failed_cases"])

    detail = client.get(f"/api/v1/evaluations/results/{result['id']}")
    assert detail.status_code == 200
    assert detail.json()["metrics"]["limitations"][0].startswith("Dataset kind is project_regression_sample")


def test_extraction_evaluation_compares_expected_json() -> None:
    result = run_eval("extraction")

    assert result["metrics"]["precision"] == 1.0
    assert result["metrics"]["recall"] == 1.0
    assert result["metrics"]["f1"] == 1.0
    assert result["metrics"]["expected_json_match_rate"] == 1.0
    assert result["metrics"]["dataset_kind"] == "project_sample_set"
    assert result["failed_cases"] == []


def test_rag_no_answer_evaluation_is_deterministic() -> None:
    result = run_eval("rag")

    assert result["metrics"]["no_answer_accuracy"] == 1.0
    assert result["metrics"]["citation_accuracy"] == 1.0
    assert result["metrics"]["groundedness"] == 1.0
    assert result["failed_cases"] == []


def test_agent_state_validity_evaluation() -> None:
    result = run_eval("agent")

    assert result["metrics"]["state_transition_validity"] == 1.0
    assert result["metrics"]["human_review_routing_accuracy"] == 1.0
    assert result["metrics"]["retry_recovery_rate"] == 1.0
    assert result["metrics"]["rule_engine_required"] == 1.0
    assert result["metrics"]["high_risk_auto_confirm_rate"] == 0.0


def test_regression_evaluation_uses_open_and_fixed_bad_cases() -> None:
    open_case = create_bad_case("open", in_regression=True)
    fixed_case = create_bad_case("fixed", in_regression=True)
    create_bad_case("open", in_regression=False)

    result = run_eval("regression")

    assert result["sample_count"] == 2
    assert result["metrics"]["regression_pass_count"] == 1
    assert result["metrics"]["regression_fail_count"] == 1
    assert result["metrics"]["reopened_case_count"] == 0
    assert result["metrics"]["fix_impact"]["fixed_cases"] == 1
    assert result["failed_cases"][0]["model_output"]["bad_case_id"] == open_case["id"]
    assert fixed_case["id"] not in str(result["failed_cases"])


def test_evaluation_results_list_filter() -> None:
    run_eval("classification")
    run_eval("ocr")

    response = client.get("/api/v1/evaluations/results?eval_type=classification")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["eval_type"] == "classification"


def test_evaluation_metrics_cover_required_metric_families() -> None:
    expected_keys = {
        "classification": {"accuracy", "macro_f1", "low_confidence_rate"},
        "ocr": {"cer", "wer", "table_structure_accuracy", "numeric_accuracy", "bbox_quality"},
        "rag": {"recall_at_k", "citation_accuracy", "groundedness", "no_answer_accuracy"},
        "end_to_end": {
            "e2e_success_rate",
            "control_table_accuracy",
            "exception_detection_f1",
            "evidence_completeness",
            "review_resolution_rate",
        },
    }
    for eval_type, keys in expected_keys.items():
        result = run_eval(eval_type)
        assert keys.issubset(result["metrics"])
        assert result["metrics"]["is_production_evaluation"] is False
