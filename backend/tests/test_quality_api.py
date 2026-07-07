import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import fitz
from fastapi.testclient import TestClient

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.audit_result import AuditResult
from app.models.audit_task import AuditTask
from app.models.control_table_row import ControlTableRow
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.document_relation import DocumentRelation
from app.models.extracted_field import ExtractedField
from app.models.report import Report
from app.services import evaluation_service
from app.main import app

client = TestClient(app)


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


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


def test_manual_acceptance_rule_manifest_runs_amount_samples() -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_rule_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_rule_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"rule": "rule.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "rule.json").write_text(
        json.dumps(
            {
                "eval_type": "rule",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "rule-pass",
                        "rule_id": "PROC_AMOUNT_001",
                        "scenario": "procurement",
                        "input": {
                            "fields": {
                                "purchase_contract": {"amount_including_tax": {"amount": 1100.0, "currency": "CNY"}},
                                "invoice": {"amount_including_tax": {"amount": 1100.0, "currency": "CNY"}},
                                "payment_receipt": {"payment_amount": {"amount": 1100.0, "currency": "CNY"}},
                            }
                        },
                        "expected": {"rule_id": "PROC_AMOUNT_001", "status": "pass", "severity": "low"},
                    },
                    {
                        "sample_id": "rule-fail",
                        "rule_id": "PROC_AMOUNT_001",
                        "scenario": "procurement",
                        "input": {
                            "fields": {
                                "purchase_contract": {"amount_including_tax": {"amount": 1100.0, "currency": "CNY"}},
                                "invoice": {"amount_including_tax": {"amount": 1250.0, "currency": "CNY"}},
                                "payment_receipt": {"payment_amount": {"amount": 1250.0, "currency": "CNY"}},
                            }
                        },
                        "expected": {
                            "rule_id": "PROC_AMOUNT_001",
                            "status": "fail",
                            "severity": "high",
                            "must_include_evidence": True,
                        },
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
                "eval_type": "rule",
                "dataset_name": "manual_acceptance_rule_unit",
                "dataset_path": "evals/datasets/manual_acceptance_rule_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["dataset_name"] == "manual_acceptance_rule_unit"
        assert result["sample_count"] == 2
        assert result["failed_cases"] == []
        assert result["metrics"]["rule_sample_pass_rate"] == 1.0
        assert result["metrics"]["rule_status_accuracy"] == 1.0
        assert result["metrics"]["rule_severity_accuracy"] == 1.0
        assert result["metrics"]["rule_evidence_coverage"] == 1.0
        assert result["metrics"]["source_type"] == "synthetic"
        assert result["metrics"]["dataset_kind"] == "non_production_manual_acceptance"
        assert result["metrics"]["is_dataset_driven"] is True
        assert result["metrics"]["is_production_evaluation"] is False
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_manual_acceptance_rule_manifest_covers_phase_a_scenarios() -> None:
    response = client.post(
        "/api/v1/evaluations/run",
        json={
            "eval_type": "rule",
            "dataset_name": "manual_acceptance",
            "dataset_path": "evals/datasets/manual_acceptance/dataset_manifest.json",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    metrics = result["metrics"]
    assert result["sample_count"] >= 18
    assert result["failed_cases"] == []
    assert set(metrics["covered_scenarios"]) == {"procurement", "sales", "confirmation", "interview", "contract_review"}
    assert {"pass", "fail", "warning", "need_review"}.issubset(set(metrics["covered_status_boundaries"]))
    assert metrics["covered_rule_count"] >= 10
    assert metrics["review_routing_accuracy"] == 1.0
    assert metrics["rule_version_accuracy"] == 1.0
    assert metrics["rule_parameter_accuracy"] == 1.0
    assert metrics["evaluation_status"] == "synthetic_only"


def test_full_db_workflow_manifest_creates_persisted_artifacts() -> None:
    response = client.post(
        "/api/v1/evaluations/run",
        json={
            "eval_type": "full_db_workflow",
            "dataset_name": "manual_acceptance",
            "dataset_path": "evals/datasets/manual_acceptance/dataset_manifest.json",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    metrics = result["metrics"]
    assert result["sample_count"] == 1
    assert result["failed_cases"] == []
    assert metrics["full_db_workflow_pass_rate"] == 1.0
    assert metrics["provider_quality_evaluation"] is False
    assert metrics["evaluation_status"] == "synthetic_only"
    with SessionLocal() as db:
        assert db.query(AuditTask).count() >= 1
        task = db.query(AuditTask).order_by(AuditTask.created_at.desc()).first()
        assert task is not None
        assert db.query(Document).filter(Document.task_id == task.id).count() >= 3
        assert (
            db.query(DocumentPage)
            .join(Document, DocumentPage.document_id == Document.id)
            .filter(Document.task_id == task.id)
            .count()
            >= 3
        )
        assert db.query(ExtractedField).filter(ExtractedField.task_id == task.id).count() >= 10
        assert db.query(DocumentRelation).filter(DocumentRelation.task_id == task.id).count() >= 1
        assert db.query(AuditResult).filter(AuditResult.task_id == task.id).count() >= 1
        assert db.query(Report).filter(Report.task_id == task.id).count() >= 1
        assert db.query(ControlTableRow).filter(ControlTableRow.task_id == task.id).count() >= 1


def test_full_db_workflow_manifest_records_failed_cases_for_bad_samples() -> None:
    dataset_dir = evaluation_service.evaluation_datasets_root() / "phase_a_full_db_failures"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = dataset_dir / "full_db_workflow.json"
    dataset_path.write_text(
        json.dumps(
            {
                "eval_type": "full_db_workflow",
                "dataset_name": "phase_a_full_db_failures",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "missing-documents",
                        "input": {"documents": []},
                        "expected": {"status": "completed"},
                    },
                    {
                        "sample_id": "rule-result-mismatch",
                        "input": {"documents": _phase_a_procurement_documents()},
                        "expected": {
                            "status": "completed",
                            "expected_rule_results": [{"rule_id": "PROC_AMOUNT_001", "status": "fail"}],
                        },
                    },
                    {
                        "sample_id": "missing-evidence-index",
                        "input": {"documents": _phase_a_procurement_documents()},
                        "expected": {
                            "status": "completed",
                            "min_evidence_ref_count": 999,
                        },
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
                "eval_type": "full_db_workflow",
                "dataset_name": "phase_a_full_db_failures",
                "dataset_path": str(dataset_path.relative_to(evaluation_service.PROJECT_ROOT)),
            },
        )

        assert response.status_code == 200, response.text
        result = response.json()
        metrics = result["metrics"]
        assert result["sample_count"] == 3
        assert len(result["failed_cases"]) == 3
        assert metrics["failed_case_count"] == 3
        assert metrics["full_db_workflow_success_rate"] == 0.0
        assert metrics["full_db_workflow_failure_rate"] == 1.0
        assert metrics["full_db_workflow_pass_rate"] == 0.0
        assert {case["title"] for case in result["failed_cases"]} == {
            "missing-documents",
            "rule-result-mismatch",
            "missing-evidence-index",
        }
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_phase_a_api_depth_e2e_runs_core_workflow_endpoints() -> None:
    task_response = client.post("/api/v1/tasks", json={"name": "Phase A API-depth E2E", "scenario": "procurement"})
    assert task_response.status_code == 200, task_response.text
    task = task_response.json()

    documents = []
    for document in _phase_a_procurement_documents():
        upload = client.post(
            f"/api/v1/tasks/{task['id']}/documents",
            files={"file": (document["filename"], make_pdf(document["text"]), "application/pdf")},
        )
        assert upload.status_code == 200, upload.text
        documents.append(upload.json())

    for document in documents:
        ocr = client.post(f"/api/v1/documents/{document['id']}/ocr")
        assert ocr.status_code == 200, ocr.text
        pages = client.get(f"/api/v1/documents/{document['id']}/pages")
        assert pages.status_code == 200, pages.text
        assert len(pages.json()) >= 1

        classify = client.post(f"/api/v1/documents/{document['id']}/classify")
        assert classify.status_code == 200, classify.text
        assert classify.json()["doc_type"] in {"purchase_contract", "invoice", "payment_receipt"}

        extract = client.post(f"/api/v1/documents/{document['id']}/extract")
        assert extract.status_code == 200, extract.text
        assert extract.json()

        fields = client.get(f"/api/v1/documents/{document['id']}/fields")
        assert fields.status_code == 200, fields.text
        assert fields.json()

    task_fields = client.get(f"/api/v1/tasks/{task['id']}/fields")
    assert task_fields.status_code == 200, task_fields.text
    assert len(task_fields.json()) >= 10

    linkage = client.post(f"/api/v1/tasks/{task['id']}/link-documents")
    assert linkage.status_code == 200, linkage.text
    assert linkage.json()["relation_count"] >= 1

    relations = client.get(f"/api/v1/tasks/{task['id']}/document-relations")
    assert relations.status_code == 200, relations.text
    assert relations.json()

    audit = client.post(f"/api/v1/tasks/{task['id']}/audit")
    assert audit.status_code == 200, audit.text
    audit_results = audit.json()
    assert audit_results
    assert any(result["evidence"] for result in audit_results)

    listed_results = client.get(f"/api/v1/tasks/{task['id']}/audit-results")
    assert listed_results.status_code == 200, listed_results.text
    assert len(listed_results.json()) == len(audit_results)

    result_detail = client.get(f"/api/v1/audit-results/{audit_results[0]['id']}")
    assert result_detail.status_code == 200, result_detail.text
    assert result_detail.json()["rule_code"]

    report = client.post(f"/api/v1/tasks/{task['id']}/reports/control-table")
    assert report.status_code == 200, report.text
    report_body = report.json()
    assert report_body["status"] == "completed"

    reports = client.get(f"/api/v1/tasks/{task['id']}/reports")
    assert reports.status_code == 200, reports.text
    assert [item["id"] for item in reports.json()] == [report_body["id"]]

    download = client.get(f"/api/v1/reports/{report_body['id']}/download")
    assert download.status_code == 200, download.text
    assert download.content


def test_production_readiness_dataset_blocks_without_external_resources() -> None:
    response = client.post(
        "/api/v1/evaluations/run",
        json={
            "eval_type": "full_db_workflow",
            "dataset_name": "production_readiness",
            "dataset_path": "evals/datasets/production_readiness/dataset_manifest.json",
        },
    )

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["sample_count"] == 0
    assert result["failed_cases"] == []
    assert result["metrics"]["external_resource_required"] is True
    assert result["metrics"]["blocked_external_dependency_count"] == 1
    assert result["metrics"]["evaluation_status"] == "blocked_external_dependency"


def _phase_a_procurement_documents() -> list[dict]:
    return [
        {
            "filename": "purchase_contract_sample.pdf",
            "text": (
                "Purchase Contract\n"
                "Contract No: PO-2026-001\n"
                "Signing Date: 2026-07-01\n"
                "Buyer Name: Demo Company\n"
                "Supplier Name: Demo Supplier Pty Ltd\n"
                "Item: Audit Service; Quantity: 1; Unit: pcs; Unit Price: 1100.00; Amount: 1100.00\n"
                "Amount Including Tax: CNY 1100.00\n"
                "Payment Terms: Net 30"
            ),
        },
        {
            "filename": "invoice_sample.pdf",
            "text": (
                "Invoice\n"
                "Invoice No: INV-2026-001\n"
                "Invoice Date: 2026-07-01\n"
                "Seller Name: Demo Supplier Pty Ltd\n"
                "Buyer Name: Demo Company\n"
                "Item: Audit Service; Quantity: 1; Unit: pcs; Unit Price: 1100.00; Amount: 1100.00\n"
                "Amount Including Tax: CNY 1100.00\n"
                "Tax Amount: CNY 100.00"
            ),
        },
        {
            "filename": "payment_receipt_sample.pdf",
            "text": (
                "Payment Receipt\n"
                "Transaction No: PAY-2026-001\n"
                "Payment Date: 2026-07-01\n"
                "Payer Name: Demo Company\n"
                "Payee Name: Demo Supplier Pty Ltd\n"
                "Amount: CNY 1100.00\n"
                "Currency: CNY\n"
                "Payment Purpose: Payment for contract PO-2026-001 and invoice INV-2026-001"
            ),
        },
    ]


def test_manual_acceptance_rag_manifest_runs_inline_documents(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_rag_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_rag_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"rag": "rag.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "rag.json").write_text(
        json.dumps(
            {
                "eval_type": "rag",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "rag-answer",
                        "input": {
                            "query": "What is the approval requirement for procurement above CNY 1000?",
                            "documents": [
                                {
                                    "document_id": "synthetic_regulation_procurement_policy_001",
                                    "title": "Synthetic Procurement Approval Policy",
                                    "content": "Procurement transactions above CNY 1000 require manager approval before payment.",
                                }
                            ],
                        },
                        "expected": {
                            "answer_must_contain": ["manager approval", "above CNY 1000"],
                            "must_have_citation": True,
                            "expected_citation_document_id": "synthetic_regulation_procurement_policy_001",
                            "no_answer": False,
                        },
                    },
                    {
                        "sample_id": "rag-no-answer",
                        "input": {
                            "query": "What is the required approval policy for cryptocurrency treasury staking?",
                            "documents": [
                                {
                                    "document_id": "synthetic_regulation_procurement_policy_001",
                                    "content": "Procurement transactions above CNY 1000 require manager approval before payment.",
                                }
                            ],
                        },
                        "expected": {
                            "answer_must_not_fabricate": True,
                            "must_have_citation": False,
                            "no_answer": True,
                            "expected_status": "evidence_insufficient",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_if_rag_service_called(*args, **kwargs):
        raise AssertionError("Inline RAG dataset runner must not call the persistent RAG service")

    monkeypatch.setattr(evaluation_service.rag_service, "query", fail_if_rag_service_called)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "rag",
                "dataset_name": "manual_acceptance_rag_unit",
                "dataset_path": "evals/datasets/manual_acceptance_rag_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["dataset_name"] == "manual_acceptance_rag_unit"
        assert result["sample_count"] == 2
        assert result["failed_cases"] == []
        assert result["metrics"]["rag_sample_pass_rate"] == 1.0
        assert result["metrics"]["answer_text_accuracy"] == 1.0
        assert result["metrics"]["citation_presence_accuracy"] == 1.0
        assert result["metrics"]["citation_document_accuracy"] == 1.0
        assert result["metrics"]["no_answer_accuracy"] == 1.0
        assert result["metrics"]["source_type"] == "synthetic"
        assert result["metrics"]["dataset_kind"] == "non_production_manual_acceptance"
        assert result["metrics"]["is_dataset_driven"] is True
        assert result["metrics"]["is_production_evaluation"] is False
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_manual_acceptance_agent_manifest_runs_workflow_contracts(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_agent_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_agent_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"agent": "agent.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "agent.json").write_text(
        json.dumps(
            {
                "eval_type": "agent",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "agent-procurement-review",
                        "input": {
                            "available_tools": [
                                "run_ocr",
                                "classify_document",
                                "extract_fields",
                                "link_business_documents",
                                "run_rule_engine",
                                "retrieve_evidence",
                                "generate_control_table",
                                "create_review_ticket",
                                "direct_rule_verdict",
                            ],
                            "risk_signal": {"rule_id": "PROC_AMOUNT_001", "status": "fail", "severity": "high"},
                        },
                        "expected": {
                            "workflow_success": True,
                            "must_use_tools": [
                                "run_ocr",
                                "classify_document",
                                "extract_fields",
                                "link_business_documents",
                                "run_rule_engine",
                                "create_review_ticket",
                            ],
                            "forbidden_tools": ["direct_rule_verdict", "final_audit_opinion_without_review"],
                            "must_route_to_review": True,
                            "conclusion_generated": False,
                            "final_status": "pending_review",
                        },
                    },
                    {
                        "sample_id": "agent-rag-insufficient",
                        "input": {
                            "available_tools": ["retrieve_evidence", "create_review_ticket"],
                            "rag_result": {"citation_count": 0, "status": "no_answer"},
                        },
                        "expected": {
                            "workflow_success": True,
                            "must_use_tools": ["retrieve_evidence", "create_review_ticket"],
                            "forbidden_tools": [
                                "generate_conclusion_without_citation",
                                "final_audit_opinion_without_review",
                            ],
                            "must_route_to_review": True,
                            "conclusion_generated": False,
                            "final_status": "evidence_insufficient",
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_if_agent_workflow_called(*args, **kwargs):
        raise AssertionError("Agent dataset runner must not call the real AgentService workflow")

    monkeypatch.setattr(evaluation_service.agent_service, "create_run", fail_if_agent_workflow_called)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "agent",
                "dataset_name": "manual_acceptance_agent_unit",
                "dataset_path": "evals/datasets/manual_acceptance_agent_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["dataset_name"] == "manual_acceptance_agent_unit"
        assert result["sample_count"] == 2
        assert result["failed_cases"] == []
        assert result["metrics"]["agent_sample_pass_rate"] == 1.0
        assert result["metrics"]["workflow_success_accuracy"] == 1.0
        assert result["metrics"]["required_tool_coverage"] == 1.0
        assert result["metrics"]["forbidden_tool_violation_rate"] == 0.0
        assert result["metrics"]["review_routing_accuracy"] == 1.0
        assert result["metrics"]["conclusion_guardrail_accuracy"] == 1.0
        assert result["metrics"]["final_status_accuracy"] == 1.0
        assert result["metrics"]["source_type"] == "synthetic"
        assert result["metrics"]["dataset_kind"] == "non_production_manual_acceptance"
        assert result["metrics"]["is_dataset_driven"] is True
        assert result["metrics"]["is_production_evaluation"] is False
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_manual_acceptance_e2e_manifest_runs_procurement_contract(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_e2e_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_e2e_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"end_to_end": "e2e.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "e2e.json").write_text(
        json.dumps(
            {
                "eval_type": "end_to_end",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "e2e-procurement",
                        "scenario": "procurement",
                        "input": {
                            "documents": [
                                {
                                    "doc_type": "purchase_contract",
                                    "filename": "purchase_contract_sample.pdf",
                                    "text": "Purchase Contract\nContract No: PO-2026-001\nAmount Including Tax: CNY 1100.00",
                                },
                                {
                                    "doc_type": "invoice",
                                    "filename": "invoice_sample.pdf",
                                    "text": "Invoice\nInvoice No: INV-2026-001\nAmount Including Tax: CNY 1100.00",
                                },
                                {
                                    "doc_type": "payment_receipt",
                                    "filename": "payment_receipt_sample.pdf",
                                    "text": "Payment Receipt\nTransaction No: PAY-2026-001\nPayment Amount: CNY 1100.00",
                                },
                            ]
                        },
                        "expected": {
                            "workflow_success": True,
                            "required_steps": [
                                "upload_documents",
                                "run_ocr",
                                "classify_documents",
                                "extract_fields",
                                "link_business_documents",
                                "run_rule_engine",
                                "generate_control_table",
                            ],
                            "expected_doc_types": ["purchase_contract", "invoice", "payment_receipt"],
                            "expected_business_key": "PO-2026-001",
                            "expected_rule_results": [{"rule_id": "PROC_AMOUNT_001", "status": "pass"}],
                            "must_generate_report": True,
                            "must_have_evidence_index": True,
                            "must_not_auto_confirm_high_risk": True,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_if_real_workflow_called(*args, **kwargs):
        raise AssertionError("E2E dataset runner must not call the real DB/API workflow")

    monkeypatch.setattr(evaluation_service.ocr_service, "run_ocr", fail_if_real_workflow_called)
    monkeypatch.setattr(evaluation_service.classification_service, "classify_document", fail_if_real_workflow_called)
    monkeypatch.setattr(evaluation_service.extraction_service, "extract_document", fail_if_real_workflow_called)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "end_to_end",
                "dataset_name": "manual_acceptance_e2e_unit",
                "dataset_path": "evals/datasets/manual_acceptance_e2e_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["dataset_name"] == "manual_acceptance_e2e_unit"
        assert result["sample_count"] == 1
        assert result["failed_cases"] == []
        assert result["metrics"]["e2e_sample_pass_rate"] == 1.0
        assert result["metrics"]["required_step_coverage"] == 1.0
        assert result["metrics"]["document_classification_accuracy"] == 1.0
        assert result["metrics"]["business_key_accuracy"] == 1.0
        assert result["metrics"]["rule_result_accuracy"] == 1.0
        assert result["metrics"]["report_generation_accuracy"] == 1.0
        assert result["metrics"]["evidence_index_accuracy"] == 1.0
        assert result["metrics"]["high_risk_guardrail_accuracy"] == 1.0
        assert result["metrics"]["source_type"] == "synthetic"
        assert result["metrics"]["dataset_kind"] == "non_production_manual_acceptance"
        assert result["metrics"]["is_dataset_driven"] is True
        assert result["metrics"]["is_production_evaluation"] is False
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_manual_acceptance_regression_manifest_aggregates_dataset_results(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_regression_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_regression_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"regression": "regression.json"},
            }
        ),
        encoding="utf-8",
    )
    required_eval_types = ["ocr", "classification", "extraction", "rule", "rag", "agent", "end_to_end"]
    (dataset_dir / "regression.json").write_text(
        json.dumps(
            {
                "eval_type": "regression",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "regression-all-pass",
                        "input": {
                            "required_eval_types": required_eval_types,
                            "dataset_path": "evals/datasets/manual_acceptance_regression_unit/dataset_manifest.json",
                        },
                        "expected": {
                            "all_required_eval_types_pass": True,
                            "max_failed_cases": 0,
                            "required_dataset_driven": True,
                            "required_non_production_flag": True,
                            "required_eval_type_count": 7,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run_regression_eval_type(db, eval_type, dataset_path, dataset_name):
        calls.append((eval_type, dataset_path, dataset_name))
        return 1, {"is_dataset_driven": True, "is_production_evaluation": False}, []

    monkeypatch.setattr(evaluation_service, "_run_regression_eval_type", fake_run_regression_eval_type)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "regression",
                "dataset_name": "manual_acceptance_regression_unit",
                "dataset_path": "evals/datasets/manual_acceptance_regression_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        metrics = result["metrics"]
        assert [call[0] for call in calls] == required_eval_types
        assert result["failed_cases"] == []
        assert metrics["regression_sample_pass_rate"] == 1.0
        assert metrics["required_eval_type_count"] == 7
        assert metrics["executed_eval_type_count"] == 7
        assert metrics["total_failed_cases"] == 0
        assert metrics["all_required_eval_types_pass"] is True
        assert metrics["dataset_driven_coverage"] == 1.0
        assert metrics["non_production_flag_accuracy"] == 1.0
        assert len(metrics["per_eval_type_results"]) == 7
        assert metrics["dataset_kind"] == "non_production_manual_acceptance"
        assert metrics["is_production_evaluation"] is False
    finally:
        shutil.rmtree(dataset_dir, ignore_errors=True)


def test_manual_acceptance_regression_manifest_blocks_recursive_eval_type(monkeypatch) -> None:
    dataset_dir = evaluation_service.evals_datasets_root() / "manual_acceptance_regression_guard_unit"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    (dataset_dir / "dataset_manifest.json").write_text(
        json.dumps(
            {
                "dataset_name": "manual_acceptance_regression_guard_unit",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "files": {"regression": "regression.json"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_dir / "regression.json").write_text(
        json.dumps(
            {
                "eval_type": "regression",
                "source_type": "synthetic",
                "is_production_evaluation": False,
                "samples": [
                    {
                        "sample_id": "regression-recursive-blocked",
                        "input": {
                            "required_eval_types": ["classification", "regression"],
                            "dataset_path": "evals/datasets/manual_acceptance_regression_guard_unit/dataset_manifest.json",
                        },
                        "expected": {
                            "all_required_eval_types_pass": True,
                            "max_failed_cases": 0,
                            "required_dataset_driven": True,
                            "required_non_production_flag": True,
                            "required_eval_type_count": 2,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    calls = []

    def fake_run_regression_eval_type(db, eval_type, dataset_path, dataset_name):
        calls.append(eval_type)
        return 1, {"is_dataset_driven": True, "is_production_evaluation": True}, []

    monkeypatch.setattr(evaluation_service, "_run_regression_eval_type", fake_run_regression_eval_type)
    try:
        response = client.post(
            "/api/v1/evaluations/run",
            json={
                "eval_type": "regression",
                "dataset_name": "manual_acceptance_regression_guard_unit",
                "dataset_path": "evals/datasets/manual_acceptance_regression_guard_unit/dataset_manifest.json",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        metrics = result["metrics"]
        assert calls == ["classification"]
        assert metrics["executed_eval_type_count"] == 1
        assert metrics["total_failed_cases"] == 1
        assert metrics["dataset_driven_coverage"] == 0.5
        assert metrics["non_production_flag_accuracy"] == 0.5
        assert metrics["per_eval_type_results"][1]["eval_type"] == "regression"
        assert metrics["per_eval_type_results"][1]["status"] == "blocked"
        assert result["failed_cases"][0]["expected_output"]["checks"]["all_required_eval_types_pass_ok"] is False
        assert result["failed_cases"][0]["expected_output"]["checks"]["max_failed_cases_ok"] is False
        assert result["failed_cases"][0]["expected_output"]["checks"]["required_dataset_driven_ok"] is False
        assert result["failed_cases"][0]["expected_output"]["checks"]["required_non_production_flag_ok"] is False
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
