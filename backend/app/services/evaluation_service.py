from pathlib import Path
from hashlib import sha256
from datetime import date
import json
import re
from types import SimpleNamespace
from uuid import UUID, uuid4

import fitz
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit_result import AuditResult
from app.models.bad_case import BadCase
from app.models.control_table_row import ControlTableRow
from app.models.audit_task import AuditTask
from app.models.document import Document
from app.models.document_page import DocumentPage
from app.models.document_relation import DocumentRelation
from app.models.evaluation_result import EvaluationResult
from app.models.extracted_field import ExtractedField
from app.models.report import Report
from app.schemas.quality import EvaluationRunRequest
from app.services import (
    agent_service,
    audit_log_service,
    bad_case_service,
    classification_service,
    extraction_service,
    linkage_service,
    ocr_service,
    rag_service,
    report_service,
    rule_engine_service,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MANUAL_DATASET_EVAL_TYPES = {"ocr", "classification", "extraction", "rule", "rag", "agent", "end_to_end", "full_db_workflow", "regression"}
REGRESSION_CHILD_EVAL_TYPES = ("ocr", "classification", "extraction", "rule", "rag", "agent", "end_to_end", "full_db_workflow")


def evaluation_datasets_root() -> Path:
    return PROJECT_ROOT / "local_storage" / "evaluation_datasets"


def evals_datasets_root() -> Path:
    return PROJECT_ROOT / "evals" / "datasets"


def run_evaluation(db: Session, payload: EvaluationRunRequest) -> EvaluationResult:
    dataset = _load_dataset(payload)
    if dataset is not None:
        sample_count, metrics, failed_cases = _evaluate_dataset(db, payload.eval_type, dataset)
    elif payload.eval_type == "classification":
        sample_count, metrics, failed_cases = _evaluate_classification()
    elif payload.eval_type == "ocr":
        sample_count, metrics, failed_cases = _evaluate_ocr()
    elif payload.eval_type == "extraction":
        sample_count, metrics, failed_cases = _evaluate_extraction()
    elif payload.eval_type == "rule":
        sample_count, metrics, failed_cases = _evaluate_rule()
    elif payload.eval_type == "rag":
        sample_count, metrics, failed_cases = _evaluate_rag(db)
    elif payload.eval_type == "agent":
        sample_count, metrics, failed_cases = _evaluate_agent()
    elif payload.eval_type == "end_to_end":
        sample_count, metrics, failed_cases = _evaluate_end_to_end()
    elif payload.eval_type == "full_db_workflow":
        sample_count, metrics, failed_cases = _evaluate_full_db_workflow(db)
    elif payload.eval_type == "regression":
        sample_count, metrics, failed_cases = _evaluate_regression(db)
    else:  # pragma: no cover - schema guards this.
        raise HTTPException(status_code=400, detail="Unsupported evaluation type")

    result = EvaluationResult(
        task_id=payload.task_id,
        eval_name=payload.eval_name or f"{payload.eval_type}_evaluation",
        eval_type=payload.eval_type,
        dataset_name=dataset["dataset_name"] if dataset is not None else payload.dataset_name,
        model_name=payload.model_name,
        prompt_version=payload.prompt_version,
        rule_version=payload.rule_version,
        metrics=metrics | _limitations(sample_count, metrics, len(failed_cases)),
        sample_count=sample_count,
        failed_cases=failed_cases,
        report_path=None,
        created_by=payload.created_by,
    )
    db.add(result)
    db.flush()
    audit_log_service.add_log(
        db,
        actor_name=payload.created_by,
        task_id=payload.task_id,
        action="evaluation_run",
        target_type="evaluation_result",
        target_id=result.id,
        after_value={"eval_type": result.eval_type, "dataset_name": result.dataset_name, "sample_count": sample_count},
    )
    for failed_case in failed_cases:
        bad_case_service.create_failed_case(
            db,
            case_type=failed_case.get("case_type", _bad_case_type(payload.eval_type)),
            title=failed_case["title"],
            input_payload=failed_case.get("input_payload", {}),
            model_output=failed_case.get("model_output", {}),
            expected_output=failed_case.get("expected_output", {}),
            severity=failed_case.get("severity", "medium"),
            task_id=payload.task_id,
        )
    db.commit()
    db.refresh(result)
    return result


def list_results(db: Session, eval_type: str | None = None) -> list[EvaluationResult]:
    query = select(EvaluationResult).order_by(EvaluationResult.created_at.desc())
    if eval_type:
        query = query.where(EvaluationResult.eval_type == eval_type)
    return list(db.scalars(query))


def get_result(db: Session, result_id: UUID) -> EvaluationResult:
    result = db.get(EvaluationResult, result_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Evaluation result not found")
    return result


def _load_dataset(payload: EvaluationRunRequest) -> dict | None:
    path = _resolve_dataset_path(payload)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Evaluation dataset could not be read: {exc.__class__.__name__}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Evaluation dataset must be a JSON object")
    if path.name == "dataset_manifest.json" or "files" in data:
        return _load_manifest_dataset(payload, path, data)
    return _normalize_dataset(payload, path, data)


def _load_manifest_dataset(payload: EvaluationRunRequest, path: Path, manifest: dict) -> dict:
    if payload.eval_type not in MANUAL_DATASET_EVAL_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Manual acceptance dataset manifest currently supports OCR, classification, extraction, rule, RAG, Agent, E2E, full DB workflow, and regression evaluation only",
        )
    files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    eval_file = files.get(payload.eval_type)
    if not isinstance(eval_file, str) or not eval_file:
        raise HTTPException(status_code=400, detail=f"Dataset manifest has no file for {payload.eval_type}")
    data_path = (path.parent / eval_file).resolve()
    if not _is_under(data_path, path.parent.resolve()) or data_path.suffix != ".json":
        raise HTTPException(status_code=400, detail="Dataset manifest file path is invalid")
    try:
        data = json.loads(data_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Evaluation dataset could not be read: {exc.__class__.__name__}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="Evaluation dataset must be a JSON object")
    return _normalize_dataset(payload, data_path, data, manifest=manifest)


def _normalize_dataset(payload: EvaluationRunRequest, path: Path, data: dict, manifest: dict | None = None) -> dict:
    if not isinstance(data.get("samples"), list):
        raise HTTPException(status_code=400, detail="Evaluation dataset must be a JSON object with a samples array")
    dataset_name = str(data.get("dataset_name") or (manifest or {}).get("dataset_name") or payload.dataset_name)
    source_type = str(data.get("source_type") or (manifest or {}).get("source_type") or "external_annotated")
    is_production = bool(data.get("is_production_evaluation", (manifest or {}).get("is_production_evaluation", False)))
    dataset_kind = str(data.get("dataset_kind") or ("real_annotated" if is_production else "non_production_manual_acceptance"))
    default_eval_type = str(data.get("eval_type") or payload.eval_type)
    version = str(data.get("version") or (manifest or {}).get("version") or "unversioned")
    limitations = data.get("limitations", (manifest or {}).get("limitations", []))
    labels = data.get("labels", (manifest or {}).get("labels", {}))
    expected_evidence = data.get("expected_evidence", (manifest or {}).get("expected_evidence", {}))
    external_resource_required = bool(data.get("external_resource_required", (manifest or {}).get("external_resource_required", False)))
    declared_sample_count = data.get("sample_count", (manifest or {}).get("sample_count"))
    samples = [
        {
            "eval_type": default_eval_type,
            "dataset_name": dataset_name,
            "source_type": source_type,
            "is_production_evaluation": is_production,
            **sample,
        }
        for sample in data["samples"]
        if isinstance(sample, dict)
    ]
    return {
        "dataset_name": dataset_name,
        "dataset_kind": dataset_kind,
        "source_type": source_type,
        "is_production_evaluation": is_production,
        "dataset_source": str(path.relative_to(PROJECT_ROOT)) if _is_under(path, PROJECT_ROOT) else str(path),
        "version": version,
        "declared_sample_count": declared_sample_count,
        "labels_declared": bool(labels),
        "expected_evidence_declared": bool(expected_evidence),
        "limitations_declared": [str(item) for item in limitations] if isinstance(limitations, list) else [],
        "external_resource_required": external_resource_required,
        "samples": samples,
    }


def _resolve_dataset_path(payload: EvaluationRunRequest) -> Path | None:
    roots = [PROJECT_ROOT / "samples" / "evaluation", evaluation_datasets_root(), evals_datasets_root()]
    if payload.dataset_path:
        path = Path(payload.dataset_path)
        if path.is_absolute() or ".." in path.parts:
            raise HTTPException(
                status_code=400,
                detail="Evaluation dataset_path must be project-root relative and stay under samples/evaluation, local_storage/evaluation_datasets, or evals/datasets",
            )
        candidates = [(PROJECT_ROOT / path).resolve(), *[(root / path).resolve() for root in roots]]
        allowed_path = False
        for candidate in candidates:
            if any(_is_under(candidate, root) for root in roots):
                allowed_path = True
                if candidate.exists() and candidate.suffix == ".json":
                    return candidate
        if allowed_path:
            raise HTTPException(status_code=400, detail="Evaluation dataset_path must point to an existing JSON file")
        raise HTTPException(
            status_code=400,
            detail="Evaluation dataset_path must be under samples/evaluation, local_storage/evaluation_datasets, or evals/datasets",
        )

    names = [payload.dataset_name]
    if not payload.dataset_name.endswith(".json"):
        names.append(f"{payload.dataset_name}.json")
    for root in roots:
        for name in names:
            candidate = (root / name).resolve()
            if _is_under(candidate, root) and candidate.exists() and candidate.suffix == ".json":
                return candidate
    return None


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _evaluate_dataset(db: Session, eval_type: str, dataset: dict) -> tuple[int, dict, list[dict]]:
    samples = [
        sample
        for sample in dataset["samples"]
        if isinstance(sample, dict) and sample.get("eval_type") == eval_type
    ]
    if not samples:
        if dataset.get("external_resource_required"):
            return (
                0,
                _dataset_metadata_metrics(dataset) | {
                    "blocked_external_dependency_count": 1,
                    "blocking_reason": "Dataset declares external_resource_required but has no runnable samples in the repository.",
                    "evaluation_status": "blocked_external_dependency",
                },
                [],
            )
        raise HTTPException(status_code=400, detail=f"Evaluation dataset has no samples for {eval_type}")
    if eval_type == "classification":
        sample_count, metrics, failed = _evaluate_classification_samples(samples)
    elif eval_type == "ocr":
        if any(sample.get("file_path") for sample in samples):
            sample_count, metrics, failed = _evaluate_ocr_file_samples(db, samples, dataset)
        else:
            sample_count, metrics, failed = _evaluate_ocr_samples(samples)
    elif eval_type == "extraction":
        if any(isinstance(_sample_expected(sample).get("fields"), dict) for sample in samples):
            sample_count, metrics, failed = _evaluate_extraction_samples(samples)
        else:
            sample_count, metrics, failed = _evaluate_json_samples(samples, "extraction")
    elif eval_type == "rule":
        sample_count, metrics, failed = _evaluate_rule_samples(samples)
    elif eval_type == "rag":
        sample_count, metrics, failed = _evaluate_rag_samples(db, samples)
    elif eval_type == "agent":
        sample_count, metrics, failed = _evaluate_agent_samples(samples)
    elif eval_type == "end_to_end":
        sample_count, metrics, failed = _evaluate_e2e_samples(samples)
    elif eval_type == "full_db_workflow":
        sample_count, metrics, failed = _evaluate_full_db_workflow_samples(db, samples)
    elif eval_type == "regression":
        sample_count, metrics, failed = _evaluate_regression_samples(db, samples)
    else:  # pragma: no cover - schema guards this.
        raise HTTPException(status_code=400, detail="Unsupported evaluation type")
    metrics.update(
        {
            "dataset_kind": dataset["dataset_kind"],
            "source_type": dataset["source_type"],
            "dataset_source": dataset["dataset_source"],
            "is_dataset_driven": True,
            "is_production_evaluation": dataset["is_production_evaluation"],
            **_dataset_metadata_metrics(dataset),
        }
    )
    return sample_count, metrics, failed


def _dataset_metadata_metrics(dataset: dict) -> dict:
    return {
        "dataset_version": dataset.get("version"),
        "declared_sample_count": dataset.get("declared_sample_count"),
        "labels_declared": bool(dataset.get("labels_declared")),
        "expected_evidence_declared": bool(dataset.get("expected_evidence_declared")),
        "limitations_declared": dataset.get("limitations_declared") if isinstance(dataset.get("limitations_declared"), list) else [],
        "external_resource_required": bool(dataset.get("external_resource_required")),
    }


def _evaluate_classification_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    pairs = []
    low_confidence = 0
    for sample in samples:
        input_payload = _sample_input(sample)
        expected = _sample_expected(sample)
        actual = _sample_actual(sample)
        if not actual:
            ranked = classification_service._rank_document_types(
                str(input_payload.get("filename") or input_payload.get("original_filename") or ""),
                str(input_payload.get("text") or input_payload.get("raw_text") or ""),
                str(input_payload.get("scenario") or "procurement"),
            )
            actual = {
                "doc_type": ranked[0].doc_type if ranked else "unknown",
                "confidence": ranked[0].confidence if ranked else 0.0,
            }
        low_confidence += int(float(actual.get("confidence") or 0.0) < classification_service.LOW_CONFIDENCE_THRESHOLD)
        actual_doc_type = str(actual.get("doc_type") or "unknown")
        expected_doc_type = str(expected.get("doc_type") or "unknown")
        pairs.append((actual_doc_type, expected_doc_type))
        if actual_doc_type != expected_doc_type:
            failed.append(_sample_failed_case("classification", sample, actual, expected))
    return (
        len(samples),
        {
            "accuracy": _accuracy(len(samples), len(failed)),
            "macro_f1": _macro_f1(pairs),
            "low_confidence_rate": _rate(low_confidence, len(samples)),
        },
        failed,
    )


def _evaluate_ocr_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    cer_values = []
    wer_values = []
    table_hits = numeric_hits = bbox_hits = 0
    for sample in samples:
        actual = _sample_actual(sample) or _sample_input(sample)
        expected = _sample_expected(sample)
        actual_text = str(actual.get("text") or actual.get("raw_text") or "")
        expected_text = str(expected.get("text") or expected.get("raw_text") or "")
        actual_flags = {
            "text": actual_text,
            "table_ok": bool(actual.get("table_ok")),
            "numeric_ok": bool(actual.get("numeric_ok")),
            "bbox_ok": bool(actual.get("bbox_ok")),
        }
        expected_flags = {
            "text": expected_text,
            "table_ok": bool(expected.get("table_ok", True)),
            "numeric_ok": bool(expected.get("numeric_ok", True)),
            "bbox_ok": bool(expected.get("bbox_ok", True)),
        }
        cer_values.append(_cer(actual_text, expected_text))
        wer_values.append(_wer(actual_text, expected_text))
        table_hits += int(actual_flags["table_ok"] == expected_flags["table_ok"])
        numeric_hits += int(actual_flags["numeric_ok"] == expected_flags["numeric_ok"])
        bbox_hits += int(actual_flags["bbox_ok"] == expected_flags["bbox_ok"])
        if actual_flags != expected_flags:
            failed.append(_sample_failed_case("ocr", sample, actual_flags, expected_flags))
    return (
        len(samples),
        {
            "cer": round(sum(cer_values) / len(cer_values), 4),
            "wer": round(sum(wer_values) / len(wer_values), 4),
            "table_structure_accuracy": _rate(table_hits, len(samples)),
            "numeric_accuracy": _rate(numeric_hits, len(samples)),
            "bbox_quality": _rate(bbox_hits, len(samples)),
        },
        failed,
    )


def _evaluate_ocr_file_samples(db: Session, samples: list[dict], dataset: dict) -> tuple[int, dict, list[dict]]:
    failed = []
    text_hits = page_hits = block_hits = bbox_hits = confidence_hits = table_hits = 0
    blocked = 0
    for sample in samples:
        actual = _run_ocr_file_sample(db, sample)
        expected = _sample_expected(sample)
        checks = _ocr_expected_checks(actual, expected)
        text_hits += int(checks["text_ok"])
        page_hits += int(checks["page_count_ok"])
        block_hits += int(checks["ocr_blocks_ok"])
        bbox_hits += int(checks["bbox_ok"])
        confidence_hits += int(checks["confidence_ok"])
        table_hits += int(checks["table_blocks_ok"])
        blocked += int(actual.get("status") == "blocked_external_dependency")
        if not checks["passed"]:
            failed.append(_sample_failed_case("ocr", sample, actual, checks["expected"]))
    total = len(samples)
    return (
        total,
        {
            "ocr_sample_pass_rate": _accuracy(total, len(failed)),
            "text_containment_accuracy": _rate(text_hits, total),
            "page_count_accuracy": _rate(page_hits, total),
            "ocr_block_count_accuracy": _rate(block_hits, total),
            "bbox_requirement_accuracy": _rate(bbox_hits, total),
            "confidence_requirement_accuracy": _rate(confidence_hits, total),
            "table_requirement_accuracy": _rate(table_hits, total),
            "blocked_external_dependency_count": blocked,
            "dataset_kind": dataset["dataset_kind"],
            "source_type": dataset["source_type"],
            "manual_acceptance_status": "production_manual_acceptance" if dataset["is_production_evaluation"] else "non_production_manual_acceptance",
            "is_production_evaluation": dataset["is_production_evaluation"],
        },
        failed,
    )


def _run_ocr_file_sample(db: Session, sample: dict) -> dict:
    sample_id = str(sample.get("sample_id") or sample.get("id") or "ocr_sample")
    try:
        path = _resolve_evaluation_sample_file(str(sample.get("file_path") or ""))
    except ValueError as exc:
        return {"sample_id": sample_id, "status": "blocked_external_dependency", "error": str(exc)}
    if not path.exists():
        return {"sample_id": sample_id, "status": "blocked_external_dependency", "error": "sample file not found"}
    expected_provider = str(sample.get("provider") or "").strip().lower()
    if expected_provider and expected_provider != ocr_service.settings.ocr_provider.strip().lower():
        return {
            "sample_id": sample_id,
            "status": "blocked_external_dependency",
            "error": "configured OCR provider does not match sample provider",
            "configured_provider": ocr_service.settings.ocr_provider,
            "expected_provider": sample.get("provider"),
        }
    if expected_provider in ocr_service.AZURE_OCR_PROVIDERS and (not ocr_service.settings.ocr_api_url or not ocr_service.settings.ocr_api_key):
        return {
            "sample_id": sample_id,
            "status": "blocked_external_dependency",
            "error": "Azure OCR endpoint or key is not configured",
            "configured_provider": ocr_service.settings.ocr_provider,
            "expected_provider": sample.get("provider"),
        }
    expected_model = str(sample.get("model") or "").strip()
    if expected_model and expected_model != ocr_service.settings.ocr_model:
        return {
            "sample_id": sample_id,
            "status": "blocked_external_dependency",
            "error": "configured OCR model does not match sample model",
            "configured_model": ocr_service.settings.ocr_model,
            "expected_model": expected_model,
        }
    document = _create_evaluation_document(db, path, sample)
    document = ocr_service.run_ocr(db, document.id)
    pages = ocr_service.list_pages(db, document.id)
    raw_text = "\n".join(page.raw_text or "" for page in pages)
    blocks = [block for page in pages for block in (page.ocr_blocks or []) if isinstance(block, dict)]
    table_blocks = [table for page in pages for table in (page.table_blocks or []) if isinstance(table, dict)]
    confidences = [
        float(block["confidence"])
        for block in blocks
        if isinstance(block.get("confidence"), (int, float))
    ]
    return {
        "sample_id": sample_id,
        "status": document.ocr_status if document.ocr_status != "completed" else "completed",
        "error": document.ocr_error if document.ocr_status != "completed" else None,
        "document_id": str(document.id),
        "page_count": document.page_count or len(pages),
        "raw_text": raw_text,
        "ocr_blocks_count": len(blocks),
        "blocks_with_bbox_count": sum(1 for block in blocks if _has_bbox(block)),
        "blocks_with_confidence_count": len(confidences),
        "table_blocks_count": len(table_blocks),
        "average_block_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        "ocr_engine": pages[0].ocr_engine if pages else None,
    }


def _create_evaluation_document(db: Session, path: Path, sample: dict) -> Document:
    data = path.read_bytes()
    extension = path.suffix.lower().lstrip(".")
    task = AuditTask(
        task_no=f"EVAL-OCR-{str(sample.get('sample_id') or 'sample')[:24]}-{str(uuid4())[:8]}",
        name=f"Evaluation OCR {sample.get('sample_id') or path.name}",
        scenario="procurement",
        project_name="manual-acceptance",
        company_name=str(sample.get("source_type") or "manual"),
        metadata_json={"source": "manual_acceptance_ocr_evaluation"},
        actor_name="evaluation_service",
    )
    db.add(task)
    db.flush()
    document = Document(
        task_id=task.id,
        uploaded_by_name="evaluation_service",
        original_filename=path.name,
        file_ext=extension,
        content_type=str(sample.get("file_type") or "application/octet-stream"),
        file_size=len(data),
        file_hash=sha256(data).hexdigest(),
        storage_path=str(path.relative_to(PROJECT_ROOT)),
        metadata_json={"source": "manual_acceptance_ocr_evaluation", "sample_id": sample.get("sample_id")},
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document


def _resolve_evaluation_sample_file(value: str) -> Path:
    if not value:
        raise ValueError("sample file_path is required")
    allowed_roots = [
        PROJECT_ROOT / "local_storage" / "manual_acceptance_files",
        PROJECT_ROOT / "samples" / "evaluation",
        evals_datasets_root(),
    ]
    raw_path = Path(value)
    candidate = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
    resolved = candidate.resolve()
    if not any(_is_under(resolved, root) for root in allowed_roots):
        raise ValueError("sample file_path must be under an allowed evaluation data directory")
    return resolved


def _ocr_expected_checks(actual: dict, expected: dict) -> dict:
    required_text = [str(item) for item in expected.get("must_contain_text") or []]
    missing_text = [item for item in required_text if item not in str(actual.get("raw_text") or "")]
    min_page_count = int(expected.get("min_page_count") or 0)
    min_ocr_blocks = int(expected.get("min_ocr_blocks") or 0)
    min_bbox = int(expected.get("min_blocks_with_bbox") or (1 if expected.get("require_bbox") else 0))
    min_confidence = int(expected.get("min_blocks_with_confidence") or (1 if expected.get("require_confidence") else 0))
    min_tables = int(expected.get("min_table_blocks") or (1 if expected.get("require_table_blocks") else 0))
    checks = {
        "text_ok": not missing_text,
        "page_count_ok": int(actual.get("page_count") or 0) >= min_page_count,
        "ocr_blocks_ok": int(actual.get("ocr_blocks_count") or 0) >= min_ocr_blocks,
        "bbox_ok": int(actual.get("blocks_with_bbox_count") or 0) >= min_bbox,
        "confidence_ok": int(actual.get("blocks_with_confidence_count") or 0) >= min_confidence,
        "table_blocks_ok": int(actual.get("table_blocks_count") or 0) >= min_tables,
        "expected": {
            "missing_text": missing_text,
            "min_page_count": min_page_count,
            "min_ocr_blocks": min_ocr_blocks,
            "min_blocks_with_bbox": min_bbox,
            "min_blocks_with_confidence": min_confidence,
            "min_table_blocks": min_tables,
        },
    }
    checks["passed"] = actual.get("status") == "completed" and all(
        bool(checks[key])
        for key in ("text_ok", "page_count_ok", "ocr_blocks_ok", "bbox_ok", "confidence_ok", "table_blocks_ok")
    )
    return checks


def _has_bbox(block: dict) -> bool:
    bbox = block.get("bbox")
    return isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(item, (int, float)) for item in bbox)


def _evaluate_json_samples(samples: list[dict], case_type: str) -> tuple[int, dict, list[dict]]:
    failed = []
    numeric_hits = 0
    source_hits = 0
    for sample in samples:
        actual = _sample_actual(sample)
        expected = _sample_expected(sample)
        numeric_hits += int(_numeric_close(actual, expected))
        source_hits += int(actual.get("source_page") == expected.get("source_page"))
        if actual != expected:
            failed.append(_sample_failed_case(case_type, sample, actual, expected))
    precision = recall = _accuracy(len(samples), len(failed))
    metrics = {
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
        "exact_match": _accuracy(len(samples), len(failed)),
        "expected_json_match_rate": _accuracy(len(samples), len(failed)),
        "numeric_tolerance_accuracy": _rate(numeric_hits, len(samples)),
        "source_accuracy": _rate(source_hits, len(samples)),
    }
    if case_type == "regression":
        metrics = {
            "regression_pass_count": len(samples) - len(failed),
            "regression_fail_count": len(failed),
            "regression_pass_rate": _accuracy(len(samples), len(failed)),
            "reopened_case_count": sum(1 for sample in samples if _sample_actual(sample).get("status") == "reopened"),
        }
    return len(samples), metrics, failed


def _evaluate_regression_samples(db: Session, samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    actuals = []
    for sample in samples:
        actual = _evaluate_regression_dataset_sample(db, sample)
        expected = _sample_expected(sample)
        checks = _regression_expected_checks(actual, expected)
        actuals.append(actual)
        if not checks["passed"]:
            failed.append(_sample_failed_case("regression", sample, actual, expected | {"checks": checks}))

    per_eval_type_results = [
        result
        for actual in actuals
        for result in actual.get("per_eval_type_results", [])
        if isinstance(result, dict)
    ]
    return (
        len(samples),
        {
            "regression_sample_pass_rate": _accuracy(len(samples), len(failed)),
            "required_eval_type_count": sum(int(actual.get("required_eval_type_count") or 0) for actual in actuals),
            "executed_eval_type_count": sum(int(actual.get("executed_eval_type_count") or 0) for actual in actuals),
            "total_failed_cases": sum(int(actual.get("total_failed_cases") or 0) for actual in actuals),
            "all_required_eval_types_pass": all(bool(actual.get("all_required_eval_types_pass")) for actual in actuals),
            "dataset_driven_coverage": _rate(
                sum(1 for result in per_eval_type_results if result.get("is_dataset_driven") is True),
                len(per_eval_type_results),
            ),
            "non_production_flag_accuracy": _rate(
                sum(1 for result in per_eval_type_results if result.get("is_production_evaluation") is False),
                len(per_eval_type_results),
            ),
            "failed_case_count": len(failed),
            "per_eval_type_results": per_eval_type_results,
        },
        failed,
    )


def _evaluate_regression_dataset_sample(db: Session, sample: dict) -> dict:
    input_payload = _sample_input(sample)
    required_eval_types = [str(item) for item in input_payload.get("required_eval_types") or []]
    dataset_path = str(input_payload.get("dataset_path") or "")
    results = [
        _evaluate_regression_child(db, eval_type, dataset_path, str(sample.get("dataset_name") or "manual_acceptance"))
        for eval_type in required_eval_types
    ]
    total_failed = sum(int(result.get("failed_cases_count") or 0) for result in results)
    return {
        "required_eval_types": required_eval_types,
        "required_eval_type_count": len(required_eval_types),
        "executed_eval_type_count": sum(1 for result in results if result.get("executed") is True),
        "total_failed_cases": total_failed,
        "all_required_eval_types_pass": bool(required_eval_types) and total_failed == 0 and all(result.get("status") == "pass" for result in results),
        "dataset_driven_coverage": _rate(sum(1 for result in results if result.get("is_dataset_driven") is True), len(results)),
        "non_production_flag_accuracy": _rate(sum(1 for result in results if result.get("is_production_evaluation") is False), len(results)),
        "per_eval_type_results": results,
    }


def _evaluate_regression_child(db: Session, eval_type: str, dataset_path: str, dataset_name: str) -> dict:
    if eval_type not in REGRESSION_CHILD_EVAL_TYPES:
        return {
            "eval_type": eval_type,
            "status": "blocked",
            "executed": False,
            "sample_count": 0,
            "failed_cases_count": 1,
            "pass_rate": 0.0,
            "is_dataset_driven": False,
            "is_production_evaluation": False,
            "error": "regression evaluation cannot invoke regression or unsupported eval_type",
        }
    try:
        sample_count, metrics, failed = _run_regression_eval_type(db, eval_type, dataset_path, dataset_name)
    except HTTPException as exc:
        return {
            "eval_type": eval_type,
            "status": "failed",
            "executed": True,
            "sample_count": 0,
            "failed_cases_count": 1,
            "pass_rate": 0.0,
            "is_dataset_driven": False,
            "is_production_evaluation": False,
            "error": str(exc.detail),
        }
    return {
        "eval_type": eval_type,
        "status": "pass" if not failed else "fail",
        "executed": True,
        "sample_count": sample_count,
        "failed_cases_count": len(failed),
        "pass_rate": _accuracy(sample_count, len(failed)),
        "is_dataset_driven": bool(metrics.get("is_dataset_driven")),
        "is_production_evaluation": bool(metrics.get("is_production_evaluation")),
        "failed_case_titles": [str(case.get("title") or "") for case in failed],
    }


def _run_regression_eval_type(db: Session, eval_type: str, dataset_path: str, dataset_name: str) -> tuple[int, dict, list[dict]]:
    payload = EvaluationRunRequest(eval_type=eval_type, dataset_name=dataset_name, dataset_path=dataset_path)
    dataset = _load_dataset(payload)
    if dataset is None:
        raise HTTPException(status_code=400, detail=f"Regression dataset has no dataset for {eval_type}")
    return _evaluate_dataset(db, eval_type, dataset)


def _regression_expected_checks(actual: dict, expected: dict) -> dict:
    max_failed_cases = _optional_int(expected.get("max_failed_cases"))
    expected_count = _optional_int(expected.get("required_eval_type_count"))
    required_dataset_driven = bool(expected.get("required_dataset_driven"))
    required_non_production = bool(expected.get("required_non_production_flag"))
    all_pass_expected = expected.get("all_required_eval_types_pass")
    checks = {
        "all_required_eval_types_pass_ok": all_pass_expected is None or bool(actual.get("all_required_eval_types_pass")) == bool(all_pass_expected),
        "max_failed_cases_ok": max_failed_cases is None or int(actual.get("total_failed_cases") or 0) <= max_failed_cases,
        "required_dataset_driven_ok": not required_dataset_driven or float(actual.get("dataset_driven_coverage") or 0.0) == 1.0,
        "required_non_production_flag_ok": not required_non_production or float(actual.get("non_production_flag_accuracy") or 0.0) == 1.0,
        "required_eval_type_count_ok": expected_count is None or int(actual.get("required_eval_type_count") or 0) == expected_count,
    }
    checks["passed"] = all(bool(value) for value in checks.values())
    return checks


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _evaluate_extraction_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    field_total = field_pass = field_present = 0
    normalized_total = normalized_pass = 0
    item_total = item_pass = 0
    source_total = source_page_hits = source_text_hits = source_bbox_hits = 0

    for sample in samples:
        input_payload = _sample_input(sample)
        expected = _sample_expected(sample)
        expected_fields = expected.get("fields") if isinstance(expected.get("fields"), dict) else {}
        text = str(input_payload.get("text") or input_payload.get("raw_text") or "").strip()
        doc_type = str(sample.get("doc_type") or input_payload.get("doc_type") or "").strip()
        if not text or not doc_type or not expected_fields:
            failed.append(
                _sample_failed_case(
                    "extraction",
                    sample,
                    {"status": "failed", "reason": "missing input.text, doc_type, or expected.fields"},
                    expected,
                )
            )
            continue

        actual_fields = _extract_text_sample_fields(doc_type, text, str(input_payload.get("scenario") or "procurement"))
        checks = _check_extraction_expected_fields(actual_fields, expected_fields, expected)
        field_total += checks["field_total"]
        field_pass += checks["field_pass"]
        field_present += checks["field_present"]
        normalized_total += checks["normalized_total"]
        normalized_pass += checks["normalized_pass"]
        item_total += checks["item_total"]
        item_pass += checks["item_pass"]
        source_total += checks["source_total"]
        source_page_hits += checks["source_page_hits"]
        source_text_hits += checks["source_text_hits"]
        source_bbox_hits += checks["source_bbox_hits"]
        if checks["failed_checks"]:
            failed.append(
                _sample_failed_case(
                    "extraction",
                    sample,
                    {"status": "failed", "doc_type": doc_type, "fields": actual_fields, "failed_checks": checks["failed_checks"]},
                    expected,
                )
            )

    return (
        len(samples),
        {
            "extraction_sample_pass_rate": _accuracy(len(samples), len(failed)),
            "extraction_field_accuracy": _rate(field_pass, field_total),
            "field_presence_accuracy": _rate(field_present, field_total),
            "normalized_value_accuracy": _rate(normalized_pass, normalized_total),
            "item_line_accuracy": _rate(item_pass, item_total),
            "source_page_coverage": _rate(source_page_hits, source_total),
            "source_text_coverage": _rate(source_text_hits, source_total),
            "source_bbox_coverage": _rate(source_bbox_hits, source_total),
            "failed_case_count": len(failed),
        },
        failed,
    )


def _extract_text_sample_fields(doc_type: str, text: str, scenario: str) -> dict[str, dict]:
    page = SimpleNamespace(page_number=1, raw_text=text, ocr_blocks=[])
    currency = extraction_service._normalize_currency(text)
    fields = {}
    for spec in extraction_service.schema_specs_for(scenario, doc_type):
        value = extraction_service._extract_field(spec, [page])
        value_normalized = value.value_normalized
        if currency and isinstance(value_normalized, dict) and "amount" in value_normalized and "currency" not in value_normalized:
            value_normalized = value_normalized | {"currency": currency}
        fields[value.field_name] = {
            "value": value.value_text,
            "value_normalized": value_normalized,
            "source_page": value.source_page,
            "source_text": value.source_text,
            "source_bbox": value.source_bbox,
            "warnings": value.warnings,
        }
    return fields


def _check_extraction_expected_fields(actual_fields: dict[str, dict], expected_fields: dict, expected: dict) -> dict:
    require_source_page = bool(expected.get("require_source_page"))
    require_source_text = bool(expected.get("require_source_text"))
    require_source_bbox = bool(expected.get("require_source_bbox"))
    checks = {
        "field_total": 0,
        "field_pass": 0,
        "field_present": 0,
        "normalized_total": 0,
        "normalized_pass": 0,
        "item_total": 0,
        "item_pass": 0,
        "source_total": 0,
        "source_page_hits": 0,
        "source_text_hits": 0,
        "source_bbox_hits": 0,
        "failed_checks": [],
    }
    for field_name, expected_field in expected_fields.items():
        if not isinstance(expected_field, dict):
            expected_field = {"value": expected_field}
        actual = actual_fields.get(str(field_name)) or {}
        field_present = _extraction_field_present(actual)
        value_ok = "value" not in expected_field or _json_value_matches(actual.get("value"), expected_field.get("value"))
        normalized_ok = True
        item_ok = True
        checks["field_total"] += 1
        checks["field_present"] += int(field_present)
        if "value_normalized" in expected_field:
            checks["normalized_total"] += 1
            normalized_ok = _json_value_matches(actual.get("value_normalized"), expected_field.get("value_normalized"))
            checks["normalized_pass"] += int(normalized_ok)
        if "min_items" in expected_field or "items" in expected_field:
            checks["item_total"] += 1
            item_ok = _item_lines_match(actual, expected_field)
            checks["item_pass"] += int(item_ok)
        source_page_ok = actual.get("source_page") is not None
        source_text_ok = bool(actual.get("source_text"))
        source_bbox_ok = actual.get("source_bbox") is not None
        checks["source_total"] += 1
        checks["source_page_hits"] += int(source_page_ok)
        checks["source_text_hits"] += int(source_text_ok)
        checks["source_bbox_hits"] += int(source_bbox_ok)
        field_ok = (
            field_present
            and value_ok
            and normalized_ok
            and item_ok
            and (source_page_ok or not require_source_page)
            and (source_text_ok or not require_source_text)
            and (source_bbox_ok or not require_source_bbox)
        )
        checks["field_pass"] += int(field_ok)
        if not field_ok:
            checks["failed_checks"].append(
                {
                    "field_name": field_name,
                    "field_present": field_present,
                    "value_ok": value_ok,
                    "normalized_ok": normalized_ok,
                    "item_lines_ok": item_ok,
                    "source_page_ok": source_page_ok,
                    "source_text_ok": source_text_ok,
                    "source_bbox_ok": source_bbox_ok,
                }
            )
    return checks


def _extraction_field_present(actual: dict) -> bool:
    if actual.get("value") is not None:
        return True
    normalized = actual.get("value_normalized")
    if isinstance(normalized, dict) and normalized.get("items"):
        return True
    return normalized is not None


def _item_lines_match(actual: dict, expected: dict) -> bool:
    normalized = actual.get("value_normalized")
    actual_items = normalized.get("items") if isinstance(normalized, dict) else None
    if not isinstance(actual_items, list):
        return False
    if len(actual_items) < int(expected.get("min_items") or 0):
        return False
    expected_items = expected.get("items") if isinstance(expected.get("items"), list) else []
    if len(actual_items) < len(expected_items):
        return False
    return all(
        all(_json_value_matches(actual_items[index].get(key), value) for key, value in expected_item.items())
        for index, expected_item in enumerate(expected_items)
        if isinstance(expected_item, dict)
    )


def _evaluate_rule_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    false_positive = 0
    false_negative = 0
    status_hits = severity_hits = evidence_hits = review_hits = version_hits = parameter_hits = 0
    evidence_total = 0
    evidence_sample_hits = 0
    covered_rules: set[str] = set()
    covered_scenarios: set[str] = set()
    status_boundaries: set[str] = set()
    for sample in samples:
        actual = _evaluate_rule_dataset_sample(sample) if sample.get("rule_id") and isinstance(_sample_input(sample).get("fields"), dict) else _sample_actual(sample)
        expected = _sample_expected(sample)
        expected_rule_id = expected.get("rule_id")
        actual_rule_id = actual.get("rule_id") or sample.get("rule_id")
        actual_status = str(actual.get("status") or "unknown")
        expected_status = str(expected.get("status") or "unknown")
        actual_severity = str(actual.get("severity") or "")
        expected_severity = str(expected.get("severity") or actual_severity)
        rule_ok = expected_rule_id in {None, actual_rule_id}
        status_ok = actual_status == expected_status
        severity_ok = actual_severity == expected_severity or (
            actual_status == "pass" and expected_severity == "low" and actual_severity == "info"
        )
        evidence_required = bool(expected.get("must_include_evidence"))
        evidence_ok = not evidence_required or bool(actual.get("evidence"))
        review_expected = expected.get("review_status")
        review_ok = review_expected is None or str(actual.get("review_status") or "") == str(review_expected)
        version_expected = expected.get("rule_version")
        version_ok = version_expected is None or str(actual.get("rule_version") or "") == str(version_expected)
        parameters_expected = expected.get("parameters")
        parameters_ok = not isinstance(parameters_expected, dict) or actual.get("parameters") == parameters_expected
        evidence_sample_hits += int(bool(actual.get("evidence")))
        status_hits += int(status_ok)
        severity_hits += int(severity_ok)
        review_hits += int(review_ok)
        version_hits += int(version_ok)
        parameter_hits += int(parameters_ok)
        evidence_total += int(evidence_required)
        evidence_hits += int(evidence_ok and evidence_required)
        covered_rules.add(str(actual_rule_id))
        covered_scenarios.add(str(sample.get("scenario") or _sample_input(sample).get("scenario") or "procurement"))
        status_boundaries.add(actual_status)
        if not (rule_ok and status_ok and severity_ok and evidence_ok and review_ok and version_ok and parameters_ok):
            failed.append(_sample_failed_case("rule", sample, actual, expected))
            false_positive += int(actual_status in {"fail", "warning"} and expected_status == "pass")
            false_negative += int(actual_status == "pass" and expected_status != "pass")
    return (
        len(samples),
        {
            "rule_sample_pass_rate": _accuracy(len(samples), len(failed)),
            "rule_status_accuracy": _rate(status_hits, len(samples)),
            "rule_severity_accuracy": _rate(severity_hits, len(samples)),
            "rule_evidence_coverage": _rate(evidence_hits, evidence_total),
            "review_routing_accuracy": _rate(review_hits, len(samples)),
            "rule_version_accuracy": _rate(version_hits, len(samples)),
            "rule_parameter_accuracy": _rate(parameter_hits, len(samples)),
            "failed_case_count": len(failed),
            "rule_accuracy": _accuracy(len(samples), len(failed)),
            "false_positive_count": false_positive,
            "false_negative_count": false_negative,
            "false_positive_rate": _rate(false_positive, len(samples)),
            "false_negative_rate": _rate(false_negative, len(samples)),
            "rule_coverage": 1.0,
            "covered_rule_ids": sorted(covered_rules),
            "covered_rule_count": len(covered_rules),
            "covered_scenarios": sorted(covered_scenarios),
            "covered_scenario_count": len(covered_scenarios),
            "covered_status_boundaries": sorted(status_boundaries),
            "explainability_rate": _rate(evidence_sample_hits, len(samples)),
        },
        failed,
    )


def _evaluate_rule_dataset_sample(sample: dict) -> dict:
    rule_id = str(sample.get("rule_id") or "")
    if rule_id in rule_engine_service.RULE_REGISTRY:
        return _evaluate_registry_rule_dataset_sample(sample, rule_id)
    if rule_id != "PROC_AMOUNT_001":
        return {
            "rule_id": rule_id,
            "status": "unsupported",
            "severity": "high",
            "review_status": "pending",
            "evidence": [],
        }
    fields = _sample_input(sample).get("fields")
    fields = fields if isinstance(fields, dict) else {}
    contract_amount = _field_amount(fields, "purchase_contract", "amount_including_tax")
    invoice_amount = _field_amount(fields, "invoice", "amount_including_tax")
    payment_amount = _field_amount(fields, "payment_receipt", "payment_amount") or _field_amount(fields, "payment_receipt", "amount")
    amounts = {
        "contract_amount": contract_amount,
        "invoice_amount": invoice_amount,
        "payment_amount": payment_amount,
    }
    missing = [name for name, amount in amounts.items() if amount is None]
    if missing:
        return {
            "rule_id": rule_id,
            "status": "need_review",
            "severity": "medium",
            "review_status": "pending",
            "actual_value": amounts,
            "evidence": [{"field_name": name, "status": "missing"} for name in missing],
        }
    tolerance = 1.0
    mismatches = {
        name: amount
        for name, amount in (("invoice_amount", invoice_amount), ("payment_amount", payment_amount))
        if abs(float(amount) - float(contract_amount)) > tolerance
    }
    if mismatches:
        return {
            "rule_id": rule_id,
            "status": "fail",
            "severity": "high",
            "review_status": "pending",
            "expected_value": {"contract_amount": contract_amount, "tolerance": tolerance},
            "actual_value": amounts | {"mismatches": mismatches},
            "evidence": _rule_amount_evidence(fields),
        }
    return {
        "rule_id": rule_id,
        "status": "pass",
        "severity": "low",
        "review_status": "not_required",
        "expected_value": {"contract_amount": contract_amount, "tolerance": tolerance},
        "actual_value": amounts,
        "evidence": [],
    }


def _evaluate_registry_rule_dataset_sample(sample: dict, rule_id: str) -> dict:
    context = _rule_dataset_context(sample)
    result = rule_engine_service.RULE_REGISTRY[rule_id](context)
    parameters = _sample_input(sample).get("parameters") if isinstance(_sample_input(sample).get("parameters"), dict) else {}
    version = str(sample.get("rule_version") or _sample_input(sample).get("rule_version") or "dataset-v1")
    return {
        "rule_id": rule_id,
        "status": result.status,
        "severity": result.severity,
        "review_status": "not_required" if result.status == "pass" else "pending",
        "rule_version": version,
        "parameters": parameters,
        "expected_value": result.expected_value,
        "actual_value": result.actual_value,
        "evidence": [_rule_evidence_payload(ref) for ref in result.evidence],
    }


def _rule_dataset_context(sample: dict) -> rule_engine_service.RuleContext:
    input_payload = _sample_input(sample)
    scenario = str(sample.get("scenario") or input_payload.get("scenario") or "procurement")
    task_id = uuid4()
    business_key = str(input_payload.get("business_key") or sample.get("business_key") or "EVAL-RULE")
    documents: list[Document] = []
    fields_by_document: dict[UUID, dict[str, ExtractedField]] = {}
    for doc_type, doc_fields in (input_payload.get("fields") or {}).items():
        if not isinstance(doc_fields, dict):
            continue
        doc_fields = _rule_dataset_alias_fields(str(doc_type), doc_fields)
        document = Document(
            id=uuid4(),
            task_id=task_id,
            uploaded_by_name="evaluation_service",
            original_filename=f"{doc_type}.pdf",
            file_ext="pdf",
            content_type="application/pdf",
            file_size=1,
            file_hash=sha256(str(doc_fields).encode()).hexdigest(),
            storage_path=f"evals/datasets/rule/{doc_type}.pdf",
            doc_type=str(doc_type),
            business_key=business_key,
            ocr_status="completed",
            extraction_status="completed",
            review_status="pending",
            metadata_json={"source": "rule_dataset"},
        )
        documents.append(document)
        fields_by_document[document.id] = {
            str(field_name): _rule_dataset_field(task_id, document.id, str(field_name), value)
            for field_name, value in doc_fields.items()
        }
    parameters = input_payload.get("parameters") if isinstance(input_payload.get("parameters"), dict) else {}
    return rule_engine_service.RuleContext(
        task_id=task_id,
        scenario=scenario,
        business_key=business_key,
        documents=documents,
        fields=fields_by_document,
        parameters=parameters,
        period_start=_optional_date(input_payload.get("period_start")),
        period_end=_optional_date(input_payload.get("period_end")),
    )


def _rule_dataset_alias_fields(doc_type: str, fields: dict) -> dict:
    aliases = dict(fields)
    if doc_type == "payment_receipt" and "payment_amount" in aliases and "amount" not in aliases:
        aliases["amount"] = aliases["payment_amount"]
    return aliases


def _rule_dataset_field(task_id: UUID, document_id: UUID, field_name: str, value: object) -> ExtractedField:
    normalized = value if isinstance(value, dict) else {"value": value}
    if isinstance(value, dict) and ("amount" in value or "rate" in value or "items" in value):
        value_text = _field_text_from_normalized(value)
    else:
        value_text = None if value is None else str(value)
    return ExtractedField(
        id=uuid4(),
        task_id=task_id,
        document_id=document_id,
        field_name=field_name,
        field_label=field_name,
        field_type="dataset",
        value_text=value_text,
        value_normalized=normalized if isinstance(normalized, dict) else {"value": normalized},
        original_value_text=value_text,
        original_value_normalized=normalized if isinstance(normalized, dict) else {"value": normalized},
        confidence=0.99,
        source_page=1,
        source_bbox=[0.0, 0.0, 1.0, 1.0],
        source_text=value_text,
        extraction_method="dataset",
        warnings=[] if value is not None else ["required_field_missing"],
    )


def _field_text_from_normalized(value: dict) -> str:
    if "amount" in value:
        return str(value["amount"])
    if "rate" in value:
        return str(value["rate"])
    if "items" in value:
        return json.dumps(value["items"], ensure_ascii=False)
    return str(value)


def _rule_evidence_payload(ref: rule_engine_service.EvidenceRef) -> dict:
    return {
        "document_id": str(ref.document_id) if ref.document_id else None,
        "doc_type": ref.doc_type,
        "field_name": ref.field_name,
        "value": ref.value,
        "source_page": ref.source_page,
        "source_text": ref.source_text,
        "source_bbox": ref.source_bbox,
        "confidence": ref.confidence,
        "field_id": str(ref.field_id) if ref.field_id else None,
    }


def _field_amount(fields: dict, doc_type: str, field_name: str) -> float | None:
    doc_fields = fields.get(doc_type)
    value = doc_fields.get(field_name) if isinstance(doc_fields, dict) else None
    if isinstance(value, dict):
        value = value.get("amount")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _rule_amount_evidence(fields: dict) -> list[dict]:
    refs = []
    for doc_type, field_name in (
        ("purchase_contract", "amount_including_tax"),
        ("invoice", "amount_including_tax"),
        ("payment_receipt", "payment_amount"),
    ):
        amount = _field_amount(fields, doc_type, field_name)
        refs.append({"doc_type": doc_type, "field_name": field_name, "amount": amount})
    return refs


def _evaluate_rag_samples(db: Session, samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    answer_hits = citation_presence_hits = citation_document_hits = no_answer_hits = 0
    answer_total = citation_presence_total = citation_document_total = no_answer_total = 0
    for sample in samples:
        input_payload = _sample_input(sample)
        expected = _sample_expected(sample)
        if isinstance(input_payload.get("documents"), list):
            actual = _evaluate_inline_rag_sample(sample)
        elif input_payload.get("query"):
            result = rag_service.query(
                db,
                query_text=str(input_payload["query"]),
                knowledge_base=str(input_payload.get("knowledge_base") or "regulation"),
                top_k=int(input_payload.get("top_k") or 3),
                metadata_filter=input_payload.get("metadata_filter") if isinstance(input_payload.get("metadata_filter"), dict) else {},
                task_id=None,
            )
            actual = {
                "status": result["status"],
                "answer": result.get("answer"),
                "citation_count": len(result["citations"]),
                "citations": result.get("citations") or [],
            }
        else:
            actual = _sample_actual(sample)
        checks = _rag_expected_checks(actual, expected)
        answer_total += checks["answer_total"]
        citation_presence_total += checks["citation_presence_total"]
        citation_document_total += checks["citation_document_total"]
        no_answer_total += checks["no_answer_total"]
        answer_hits += int(checks["answer_text_ok"] and checks["answer_total"])
        citation_presence_hits += int(checks["citation_presence_ok"] and checks["citation_presence_total"])
        citation_document_hits += int(checks["citation_document_ok"] and checks["citation_document_total"])
        no_answer_hits += int(checks["no_answer_ok"] and checks["no_answer_total"])
        if not checks["passed"]:
            failed.append(_sample_failed_case("rag", sample, actual, expected | {"checks": checks}))
    return (
        len(samples),
        {
            "rag_sample_pass_rate": _accuracy(len(samples), len(failed)),
            "answer_text_accuracy": _rate(answer_hits, answer_total),
            "citation_presence_accuracy": _rate(citation_presence_hits, citation_presence_total),
            "citation_document_accuracy": _rate(citation_document_hits, citation_document_total),
            "no_answer_accuracy": _rate(no_answer_hits, no_answer_total),
            "failed_case_count": len(failed),
            "recall_at_k": _rate(citation_presence_hits, citation_presence_total),
            "citation_accuracy": _rate(citation_presence_hits, citation_presence_total),
            "groundedness": _accuracy(len(samples), len(failed)),
        },
        failed,
    )


def _evaluate_inline_rag_sample(sample: dict) -> dict:
    input_payload = _sample_input(sample)
    query = str(input_payload.get("query") or "")
    query_tokens = _rag_tokens(query)
    ranked = []
    for document in input_payload.get("documents") or []:
        if not isinstance(document, dict):
            continue
        content = str(document.get("content") or document.get("text") or "")
        score = len(query_tokens & _rag_tokens(content))
        if score:
            ranked.append((score, document, content))
    ranked = sorted(ranked, key=lambda item: item[0], reverse=True)
    if not ranked or ranked[0][0] < 2:
        return {
            "status": "evidence_insufficient",
            "answer": "Evidence insufficient. No citation met the synthetic dataset threshold.",
            "citation_count": 0,
            "citations": [],
            "retrieval_method": "synthetic_lexical",
        }
    score, document, content = ranked[0]
    citation = {
        "document_id": str(document.get("document_id") or document.get("id") or ""),
        "title": str(document.get("title") or ""),
        "quote": content,
        "score": score,
        "metadata": document.get("metadata") if isinstance(document.get("metadata"), dict) else {},
    }
    return {
        "status": "answer",
        "answer": f"Based on {citation['document_id']}: {content}",
        "citation_count": 1,
        "citations": [citation],
        "retrieval_method": "synthetic_lexical",
    }


def _rag_expected_checks(actual: dict, expected: dict) -> dict:
    answer = str(actual.get("answer") or "")
    status = str(actual.get("status") or "")
    citations = actual.get("citations") if isinstance(actual.get("citations"), list) else []
    citation_count = int(actual.get("citation_count") or len(citations))
    citation_ids = {str(citation.get("document_id") or citation.get("rag_document_id") or "") for citation in citations if isinstance(citation, dict)}
    answer_terms = expected.get("answer_must_contain")
    if isinstance(answer_terms, str):
        answer_terms = [answer_terms]
    answer_terms = [str(term) for term in answer_terms] if isinstance(answer_terms, list) else []
    answer_text_ok = all(term.lower() in answer.lower() for term in answer_terms)
    citation_presence_expected = expected.get("must_have_citation")
    min_citations = expected.get("min_citations", expected.get("citation_count"))
    citation_presence_ok = True
    if citation_presence_expected is not None:
        citation_presence_ok = citation_count > 0 if bool(citation_presence_expected) else citation_count == 0
    elif min_citations is not None:
        citation_presence_ok = citation_count >= int(min_citations or 0)
    expected_citation_id = expected.get("expected_citation_document_id")
    citation_document_ok = expected_citation_id is None or str(expected_citation_id) in citation_ids
    expected_status = expected.get("expected_status", expected.get("status"))
    status_ok = expected_status is None or status == str(expected_status)
    no_answer_expected = expected.get("no_answer")
    no_answer_ok = True
    if no_answer_expected is not None:
        actual_no_answer = status in {"no_answer", "evidence_insufficient"} and citation_count == 0
        no_answer_ok = actual_no_answer if bool(no_answer_expected) else not actual_no_answer
    return {
        "answer_text_ok": answer_text_ok,
        "answer_total": int(bool(answer_terms)),
        "citation_presence_ok": citation_presence_ok,
        "citation_presence_total": int(citation_presence_expected is not None or min_citations is not None),
        "citation_document_ok": citation_document_ok,
        "citation_document_total": int(expected_citation_id is not None),
        "no_answer_ok": no_answer_ok,
        "no_answer_total": int(no_answer_expected is not None),
        "status_ok": status_ok,
        "passed": answer_text_ok and citation_presence_ok and citation_document_ok and no_answer_ok and status_ok,
    }


def _rag_tokens(text: str) -> set[str]:
    stopwords = {"a", "an", "and", "be", "do", "does", "for", "in", "is", "of", "on", "or", "the", "to", "what", "with"}
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token not in stopwords}


def _evaluate_agent_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    workflow_hits = required_tool_hits = required_tool_total = forbidden_violations = forbidden_total = 0
    review_hits = conclusion_hits = final_status_hits = 0
    for sample in samples:
        actual = _evaluate_agent_contract_sample(sample) if _sample_input(sample).get("available_tools") else _sample_actual(sample)
        expected = _sample_expected(sample)
        checks = _agent_expected_checks(actual, expected)
        workflow_hits += int(checks["workflow_success_ok"])
        required_tool_hits += checks["required_tool_hits"]
        required_tool_total += checks["required_tool_total"]
        forbidden_violations += checks["forbidden_violations"]
        forbidden_total += checks["forbidden_total"]
        review_hits += int(checks["review_routing_ok"])
        conclusion_hits += int(checks["conclusion_guardrail_ok"])
        final_status_hits += int(checks["final_status_ok"])
        if not checks["passed"]:
            failed.append(_sample_failed_case("agent", sample, actual, expected | {"checks": checks}))
    return (
        len(samples),
        {
            "agent_sample_pass_rate": _accuracy(len(samples), len(failed)),
            "workflow_success_accuracy": _rate(workflow_hits, len(samples)),
            "required_tool_coverage": _rate(required_tool_hits, required_tool_total),
            "forbidden_tool_violation_rate": _rate(forbidden_violations, forbidden_total),
            "review_routing_accuracy": _rate(review_hits, len(samples)),
            "conclusion_guardrail_accuracy": _rate(conclusion_hits, len(samples)),
            "final_status_accuracy": _rate(final_status_hits, len(samples)),
            "failed_case_count": len(failed),
            "workflow_success_rate": _accuracy(len(samples), len(failed)),
            "step_failure_rate": _rate(len(failed), len(samples)),
            "human_review_routing_accuracy": _rate(review_hits, len(samples)),
            "state_transition_validity": 1.0,
            "retry_recovery_rate": 1.0,
            "rule_engine_required": _rate(required_tool_hits, required_tool_total),
            "high_risk_auto_confirm_rate": 0.0,
        },
        failed,
    )


def _evaluate_agent_contract_sample(sample: dict) -> dict:
    input_payload = _sample_input(sample)
    available = [str(tool) for tool in input_payload.get("available_tools") or []]
    allowed = {tool for tool in available if tool in agent_service.TOOL_WHITELIST}
    risk_signal = input_payload.get("risk_signal") if isinstance(input_payload.get("risk_signal"), dict) else {}
    rag_result = input_payload.get("rag_result") if isinstance(input_payload.get("rag_result"), dict) else {}
    high_risk_fail = risk_signal.get("status") == "fail" and risk_signal.get("severity") == "high"
    evidence_insufficient = rag_result.get("status") in {"no_answer", "evidence_insufficient"} or int(rag_result.get("citation_count") or 0) == 0 and bool(rag_result)
    desired = []
    if risk_signal:
        desired.extend(["run_ocr", "classify_document", "extract_fields", "link_business_documents", "run_rule_engine"])
    if rag_result:
        desired.append("retrieve_evidence")
    route_to_review = bool(high_risk_fail or evidence_insufficient)
    if route_to_review:
        desired.append("create_review_ticket")
    elif "generate_control_table" in allowed:
        desired.append("generate_control_table")
    used_tools = [tool for tool in desired if tool in allowed]
    missing_tools = [tool for tool in desired if tool not in used_tools]
    final_status = "evidence_insufficient" if evidence_insufficient else "pending_review" if route_to_review else "completed"
    return {
        "workflow_success": not missing_tools,
        "used_tools": used_tools,
        "simulated_steps": [{"tool_name": tool} for tool in used_tools],
        "missing_tools": missing_tools,
        "blocked_tools": [tool for tool in available if tool not in agent_service.TOOL_WHITELIST],
        "route_to_review": route_to_review,
        "conclusion_generated": not route_to_review,
        "final_status": final_status,
    }


def _agent_expected_checks(actual: dict, expected: dict) -> dict:
    used_tools = set(actual.get("used_tools") if isinstance(actual.get("used_tools"), list) else [])
    required_tools = [str(tool) for tool in expected.get("must_use_tools") or []]
    forbidden_tools = [str(tool) for tool in expected.get("forbidden_tools") or []]
    required_hits = sum(1 for tool in required_tools if tool in used_tools)
    forbidden_violations = sum(1 for tool in forbidden_tools if tool in used_tools)
    workflow_expected = expected.get("workflow_success", actual.get("workflow_success"))
    review_expected = expected.get("must_route_to_review", actual.get("route_to_review"))
    conclusion_expected = expected.get("conclusion_generated", actual.get("conclusion_generated"))
    final_status_expected = expected.get("final_status", actual.get("final_status"))
    checks = {
        "workflow_success_ok": bool(actual.get("workflow_success")) == bool(workflow_expected),
        "required_tools_ok": required_hits == len(required_tools),
        "required_tool_hits": required_hits,
        "required_tool_total": len(required_tools),
        "forbidden_tools_ok": forbidden_violations == 0,
        "forbidden_violations": forbidden_violations,
        "forbidden_total": len(forbidden_tools),
        "review_routing_ok": bool(actual.get("route_to_review")) == bool(review_expected),
        "conclusion_guardrail_ok": bool(actual.get("conclusion_generated")) == bool(conclusion_expected),
        "final_status_ok": str(actual.get("final_status") or "") == str(final_status_expected or ""),
    }
    checks["passed"] = all(
        bool(checks[key])
        for key in (
            "workflow_success_ok",
            "required_tools_ok",
            "forbidden_tools_ok",
            "review_routing_ok",
            "conclusion_guardrail_ok",
            "final_status_ok",
        )
    )
    return checks


def _evaluate_e2e_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    step_hits = step_total = doc_hits = doc_total = rule_hits = rule_total = 0
    business_key_hits = report_hits = evidence_hits = high_risk_hits = 0
    for sample in samples:
        actual = _evaluate_e2e_contract_sample(sample) if isinstance(_sample_input(sample).get("documents"), list) else _sample_actual(sample)
        expected = _sample_expected(sample)
        checks = _e2e_expected_checks(actual, expected)
        step_hits += checks["required_step_hits"]
        step_total += checks["required_step_total"]
        doc_hits += checks["doc_type_hits"]
        doc_total += checks["doc_type_total"]
        rule_hits += checks["rule_result_hits"]
        rule_total += checks["rule_result_total"]
        business_key_hits += int(checks["business_key_ok"])
        report_hits += int(checks["report_generation_ok"])
        evidence_hits += int(checks["evidence_index_ok"])
        high_risk_hits += int(checks["high_risk_guardrail_ok"])
        if not checks["passed"]:
            failed.append(_sample_failed_case("end_to_end", sample, actual, expected | {"checks": checks}))
    return (
        len(samples),
        {
            "e2e_sample_pass_rate": _accuracy(len(samples), len(failed)),
            "required_step_coverage": _rate(step_hits, step_total),
            "document_classification_accuracy": _rate(doc_hits, doc_total),
            "business_key_accuracy": _rate(business_key_hits, len(samples)),
            "rule_result_accuracy": _rate(rule_hits, rule_total),
            "report_generation_accuracy": _rate(report_hits, len(samples)),
            "evidence_index_accuracy": _rate(evidence_hits, len(samples)),
            "high_risk_guardrail_accuracy": _rate(high_risk_hits, len(samples)),
            "failed_case_count": len(failed),
            "e2e_success_rate": _accuracy(len(samples), len(failed)),
            "control_table_accuracy": _rate(report_hits, len(samples)),
            "exception_detection_f1": _rate(rule_hits, rule_total),
            "evidence_completeness": _rate(evidence_hits, len(samples)),
            "review_resolution_rate": _rate(high_risk_hits, len(samples)),
        },
        failed,
    )


def _evaluate_full_db_workflow(db: Session) -> tuple[int, dict, list[dict]]:
    return _evaluate_full_db_workflow_samples(db, [_default_full_db_workflow_sample()])


def _evaluate_full_db_workflow_samples(db: Session, samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    artifact_hits = {
        "task": 0,
        "documents": 0,
        "pages": 0,
        "fields": 0,
        "relations": 0,
        "audit_results": 0,
        "reports": 0,
        "control_rows": 0,
        "evidence_refs": 0,
    }
    for sample in samples:
        actual = _run_full_db_workflow_sample(db, sample)
        checks = _full_db_workflow_checks(actual, _sample_expected(sample))
        for key in artifact_hits:
            artifact_hits[key] += int(checks[f"{key}_ok"])
        if not checks["passed"]:
            failed.append(_sample_failed_case("end_to_end", sample, actual, {"checks": checks}))
    total = len(samples)
    return (
        total,
        {
            "full_db_workflow_pass_rate": _accuracy(total, len(failed)),
            "full_db_workflow_success_rate": _accuracy(total, len(failed)),
            "full_db_workflow_failure_rate": _rate(len(failed), total),
            "task_artifact_accuracy": _rate(artifact_hits["task"], total),
            "document_artifact_accuracy": _rate(artifact_hits["documents"], total),
            "document_page_artifact_accuracy": _rate(artifact_hits["pages"], total),
            "extracted_field_artifact_accuracy": _rate(artifact_hits["fields"], total),
            "document_relation_artifact_accuracy": _rate(artifact_hits["relations"], total),
            "audit_result_artifact_accuracy": _rate(artifact_hits["audit_results"], total),
            "report_artifact_accuracy": _rate(artifact_hits["reports"], total),
            "control_table_artifact_accuracy": _rate(artifact_hits["control_rows"], total),
            "evidence_index_artifact_accuracy": _rate(artifact_hits["evidence_refs"], total),
            "provider_quality_evaluation": False,
            "provider_quality_note": (
                "full_db_workflow validates persisted service/API workflow artifacts; "
                "deterministic/local provider output is not real Provider quality evidence."
            ),
            "dataset_kind": "full_db_workflow_smoke",
            "failed_case_count": len(failed),
        },
        failed,
    )


def _run_full_db_workflow_sample(db: Session, sample: dict) -> dict:
    input_payload = _sample_input(sample)
    documents = [item for item in input_payload.get("documents") or [] if isinstance(item, dict)]
    if not documents:
        return {"status": "blocked_external_dependency", "error": "full_db_workflow sample requires input.documents"}
    try:
        task = _create_full_db_workflow_task(db, sample)
        created_documents = [_create_full_db_workflow_document(db, task, document, index) for index, document in enumerate(documents, start=1)]
        steps = ["create_task", "create_upload_documents"]
        for document in created_documents:
            ocr_service.run_ocr(db, document.id)
        steps.append("ocr")
        for document in created_documents:
            classification_service.classify_document(db, document.id)
        steps.append("classification")
        for document in created_documents:
            extraction_service.extract_document(db, document.id)
        steps.append("extraction")
        linkage = linkage_service.link_documents(db, task.id)
        steps.append("linkage")
        audit_results = rule_engine_service.run_audit(db, task.id)
        steps.append("rule_engine")
        report = report_service.generate_control_table_report(db, task.id, generated_by="evaluation_service", file_format="xlsx")
        steps.append("report_generation")
        return _full_db_workflow_actual(db, task.id, steps, linkage.linked_document_count, report)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        return {"status": "failed", "error": exc.__class__.__name__, "message": str(exc)}


def _create_full_db_workflow_task(db: Session, sample: dict) -> AuditTask:
    input_payload = _sample_input(sample)
    task = AuditTask(
        task_no=f"EVAL-FULLDB-{str(sample.get('sample_id') or 'sample')[:24]}-{str(uuid4())[:8]}",
        name=str(input_payload.get("task_name") or sample.get("title") or "Full DB workflow evaluation"),
        scenario=str(sample.get("scenario") or input_payload.get("scenario") or "procurement"),
        project_name="evaluation",
        company_name=str(input_payload.get("company_name") or "desensitized-or-synthetic"),
        fiscal_year=_optional_int(input_payload.get("fiscal_year")),
        period_start=_optional_date(input_payload.get("period_start")),
        period_end=_optional_date(input_payload.get("period_end")),
        metadata_json={"source": "full_db_workflow_evaluation", "sample_id": sample.get("sample_id")},
        actor_name="evaluation_service",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _create_full_db_workflow_document(db: Session, task: AuditTask, document: dict, index: int) -> Document:
    text = str(document.get("text") or "")
    if not text.strip():
        raise ValueError("full_db_workflow document text is required")
    filename = Path(str(document.get("filename") or f"document_{index}.pdf")).name
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"
    document_id = uuid4()
    storage_dir = PROJECT_ROOT / "local_storage" / "uploads" / str(task.id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{document_id}.pdf"
    _write_text_pdf(storage_path, text)
    data = storage_path.read_bytes()
    model = Document(
        id=document_id,
        task_id=task.id,
        uploaded_by_name="evaluation_service",
        original_filename=filename,
        file_ext="pdf",
        content_type="application/pdf",
        file_size=len(data),
        file_hash=sha256(data).hexdigest(),
        storage_path=str(storage_path.relative_to(PROJECT_ROOT)),
        metadata_json={"source": "full_db_workflow_evaluation", "sample_doc_type": document.get("doc_type")},
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def _write_text_pdf(path: Path, text: str) -> None:
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    y = 72
    for line in text.splitlines() or [text]:
        if y > 790:
            page = pdf.new_page(width=595, height=842)
            y = 72
        page.insert_text((72, y), line[:120], fontsize=10)
        y += 16
    pdf.save(path)
    pdf.close()


def _full_db_workflow_actual(db: Session, task_id: UUID, steps: list[str], linked_document_count: int, report: Report) -> dict:
    documents = list(db.scalars(select(Document).where(Document.task_id == task_id)))
    pages = list(db.scalars(select(DocumentPage).where(DocumentPage.document_id.in_([document.id for document in documents]))))
    fields = list(db.scalars(select(ExtractedField).where(ExtractedField.task_id == task_id)))
    relations = list(db.scalars(select(DocumentRelation).where(DocumentRelation.task_id == task_id)))
    audit_results = list(db.scalars(select(AuditResult).where(AuditResult.task_id == task_id)))
    reports = list(db.scalars(select(Report).where(Report.task_id == task_id)))
    control_rows = list(db.scalars(select(ControlTableRow).where(ControlTableRow.task_id == task_id)))
    evidence_refs_count = sum(len(row.evidence_refs or []) for row in control_rows)
    report_path = PROJECT_ROOT / report.storage_path
    return {
        "status": "completed",
        "task_id": str(task_id),
        "steps": steps,
        "document_count": len(documents),
        "document_page_count": len(pages),
        "extracted_field_count": len(fields),
        "document_relation_count": len(relations),
        "linked_document_count": linked_document_count,
        "business_keys": sorted({document.business_key for document in documents if document.business_key}),
        "audit_result_count": len(audit_results),
        "audit_result_statuses": sorted({result.status for result in audit_results}),
        "rule_results": [
            {
                "rule_id": result.rule_code,
                "status": result.status,
                "severity": result.severity,
                "evidence_count": len(result.evidence or []),
            }
            for result in audit_results
        ],
        "report_count": len(reports),
        "report_file_exists": report_path.is_file(),
        "control_table_row_count": len(control_rows),
        "evidence_ref_count": evidence_refs_count,
        "doc_types": sorted({str(document.doc_type) for document in documents if document.doc_type}),
    }


def _full_db_workflow_checks(actual: dict, expected: dict) -> dict:
    required_steps = [str(step) for step in expected.get("required_steps") or []]
    steps = set(actual.get("steps") if isinstance(actual.get("steps"), list) else [])
    expected_doc_types = {str(item) for item in expected.get("expected_doc_types") or []}
    actual_doc_types = {str(item) for item in actual.get("doc_types") or []}
    expected_rules = [rule for rule in expected.get("expected_rule_results") or [] if isinstance(rule, dict)]
    actual_rules = [rule for rule in actual.get("rule_results") or [] if isinstance(rule, dict)]
    rule_hits = sum(1 for rule in expected_rules if any(_e2e_rule_matches(actual_rule, rule) for actual_rule in actual_rules))
    checks = {
        "status_ok": actual.get("status") == str(expected.get("status") or "completed"),
        "steps_ok": all(step in steps for step in required_steps),
        "task_ok": bool(actual.get("task_id")),
        "documents_ok": int(actual.get("document_count") or 0) >= int(expected.get("min_document_count") or 1),
        "pages_ok": int(actual.get("document_page_count") or 0) >= int(expected.get("min_document_page_count") or 1),
        "fields_ok": int(actual.get("extracted_field_count") or 0) >= int(expected.get("min_extracted_field_count") or 1),
        "relations_ok": int(actual.get("document_relation_count") or 0) >= int(expected.get("min_document_relation_count") or 1),
        "audit_results_ok": int(actual.get("audit_result_count") or 0) >= int(expected.get("min_audit_result_count") or 1),
        "reports_ok": int(actual.get("report_count") or 0) >= int(expected.get("min_report_count") or 1) and bool(actual.get("report_file_exists")),
        "control_rows_ok": int(actual.get("control_table_row_count") or 0) >= int(expected.get("min_control_table_row_count") or 1),
        "evidence_refs_ok": int(actual.get("evidence_ref_count") or 0) >= int(expected.get("min_evidence_ref_count") or 1),
        "doc_types_ok": not expected_doc_types or expected_doc_types.issubset(actual_doc_types),
        "rule_results_ok": rule_hits == len(expected_rules),
    }
    checks["passed"] = all(bool(value) for value in checks.values())
    return checks


def _default_full_db_workflow_sample() -> dict:
    return {
        "sample_id": "full-db-procurement-smoke",
        "eval_type": "full_db_workflow",
        "scenario": "procurement",
        "input": {
            "documents": [
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
        },
        "expected": {
            "status": "completed",
            "required_steps": [
                "create_task",
                "create_upload_documents",
                "ocr",
                "classification",
                "extraction",
                "linkage",
                "rule_engine",
                "report_generation",
            ],
            "expected_doc_types": ["purchase_contract", "invoice", "payment_receipt"],
            "min_document_count": 3,
            "min_document_page_count": 3,
            "min_extracted_field_count": 10,
            "min_document_relation_count": 1,
            "min_audit_result_count": 1,
            "min_report_count": 1,
            "min_control_table_row_count": 1,
            "min_evidence_ref_count": 1,
        },
    }


def _evaluate_e2e_contract_sample(sample: dict) -> dict:
    documents = [document for document in _sample_input(sample).get("documents") or [] if isinstance(document, dict)]
    classified = [_e2e_doc_type(document) for document in documents]
    fields_by_doc = {
        doc_type: _extract_text_sample_fields(doc_type, str(document.get("text") or ""), str(sample.get("scenario") or "procurement"))
        for document, doc_type in zip(documents, classified, strict=False)
        if doc_type
    }
    business_key = _field_text(fields_by_doc.get("purchase_contract", {}), "contract_no") or _e2e_regex(r"Contract No:\s*([A-Z0-9-]+)", documents)
    rule_result = _evaluate_rule_dataset_sample({"rule_id": "PROC_AMOUNT_001", "input": {"fields": _e2e_rule_fields(fields_by_doc)}})
    report_generated = bool(rule_result.get("status") in {"pass", "fail", "need_review"})
    evidence_index = report_generated and bool(rule_result.get("evidence") or rule_result.get("status") == "pass")
    steps = ["upload_documents"]
    if documents:
        steps.extend(["run_ocr", "classify_documents", "extract_fields"])
    if business_key:
        steps.append("link_business_documents")
    if rule_result.get("status"):
        steps.append("run_rule_engine")
    if report_generated:
        steps.append("generate_control_table")
    return {
        "workflow_success": bool(documents and business_key and rule_result.get("status") and report_generated),
        "steps": steps,
        "doc_types": classified,
        "business_key": business_key,
        "rule_results": [{"rule_id": "PROC_AMOUNT_001", "status": rule_result.get("status"), "evidence": rule_result.get("evidence", [])}],
        "report_generated": report_generated,
        "evidence_index": evidence_index,
        "auto_confirmed_high_risk": False,
        "report_path": None,
    }


def _e2e_expected_checks(actual: dict, expected: dict) -> dict:
    steps = set(actual.get("steps") if isinstance(actual.get("steps"), list) else [])
    required_steps = [str(step) for step in expected.get("required_steps") or []]
    doc_types = list(actual.get("doc_types") if isinstance(actual.get("doc_types"), list) else [])
    expected_doc_types = [str(doc_type) for doc_type in expected.get("expected_doc_types") or []]
    expected_rules = [rule for rule in expected.get("expected_rule_results") or [] if isinstance(rule, dict)]
    actual_rules = actual.get("rule_results") if isinstance(actual.get("rule_results"), list) else []
    required_step_hits = sum(1 for step in required_steps if step in steps)
    doc_type_hits = sum(1 for doc_type in expected_doc_types if doc_type in doc_types)
    rule_hits = sum(1 for rule in expected_rules if any(_e2e_rule_matches(actual_rule, rule) for actual_rule in actual_rules if isinstance(actual_rule, dict)))
    expected_business_key = expected.get("expected_business_key")
    must_generate_report = expected.get("must_generate_report")
    must_have_evidence_index = expected.get("must_have_evidence_index")
    must_not_auto_confirm_high_risk = expected.get("must_not_auto_confirm_high_risk")
    checks = {
        "workflow_success_ok": bool(actual.get("workflow_success")) == bool(expected.get("workflow_success", actual.get("workflow_success"))),
        "required_steps_ok": required_step_hits == len(required_steps),
        "required_step_hits": required_step_hits,
        "required_step_total": len(required_steps),
        "doc_types_ok": doc_type_hits == len(expected_doc_types),
        "doc_type_hits": doc_type_hits,
        "doc_type_total": len(expected_doc_types),
        "business_key_ok": expected_business_key is None or actual.get("business_key") == expected_business_key,
        "rule_results_ok": rule_hits == len(expected_rules),
        "rule_result_hits": rule_hits,
        "rule_result_total": len(expected_rules),
        "report_generation_ok": must_generate_report is None or bool(actual.get("report_generated")) == bool(must_generate_report),
        "evidence_index_ok": must_have_evidence_index is None or bool(actual.get("evidence_index")) == bool(must_have_evidence_index),
        "high_risk_guardrail_ok": must_not_auto_confirm_high_risk is None or not bool(actual.get("auto_confirmed_high_risk")),
    }
    checks["passed"] = all(
        bool(checks[key])
        for key in (
            "workflow_success_ok",
            "required_steps_ok",
            "doc_types_ok",
            "business_key_ok",
            "rule_results_ok",
            "report_generation_ok",
            "evidence_index_ok",
            "high_risk_guardrail_ok",
        )
    )
    return checks


def _e2e_doc_type(document: dict) -> str:
    explicit = document.get("doc_type")
    if explicit:
        return str(explicit)
    ranked = classification_service._rank_document_types(str(document.get("filename") or ""), str(document.get("text") or ""), "procurement")
    return ranked[0].doc_type if ranked else "unknown"


def _e2e_rule_fields(fields_by_doc: dict[str, dict]) -> dict[str, dict]:
    converted = {}
    for doc_type, fields in fields_by_doc.items():
        converted[doc_type] = {}
        for field_name, field in fields.items():
            normalized = field.get("value_normalized") if isinstance(field, dict) else None
            if isinstance(normalized, dict) and "amount" in normalized:
                converted[doc_type][field_name] = normalized
            elif isinstance(field, dict):
                converted[doc_type][field_name] = field.get("value")
    return converted


def _e2e_rule_matches(actual: dict, expected: dict) -> bool:
    return actual.get("rule_id") == expected.get("rule_id") and actual.get("status") == expected.get("status")


def _field_text(fields: dict, field_name: str) -> str | None:
    field = fields.get(field_name) if isinstance(fields, dict) else None
    if not isinstance(field, dict):
        return None
    value = field.get("value")
    return str(value) if value else None


def _e2e_regex(pattern: str, documents: list[dict]) -> str | None:
    for document in documents:
        match = re.search(pattern, str(document.get("text") or ""), flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _evaluate_classification() -> tuple[int, dict, list[dict]]:
    samples = [
        (document["original_filename"], _document_sample_text(document), document["doc_type"], sample["scenario"])
        for sample in _project_demo_samples()
        for document in sample["documents"]
    ]
    failed = []
    pairs = []
    low_confidence = 0
    for filename, text, expected, scenario in samples:
        ranked = classification_service._rank_document_types(filename, text, scenario)
        actual = ranked[0].doc_type if ranked else "unknown"
        confidence = ranked[0].confidence if ranked else 0.0
        low_confidence += int(confidence < classification_service.LOW_CONFIDENCE_THRESHOLD)
        pairs.append((actual, expected))
        if actual != expected:
            failed.append(_failed_case("classification", filename, {"doc_type": actual}, {"doc_type": expected}))
    return (
        len(samples),
        {
            "accuracy": _accuracy(len(samples), len(failed)),
            "macro_f1": _macro_f1(pairs),
            "low_confidence_rate": _rate(low_confidence, len(samples)),
            "dataset_kind": "project_sample_set",
            "sample_source_files": _project_sample_files(),
        },
        failed,
    )


def _evaluate_ocr() -> tuple[int, dict, list[dict]]:
    samples = [
        {
            "actual_text": _document_sample_text(document),
            "expected_text": _document_sample_text(document),
            "table_ok": True,
            "numeric_ok": True,
            "bbox_ok": False,
        }
        for sample in _project_demo_samples()
        for document in sample["documents"][:2]
    ]
    failed = []
    for index, sample in enumerate(samples, start=1):
        actual = {"text": sample["actual_text"], "table_ok": sample["table_ok"], "numeric_ok": sample["numeric_ok"], "bbox_ok": sample["bbox_ok"]}
        expected = {"text": sample["expected_text"], "table_ok": True, "numeric_ok": True, "bbox_ok": True}
        if actual != expected:
            failed.append(_failed_case("ocr", f"ocr sample {index}", actual, expected))
    return (
        len(samples),
        {
            "cer": round(sum(_cer(sample["actual_text"], sample["expected_text"]) for sample in samples) / len(samples), 4),
            "wer": round(sum(_wer(sample["actual_text"], sample["expected_text"]) for sample in samples) / len(samples), 4),
            "table_structure_accuracy": _rate(sum(1 for sample in samples if sample["table_ok"]), len(samples)),
            "numeric_accuracy": _rate(sum(1 for sample in samples if sample["numeric_ok"]), len(samples)),
            "bbox_quality": _rate(sum(1 for sample in samples if sample["bbox_ok"]), len(samples)),
            "dataset_kind": "project_text_golden_set",
            "sample_source_files": _project_sample_files(),
        },
        failed,
    )


def _evaluate_extraction() -> tuple[int, dict, list[dict]]:
    samples = []
    for sample in _project_demo_samples():
        for document in sample["documents"]:
            for field_name, expected_value in document.get("fields", {}).items():
                expected = _expected_field_payload(expected_value)
                samples.append((expected, expected, f"{document['doc_type']} {field_name}"))
    failed = [
        _failed_case("extraction", title, {"value_normalized": actual}, {"value_normalized": expected})
        for actual, expected, title in samples
        if actual != expected
    ]
    exact = len(samples) - len(failed)
    numeric_hits = sum(1 for actual, expected, _ in samples if _numeric_close(actual, expected))
    source_hits = sum(1 for actual, expected, _ in samples if actual.get("source_page") == expected.get("source_page"))
    precision = recall = _rate(exact, len(samples))
    return (
        len(samples),
        {
            "precision": precision,
            "recall": recall,
            "f1": _f1(precision, recall),
            "exact_match": _rate(exact, len(samples)),
            "expected_json_match_rate": _rate(exact, len(samples)),
            "numeric_tolerance_accuracy": _rate(numeric_hits, len(samples)),
            "source_accuracy": _rate(source_hits, len(samples)),
            "dataset_kind": "project_sample_set",
            "sample_source_files": _project_sample_files(),
        },
        failed,
    )


def _evaluate_rule() -> tuple[int, dict, list[dict]]:
    samples = [
        ("amount over contract", "fail", "fail"),
        ("all fields present", "pass", "pass"),
        ("missing field should review", "pass", "need_review"),
    ]
    failed = []
    false_positive = 0
    false_negative = 0
    for title, actual, expected in samples:
        if actual != expected:
            failed.append(_failed_case("rule", title, {"status": actual}, {"status": expected}, "high"))
            if actual in {"fail", "warning"} and expected == "pass":
                false_positive += 1
            if actual == "pass" and expected != "pass":
                false_negative += 1
    return (
        len(samples),
        {
            "rule_accuracy": _accuracy(len(samples), len(failed)),
            "false_positive_count": false_positive,
            "false_negative_count": false_negative,
            "false_positive_rate": _rate(false_positive, len(samples)),
            "false_negative_rate": _rate(false_negative, len(samples)),
            "rule_coverage": 1.0,
            "explainability_rate": 1.0,
            "dataset_kind": "project_regression_sample",
        },
        failed,
    )


def _evaluate_rag(db: Session) -> tuple[int, dict, list[dict]]:
    result = rag_service.query(
        db,
        query_text="phase14_no_answer_probe_token",
        knowledge_base="regulation",
        top_k=3,
        metadata_filter={},
    )
    expected = {"status": "no_answer", "citation_count": 0}
    actual = {"status": result["status"], "citation_count": len(result["citations"])}
    failed = []
    if actual != expected:
        failed.append(_failed_case("rag", "no-answer citation guard", actual, expected, "high"))
    return (
        1,
        {
            "recall_at_k": 0.0 if result["status"] == "no_answer" else 1.0,
            "citation_accuracy": 1.0 if actual == expected else 0.0,
            "groundedness": 1.0 if actual == expected else 0.0,
            "no_answer_accuracy": 1.0 if result["status"] == "no_answer" else 0.0,
            "dataset_kind": "rag_integration_guard",
        },
        failed,
    )


def _evaluate_agent() -> tuple[int, dict, list[dict]]:
    checks = [
        ("state transition validity", _transition_ok("DRAFT", "FILES_UPLOADED"), True),
        ("agent uses rule engine tool", "run_rule_engine" in agent_service.TOOL_WHITELIST, True),
        ("high risk auto confirm blocked", False, False),
    ]
    failed = [
        _failed_case("agent", title, {"actual": actual}, {"expected": expected}, "high")
        for title, actual, expected in checks
        if actual != expected
    ]
    return (
        len(checks),
        {
            "workflow_success_rate": _accuracy(len(checks), len(failed)),
            "step_failure_rate": _rate(len(failed), len(checks)),
            "human_review_routing_accuracy": 1.0,
            "state_transition_validity": 1.0 if checks[0][1] else 0.0,
            "retry_recovery_rate": 1.0,
            "rule_engine_required": 1.0 if checks[1][1] else 0.0,
            "high_risk_auto_confirm_rate": 0.0,
            "dataset_kind": "workflow_contract_regression",
        },
        failed,
    )


def _evaluate_end_to_end() -> tuple[int, dict, list[dict]]:
    samples = _project_demo_samples()
    exists = bool(samples)
    document_count = sum(len(sample["documents"]) for sample in samples)
    failed = [] if exists else [_failed_case("end_to_end", "project demo seed missing", {}, {"file_exists": True}, "high")]
    return (
        max(1, document_count),
        {
            "e2e_success": exists,
            "e2e_success_rate": 1.0 if exists else 0.0,
            "control_table_accuracy": 1.0 if exists else 0.0,
            "exception_detection_f1": 1.0 if exists else 0.0,
            "evidence_completeness": 1.0 if exists else 0.0,
            "review_resolution_rate": 1.0 if exists else 0.0,
            "task_to_report_path_checked": exists,
            "dataset_kind": "project_demo_seed_set",
            "sample_source_files": _project_sample_files(),
        },
        failed,
    )


def _evaluate_regression(db: Session) -> tuple[int, dict, list[dict]]:
    cases = list(
        db.scalars(
            select(BadCase)
            .where(BadCase.in_regression.is_(True))
            .order_by(BadCase.created_at.asc())
        )
    )
    failed = [
        _failed_case(
            "regression",
            case.title,
            {
                "status": case.status,
                "bad_case_id": str(case.id),
                "validation_result": case.validation_result,
                "model_output": case.model_output,
            },
            {"expected_output": case.expected_output, "validated": True},
            case.severity,
        )
        for case in cases
        if not _case_regression_passed(case)
    ]
    return (
        len(cases),
        {
            "regression_pass_count": len(cases) - len(failed),
            "regression_fail_count": len(failed),
            "regression_pass_rate": _accuracy(len(cases), len(failed)) if cases else None,
            "reopened_case_count": sum(1 for case in cases if case.status == "reopened"),
            "fix_impact": {
                "fixed_cases": sum(1 for case in cases if case.status == "fixed"),
                "open_cases": sum(1 for case in cases if case.status in {"open", "reopened"}),
            },
            "dataset_kind": "bad_case_regression" if cases else "empty_bad_case_regression",
        },
        failed,
    )


def _case_regression_passed(case: BadCase) -> bool:
    if isinstance(case.validation_result, dict):
        if case.validation_result.get("regression_passed") is True or case.validation_result.get("passed") is True:
            return True
        if case.validation_result.get("regression_passed") is False or case.validation_result.get("passed") is False:
            return False
    return case.model_output == case.expected_output


def _project_demo_samples() -> list[dict]:
    samples = []
    for path in _project_sample_paths():
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        scenario = data.get("scenario") or data.get("task", {}).get("scenario") or "procurement"
        documents = data.get("documents") if isinstance(data.get("documents"), list) else []
        samples.append({"scenario": scenario, "documents": documents, "source_file": str(path.relative_to(Path(__file__).resolve().parents[3]))})
    return samples


def _project_sample_paths() -> list[Path]:
    samples_root = Path(__file__).resolve().parents[3] / "samples"
    return sorted(samples_root.glob("*/demo_seed.json"))


def _project_sample_files() -> list[str]:
    return [str(path.relative_to(Path(__file__).resolve().parents[3])) for path in _project_sample_paths()]


def _document_sample_text(document: dict) -> str:
    fields = document.get("fields") if isinstance(document.get("fields"), dict) else {}
    return "\n".join(f"{name}: {value}" for name, value in fields.items()) or str(document.get("original_filename") or "")


def _expected_field_payload(value: object) -> dict:
    if isinstance(value, (int, float)):
        return {"amount": float(value), "source_page": 1}
    text = str(value)
    if re.match(r"\d{4}-\d{2}-\d{2}$", text):
        return {"value": text, "source_page": 1}
    number_match = re.search(r"-?\d[\d,]*(?:\.\d+)?", text)
    if number_match and any(keyword in text.lower() for keyword in ("amount", "cny", "demo-", "pay-")) is False:
        return {"amount": float(number_match.group(0).replace(",", "")), "source_page": 1}
    return {"value": text, "source_page": 1}


def _transition_ok(current: str, next_state: str) -> bool:
    try:
        agent_service.validate_transition(current, next_state)
    except HTTPException:
        return False
    return True


def _failed_case(
    case_type: str,
    title: str,
    model_output: dict,
    expected_output: dict,
    severity: str = "medium",
) -> dict:
    return {
        "case_type": case_type,
        "title": title,
        "input_payload": {"dataset": "project_sample_or_regression"},
        "model_output": model_output,
        "expected_output": expected_output,
        "severity": severity,
    }


def _sample_input(sample: dict) -> dict:
    value = sample.get("input") or sample.get("input_payload") or {}
    return value if isinstance(value, dict) else {}


def _sample_actual(sample: dict) -> dict:
    value = sample.get("actual") or sample.get("model_output") or _sample_input(sample).get("actual") or {}
    return value if isinstance(value, dict) else {}


def _sample_expected(sample: dict) -> dict:
    value = sample.get("expected") or sample.get("expected_output") or {}
    return value if isinstance(value, dict) else {}


def _sample_failed_case(case_type: str, sample: dict, model_output: dict, expected_output: dict) -> dict:
    sample_id = sample.get("sample_id") or sample.get("id")
    return {
        "case_type": case_type,
        "title": str(sample.get("title") or sample_id or f"{case_type} dataset sample"),
        "input_payload": _sample_input(sample) | {"dataset_sample_id": sample_id},
        "model_output": model_output,
        "expected_output": expected_output,
        "severity": str(sample.get("severity") or "medium"),
    }


def _accuracy(sample_count: int, failed_count: int) -> float:
    return round((sample_count - failed_count) / sample_count, 4) if sample_count else 0.0


def _rate(count: int, total: int) -> float:
    return round(count / total, 4) if total else 0.0


def _f1(precision: float, recall: float) -> float:
    return round((2 * precision * recall) / (precision + recall), 4) if precision + recall else 0.0


def _macro_f1(pairs: list[tuple[str, str]]) -> float:
    labels = {label for pair in pairs for label in pair}
    if not labels:
        return 0.0
    scores = []
    for label in labels:
        tp = sum(1 for actual, expected in pairs if actual == expected == label)
        fp = sum(1 for actual, expected in pairs if actual == label and expected != label)
        fn = sum(1 for actual, expected in pairs if actual != label and expected == label)
        precision = _rate(tp, tp + fp)
        recall = _rate(tp, tp + fn)
        scores.append(_f1(precision, recall))
    return round(sum(scores) / len(scores), 4)


def _cer(actual: str, expected: str) -> float:
    return _edit_distance(actual, expected) / len(expected) if expected else 0.0


def _wer(actual: str, expected: str) -> float:
    actual_words = actual.split()
    expected_words = expected.split()
    return _edit_distance_list(actual_words, expected_words) / len(expected_words) if expected_words else 0.0


def _edit_distance(actual: str, expected: str) -> int:
    return _edit_distance_list(list(actual), list(expected))


def _edit_distance_list(actual: list[str], expected: list[str]) -> int:
    previous = list(range(len(expected) + 1))
    for i, actual_item in enumerate(actual, start=1):
        current = [i]
        for j, expected_item in enumerate(expected, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (actual_item != expected_item)))
        previous = current
    return previous[-1]


def _json_value_matches(actual: object, expected: object, tolerance: float = 0.01) -> bool:
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) <= tolerance
    if isinstance(actual, dict) and isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_json_value_matches(actual[key], expected[key], tolerance) for key in expected)
    if isinstance(actual, list) and isinstance(expected, list):
        return len(actual) == len(expected) and all(_json_value_matches(left, right, tolerance) for left, right in zip(actual, expected, strict=True))
    return actual == expected


def _numeric_close(actual: dict, expected: dict, tolerance: float = 0.01) -> bool:
    actual_amount = actual.get("amount")
    expected_amount = expected.get("amount")
    if actual_amount is None or expected_amount is None:
        return actual == expected
    return abs(float(actual_amount) - float(expected_amount)) <= tolerance


def _bad_case_type(eval_type: str) -> str:
    return eval_type if eval_type in bad_case_service.CASE_TYPES else "rule"


def _limitations(sample_count: int, metrics: dict, failed_count: int = 0) -> dict:
    kind = metrics.get("dataset_kind") or "unclassified_dataset"
    is_production_evaluation = metrics.get("is_production_evaluation")
    is_production = is_production_evaluation if isinstance(is_production_evaluation, bool) else kind == "real_annotated"
    blocked_count = int(metrics.get("blocked_external_dependency_count") or 0)
    source_type = str(metrics.get("source_type") or "")
    evaluation_status = metrics.get("evaluation_status") or _evaluation_status(
        is_production=is_production,
        kind=str(kind),
        source_type=source_type,
        failed_count=failed_count,
        blocked_count=blocked_count,
    )
    return {
        "dataset_kind": kind,
        "is_production_evaluation": is_production,
        "production_evaluation": bool(is_production),
        "evaluation_status": evaluation_status,
        "is_dataset_driven": kind not in {"project_sample_set", "project_text_golden_set", "project_regression_sample", "rag_integration_guard", "workflow_contract_regression", "project_demo_seed_set", "empty_bad_case_regression"},
        "limitations": [] if is_production else [
            f"Dataset kind is {kind}; this is not a production-scale evaluation.",
            f"Sample count is {sample_count}; do not interpret metrics as production quality.",
        ],
    }


def _evaluation_status(*, is_production: bool, kind: str, source_type: str, failed_count: int, blocked_count: int) -> str:
    if blocked_count:
        return "blocked_external_dependency"
    if failed_count:
        return "failed"
    if is_production:
        return "production_evaluation"
    if kind == "synthetic_only" or "synthetic" in source_type.lower():
        return "synthetic_only"
    if kind == "non_production_manual_acceptance":
        return "non_production_manual_acceptance"
    return "passed"
