import json
import shutil
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.document import Document
from app.services import evaluation_service
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


def auth_headers(email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(email: str, role_codes: list[str]) -> dict:
    response = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": "test-password",
            "full_name": email.split("@")[0],
            "role_codes": role_codes,
        },
    )
    assert response.status_code == 200
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
    client.patch(
        f"/api/v1/bad-cases/{fixed_case['id']}",
        json={"validation_result": {"regression_passed": True}},
    )
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


def test_dataset_driven_evaluation_is_task_scoped_and_creates_scoped_bad_cases() -> None:
    owner = create_user("eval-owner@example.com", ["analyst"])
    create_user("eval-other@example.com", ["analyst"])
    owner_headers = auth_headers("eval-owner@example.com", "test-password")
    other_headers = auth_headers("eval-other@example.com", "test-password")
    task = client.post(
        "/api/v1/tasks",
        json={"name": "Scoped evaluation task", "scenario": "procurement"},
        headers=owner_headers,
    ).json()
    assert task["owner_id"] == owner["id"]
    dataset_path = evaluation_service.evaluation_datasets_root() / "strict_eval_dataset.json"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text(
        json.dumps(
            {
                "dataset_name": "strict_eval_dataset",
                "dataset_kind": "desensitized_annotated",
                "samples": [
                    {
                        "id": "cls-pass",
                        "eval_type": "classification",
                        "actual": {"doc_type": "invoice", "confidence": 0.93},
                        "expected": {"doc_type": "invoice"},
                    },
                    {
                        "id": "cls-fail",
                        "eval_type": "classification",
                        "actual": {"doc_type": "purchase_contract", "confidence": 0.91},
                        "expected": {"doc_type": "invoice"},
                        "severity": "high",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result_response = client.post(
        "/api/v1/evaluations/run",
        json={
            "task_id": task["id"],
            "eval_type": "classification",
            "dataset_name": "strict_eval_dataset",
            "dataset_path": "strict_eval_dataset.json",
            "created_by": "qa_test",
        },
    )

    assert result_response.status_code == 200, result_response.text
    result = result_response.json()
    assert result["task_id"] == task["id"]
    assert result["sample_count"] == 2
    assert result["metrics"]["is_dataset_driven"] is True
    assert result["metrics"]["dataset_kind"] == "desensitized_annotated"
    assert result["metrics"]["accuracy"] == 0.5
    assert result["failed_cases"][0]["title"] == "cls-fail"
    assert result["metrics"]["is_production_evaluation"] is False

    owner_results = client.get("/api/v1/evaluations/results", headers=owner_headers)
    other_results = client.get("/api/v1/evaluations/results", headers=other_headers)
    assert result["id"] in {item["id"] for item in owner_results.json()}
    assert result["id"] not in {item["id"] for item in other_results.json()}
    assert client.get(f"/api/v1/evaluations/results/{result['id']}", headers=other_headers).status_code == 403

    owner_cases = client.get("/api/v1/bad-cases?case_type=classification", headers=owner_headers).json()
    other_cases = client.get("/api/v1/bad-cases?case_type=classification", headers=other_headers).json()
    assert any(case["title"] == "cls-fail" and case["task_id"] == task["id"] for case in owner_cases)
    assert all(case["title"] != "cls-fail" for case in other_cases)


def test_manual_acceptance_ocr_manifest_runs_expected_assertions(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_unit"
    sample_path = Path(__file__).resolve().parents[2] / "local_storage" / "manual_acceptance_files" / "ocr" / "unit_receipt.jpg"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    sample_path.parent.mkdir(parents=True, exist_ok=True)
    sample_path.write_bytes(b"unit-test-image")
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_unit",
                "source_type": "public",
                "is_production_evaluation": False,
                "files": {"ocr": "ocr.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "ocr.json").write_text(
        json.dumps(
            {
                "eval_type": "ocr",
                "source_type": "public",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "ocr-unit",
                        "file_path": str(sample_path.relative_to(Path(__file__).resolve().parents[2])),
                        "file_type": "image/jpeg",
                        "provider": "azure-document-intelligence",
                        "model": "prebuilt-layout",
                        "expected": {
                            "min_page_count": 1,
                            "must_contain_text": ["GREEN FIELD", "TOTAL", "$56.58"],
                            "min_ocr_blocks": 2,
                            "require_bbox": True,
                            "require_confidence": True,
                            "min_blocks_with_bbox": 2,
                            "min_blocks_with_confidence": 2,
                            "require_table_blocks": True,
                            "min_table_blocks": 1,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fake_run_ocr(db, document_id):
        document = db.get(Document, document_id)
        document.ocr_status = "completed"
        document.page_count = 1
        db.commit()
        db.refresh(document)
        return document

    def fake_list_pages(db, document_id):
        return [
            SimpleNamespace(
                raw_text="GREEN FIELD receipt TOTAL $56.58",
                ocr_blocks=[
                    {"text": "GREEN FIELD", "bbox": [1, 1, 2, 2], "confidence": 0.98},
                    {"text": "TOTAL $56.58", "bbox": [1, 3, 2, 4], "confidence": 0.97},
                ],
                table_blocks=[{"type": "azure_table"}],
                ocr_engine="azure-document-intelligence:prebuilt-layout",
            )
        ]

    monkeypatch.setattr(settings, "ocr_provider", "azure-document-intelligence")
    monkeypatch.setattr(settings, "ocr_api_url", "https://azure.example.test")
    monkeypatch.setattr(settings, "ocr_api_key", "unit-test-placeholder-key")
    monkeypatch.setattr(settings, "ocr_model", "prebuilt-layout")
    monkeypatch.setattr(evaluation_service.ocr_service, "run_ocr", fake_run_ocr)
    monkeypatch.setattr(evaluation_service.ocr_service, "list_pages", fake_list_pages)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "ocr",
                "dataset_name": "manual_acceptance_unit",
                "dataset_path": "evals/datasets/manual_acceptance_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["dataset_name"] == "manual_acceptance_unit"
        assert result["sample_count"] == 1
        assert result["failed_cases"] == []
        assert result["metrics"]["ocr_sample_pass_rate"] == 1.0
        assert result["metrics"]["source_type"] == "public"
        assert result["metrics"]["manual_acceptance_status"] == "non_production_manual_acceptance"
        assert result["metrics"]["is_production_evaluation"] is False
        assert result["metrics"]["blocked_external_dependency_count"] == 0
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)
        sample_path.unlink(missing_ok=True)


def test_manual_acceptance_classification_manifest_runs_text_samples() -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_classification_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_classification_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"classification": "classification.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "classification.json").write_text(
        json.dumps(
            {
                "samples": [
                    {
                        "sample_id": "classification-pass",
                        "input": {
                            "filename": "invoice_sample.pdf",
                            "text": "Invoice\nInvoice Number: INV-001\nIssue Date: 2026-07-02\nSeller: Demo Supplier\nTax Amount: CNY 100.00",
                        },
                        "expected": {"doc_type": "invoice"},
                    },
                    {
                        "sample_id": "classification-fail",
                        "title": "classification-fail",
                        "input": {
                            "filename": "invoice_sample_2.pdf",
                            "text": "Invoice\nInvoice Number: INV-002\nBuyer: Demo Company\nSeller: Demo Supplier\nTax Amount: CNY 20.00",
                        },
                        "expected": {"doc_type": "payment_receipt"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "classification",
                "dataset_name": "manual_acceptance_classification_unit",
                "dataset_path": "evals/datasets/manual_acceptance_classification_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["dataset_name"] == "manual_acceptance_classification_unit"
        assert result["sample_count"] == 2
        assert result["metrics"]["accuracy"] == 0.5
        assert result["metrics"]["source_type"] == "synthetic"
        assert result["metrics"]["dataset_kind"] == "non_production_manual_acceptance"
        assert result["metrics"]["is_dataset_driven"] is True
        assert result["metrics"]["is_production_evaluation"] is False
        assert len(result["failed_cases"]) == 1
        assert result["failed_cases"][0]["title"] == "classification-fail"
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_manual_acceptance_extraction_manifest_runs_text_samples(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_extraction_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_extraction_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"extraction": "extraction.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "extraction.json").write_text(
        json.dumps(
            {
                "eval_type": "extraction",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "extraction-invoice",
                        "doc_type": "invoice",
                        "input": {
                            "filename": "invoice_sample.pdf",
                            "text": (
                                "Invoice\n"
                                "Invoice No: INV-2026-001\n"
                                "Invoice Date: 2026/07/04\n"
                                "Seller Name: Demo Supplier Pty Ltd\n"
                                "Buyer Name: Demo Company\n"
                                "Item: Audit Service; Quantity: 2; Unit: pcs; Unit Price: 500.00; Amount: 1000.00\n"
                                "Amount Excluding Tax: 1,000.00\n"
                                "Tax Amount: 100.00\n"
                                "Amount Including Tax: CNY 1,100.00"
                            ),
                        },
                        "expected": {
                            "fields": {
                                "invoice_no": {"value": "INV-2026-001"},
                                "invoice_date": {"value_normalized": {"value": "2026-07-04"}},
                                "seller_name": {"value": "Demo Supplier Pty Ltd"},
                                "buyer_name": {"value": "Demo Company"},
                                "amount_excluding_tax": {"value_normalized": {"amount": 1000.0, "currency": "CNY"}},
                                "tax_amount": {"value_normalized": {"amount": 100.0, "currency": "CNY"}},
                                "amount_including_tax": {"value_normalized": {"amount": 1100.0, "currency": "CNY"}},
                                "item_lines": {
                                    "min_items": 1,
                                    "items": [
                                        {
                                            "item_name": "Audit Service",
                                            "quantity": 2.0,
                                            "unit": "pcs",
                                            "unit_price": 500.0,
                                            "amount": 1000.0,
                                        }
                                    ],
                                },
                            },
                            "require_source_page": True,
                            "require_source_text": True,
                            "require_source_bbox": False,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_if_llm_called():
        raise AssertionError("Extraction dataset runner must not call a real LLM provider")

    monkeypatch.setattr(evaluation_service.extraction_service.llm_provider, "get_llm_provider", fail_if_llm_called)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "extraction",
                "dataset_name": "manual_acceptance_extraction_unit",
                "dataset_path": "evals/datasets/manual_acceptance_extraction_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["dataset_name"] == "manual_acceptance_extraction_unit"
        assert result["sample_count"] == 1
        assert result["failed_cases"] == []
        assert result["metrics"]["extraction_field_accuracy"] == 1.0
        assert result["metrics"]["normalized_value_accuracy"] == 1.0
        assert result["metrics"]["item_line_accuracy"] == 1.0
        assert result["metrics"]["source_page_coverage"] == 1.0
        assert result["metrics"]["source_text_coverage"] == 1.0
        assert result["metrics"]["source_bbox_coverage"] == 0.0
        assert result["metrics"]["source_type"] == "synthetic"
        assert result["metrics"]["dataset_kind"] == "non_production_manual_acceptance"
        assert result["metrics"]["is_dataset_driven"] is True
        assert result["metrics"]["is_production_evaluation"] is False
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_manual_acceptance_ocr_file_path_is_restricted(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_path_guard"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps({"dataset_name": "manual_acceptance_path_guard", "files": {"ocr": "ocr.json"}}),
        encoding="utf-8",
    )
    (dataset_dir / "ocr.json").write_text(
        json.dumps(
            {
                "eval_type": "ocr",
                "samples": [
                    {
                        "sample_id": "blocked-path",
                        "file_path": "/etc/passwd",
                        "provider": "azure-document-intelligence",
                        "model": "prebuilt-layout",
                        "expected": {"must_contain_text": ["never"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_if_called(db, document_id):
        raise AssertionError("OCR service should not be called for blocked paths")

    monkeypatch.setattr(evaluation_service.ocr_service, "run_ocr", fail_if_called)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "ocr",
                "dataset_name": "manual_acceptance_path_guard",
                "dataset_path": "manual_acceptance_path_guard/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["sample_count"] == 1
        assert result["metrics"]["blocked_external_dependency_count"] == 1
        assert result["failed_cases"][0]["model_output"]["status"] == "blocked_external_dependency"
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_evaluation_dataset_path_is_restricted() -> None:
    for dataset_path in ("../evals/datasets/manual_acceptance/dataset_manifest.json", "/etc/passwd"):
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "classification",
                "dataset_name": "blocked",
                "dataset_path": dataset_path,
            },
        )

        assert response.status_code == 400
        assert "dataset_path" in response.json()["detail"]


def test_missing_project_root_dataset_path_has_clear_error() -> None:
    response = client.post(
        "/api/v1/evaluations/run",
        json={
            "eval_type": "classification",
            "dataset_name": "missing",
            "dataset_path": "evals/datasets/manual_acceptance/missing.json",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Evaluation dataset_path must point to an existing JSON file"


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
