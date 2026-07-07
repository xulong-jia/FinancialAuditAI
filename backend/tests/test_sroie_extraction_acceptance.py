import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services import evaluation_service


client = TestClient(app)


def _write_sroie_extraction_manifest(
    tmp_path: Path,
    *,
    entities: dict | None = None,
    expected: dict | None = None,
    source_type: str = "public_dataset",
    is_production_evaluation: bool = False,
    sample_extra: dict | None = None,
) -> str:
    dataset_dir = tmp_path / "local_storage" / "external_acceptance" / "production_dataset" / "extraction" / "sroie"
    files_dir = dataset_dir / "files"
    entities_dir = dataset_dir / "entities"
    labels_dir = dataset_dir / "labels"
    box_dir = dataset_dir / "box"
    for directory in (files_dir, entities_dir, labels_dir, box_dir):
        directory.mkdir(parents=True, exist_ok=True)

    entities_payload = entities or {
        "company": "ABC SDN BHD",
        "date": "12-01-19",
        "address": "No 55 Jalan Sri Bahari Taman 10050 Pulau Pinang",
        "total": "12.00",
    }
    (files_dir / "sample.jpg").write_bytes(b"public-sroie-sample")
    (entities_dir / "sample.txt").write_text(json.dumps(entities_payload), encoding="utf-8")
    (labels_dir / "sample.label.json").write_text(
        json.dumps({"expected": {"key_information": entities_payload}}),
        encoding="utf-8",
    )
    box_lines = [
        f"0,0,100,0,100,10,0,10,{entities_payload.get('company', '')}",
        f"0,12,100,12,100,22,0,22,{entities_payload.get('date', '')}",
        f"0,24,100,24,100,34,0,34,{entities_payload.get('address', '')}",
        f"0,36,100,36,100,46,0,46,{entities_payload.get('total', '')}",
    ]
    (box_dir / "sample.txt").write_text("\n".join(box_lines), encoding="utf-8")

    sample = {
        "sample_id": "sroie-public-extraction-sample",
        "document_type": "invoice",
        "file_path": "files/sample.jpg",
        "entities_path": "entities/sample.txt",
        "ocr_label_path": "labels/sample.label.json",
        "box_path": "box/sample.txt",
        "expected": expected or {"require_source_evidence": True, "require_source_bbox": False},
    }
    sample.update(sample_extra or {})
    (dataset_dir / "sroie_extraction_external_manifest.json").write_text(
        json.dumps(
            {
                "eval_type": "extraction",
                "dataset_name": "sroie_public_extraction_acceptance_unit",
                "version": "0.1.0",
                "source_type": source_type,
                "is_production_evaluation": is_production_evaluation,
                "sample_count": 1,
                "samples": [sample],
            }
        ),
        encoding="utf-8",
    )
    return "local_storage/external_acceptance/production_dataset/extraction/sroie/sroie_extraction_external_manifest.json"


def _run_sroie_eval(dataset_path: str) -> dict:
    response = client.post(
        "/api/v1/evaluations/run",
        json={
            "eval_type": "extraction",
            "dataset_name": "sroie_public_extraction_acceptance_unit",
            "dataset_path": dataset_path,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_sroie_extraction_public_manifest_runs_normalized_field_match(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(evaluation_service, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(
        evaluation_service.extraction_service.llm_provider,
        "get_llm_provider",
        lambda: (_ for _ in ()).throw(AssertionError("SROIE extraction acceptance must not call a real provider")),
    )
    dataset_path = _write_sroie_extraction_manifest(tmp_path)

    result = _run_sroie_eval(dataset_path)

    metrics = result["metrics"]
    assert result["sample_count"] == 1
    assert result["failed_cases"] == []
    assert metrics["source_type"] == "public_dataset"
    assert metrics["is_production_evaluation"] is False
    assert metrics["production_evaluation"] is False
    assert metrics["evaluation_status"] == "non_production_public_acceptance"
    assert metrics["extraction_public_sample_pass_rate"] == 1.0
    assert metrics["extraction_public_field_accuracy"] == 1.0
    assert metrics["extraction_public_company_accuracy"] == 1.0
    assert metrics["extraction_public_date_accuracy"] == 1.0
    assert metrics["extraction_public_total_accuracy"] == 1.0
    assert metrics["extraction_public_evidence_coverage"] == 1.0


def test_sroie_extraction_public_dataset_cannot_be_marked_production(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(evaluation_service, "PROJECT_ROOT", tmp_path)
    dataset_path = _write_sroie_extraction_manifest(tmp_path, is_production_evaluation=True)

    result = _run_sroie_eval(dataset_path)

    metrics = result["metrics"]
    assert metrics["source_type"] == "public_dataset"
    assert metrics["is_production_evaluation"] is False
    assert metrics["production_evaluation"] is False
    assert "production_evaluation requires source_type=desensitized or production_approved" in metrics["production_guard_warnings"]


def test_sroie_extraction_address_token_overlap_passes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(evaluation_service, "PROJECT_ROOT", tmp_path)
    dataset_path = _write_sroie_extraction_manifest(
        tmp_path,
        entities={
            "company": "ABC SDN BHD",
            "date": "25/12/2018",
            "address": "No 55 Jalan Sri Bahari Taman 10050 Pulau Pinang",
            "total": "12.00",
        },
        expected={
            "fields": {
                "address": {"value": "NO.55, JALAN SRI BAHARI, TAMAN, 10050 PULAU PINANG"},
            },
            "require_source_evidence": True,
            "require_source_bbox": False,
        },
    )

    result = _run_sroie_eval(dataset_path)

    assert result["failed_cases"] == []
    assert result["metrics"]["extraction_public_address_accuracy"] == 1.0


def test_sroie_extraction_missing_expected_field_reports_failed_case(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(evaluation_service, "PROJECT_ROOT", tmp_path)
    dataset_path = _write_sroie_extraction_manifest(
        tmp_path,
        expected={
            "fields": {
                "total": {"value_normalized": {"amount": 999.0}},
            },
            "require_source_evidence": True,
            "require_source_bbox": False,
        },
    )

    result = _run_sroie_eval(dataset_path)

    assert result["failed_cases"]
    assert result["metrics"]["failed_case_count"] == 1
    assert result["metrics"]["extraction_public_total_accuracy"] == 0.0
    assert result["failed_cases"][0]["model_output"]["failed_checks"][0]["field_name"] == "total"


def test_sroie_extraction_rejects_path_escape(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(evaluation_service, "PROJECT_ROOT", tmp_path)
    dataset_path = _write_sroie_extraction_manifest(
        tmp_path,
        sample_extra={"entities_path": "../outside.txt"},
    )

    response = client.post(
        "/api/v1/evaluations/run",
        json={"eval_type": "extraction", "dataset_name": "sroie_public_extraction_acceptance_unit", "dataset_path": dataset_path},
    )

    assert response.status_code == 400
    assert "entities_path" in response.json()["detail"]


def test_sroie_extraction_rejects_absolute_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(evaluation_service, "PROJECT_ROOT", tmp_path)
    dataset_path = _write_sroie_extraction_manifest(
        tmp_path,
        sample_extra={"entities_path": str(tmp_path / "outside.txt")},
    )

    response = client.post(
        "/api/v1/evaluations/run",
        json={"eval_type": "extraction", "dataset_name": "sroie_public_extraction_acceptance_unit", "dataset_path": dataset_path},
    )

    assert response.status_code == 400
    assert "entities_path" in response.json()["detail"]
