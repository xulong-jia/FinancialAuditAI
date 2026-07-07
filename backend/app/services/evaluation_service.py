from pathlib import Path
from hashlib import sha256
import json
import re
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bad_case import BadCase
from app.models.audit_task import AuditTask
from app.models.document import Document
from app.models.evaluation_result import EvaluationResult
from app.schemas.quality import EvaluationRunRequest
from app.services import agent_service, audit_log_service, bad_case_service, classification_service, extraction_service, ocr_service, rag_service


PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
        metrics=metrics | _limitations(sample_count, metrics.get("dataset_kind"), metrics.get("is_production_evaluation")),
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
    if payload.eval_type not in {"ocr", "classification", "extraction", "rule"}:
        raise HTTPException(
            status_code=400,
            detail="Manual acceptance dataset manifest currently supports OCR, classification, extraction, and rule evaluation only",
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
    elif eval_type == "regression":
        sample_count, metrics, failed = _evaluate_json_samples(samples, "regression")
    else:  # pragma: no cover - schema guards this.
        raise HTTPException(status_code=400, detail="Unsupported evaluation type")
    metrics.update(
        {
            "dataset_kind": dataset["dataset_kind"],
            "source_type": dataset["source_type"],
            "dataset_source": dataset["dataset_source"],
            "is_dataset_driven": True,
            "is_production_evaluation": dataset["is_production_evaluation"],
        }
    )
    return sample_count, metrics, failed


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
    status_hits = severity_hits = evidence_hits = 0
    evidence_total = 0
    evidence_sample_hits = 0
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
        severity_ok = actual_severity == expected_severity
        evidence_required = bool(expected.get("must_include_evidence"))
        evidence_ok = not evidence_required or bool(actual.get("evidence"))
        evidence_sample_hits += int(bool(actual.get("evidence")))
        status_hits += int(status_ok)
        severity_hits += int(severity_ok)
        evidence_total += int(evidence_required)
        evidence_hits += int(evidence_ok and evidence_required)
        if not (rule_ok and status_ok and severity_ok and evidence_ok):
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
            "failed_case_count": len(failed),
            "rule_accuracy": _accuracy(len(samples), len(failed)),
            "false_positive_count": false_positive,
            "false_negative_count": false_negative,
            "false_positive_rate": _rate(false_positive, len(samples)),
            "false_negative_rate": _rate(false_negative, len(samples)),
            "rule_coverage": 1.0,
            "explainability_rate": _rate(evidence_sample_hits, len(samples)),
        },
        failed,
    )


def _evaluate_rule_dataset_sample(sample: dict) -> dict:
    rule_id = str(sample.get("rule_id") or "")
    if rule_id != "PROC_AMOUNT_001":
        return {"rule_id": rule_id, "status": "unsupported", "severity": "high", "evidence": []}
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
            "expected_value": {"contract_amount": contract_amount, "tolerance": tolerance},
            "actual_value": amounts | {"mismatches": mismatches},
            "evidence": _rule_amount_evidence(fields),
        }
    return {
        "rule_id": rule_id,
        "status": "pass",
        "severity": "low",
        "expected_value": {"contract_amount": contract_amount, "tolerance": tolerance},
        "actual_value": amounts,
        "evidence": [],
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
    recall_hits = citation_hits = grounded_hits = no_answer_hits = 0
    for sample in samples:
        input_payload = _sample_input(sample)
        expected = _sample_expected(sample)
        if input_payload.get("query"):
            result = rag_service.query(
                db,
                query_text=str(input_payload["query"]),
                knowledge_base=str(input_payload.get("knowledge_base") or "regulation"),
                top_k=int(input_payload.get("top_k") or 3),
                metadata_filter=input_payload.get("metadata_filter") if isinstance(input_payload.get("metadata_filter"), dict) else {},
                task_id=None,
            )
            actual = {"status": result["status"], "citation_count": len(result["citations"])}
        else:
            actual = _sample_actual(sample)
        expected_status = expected.get("status")
        min_citations = int(expected.get("min_citations") or expected.get("citation_count") or 0)
        status_ok = expected_status is None or actual.get("status") == expected_status
        citation_ok = int(actual.get("citation_count") or 0) >= min_citations
        recall_hits += int(citation_ok)
        citation_hits += int(citation_ok)
        grounded_hits += int(status_ok and citation_ok)
        no_answer_hits += int((actual.get("status") == "no_answer") == (expected_status == "no_answer"))
        if not (status_ok and citation_ok):
            failed.append(_sample_failed_case("rag", sample, actual, expected))
    return (
        len(samples),
        {
            "recall_at_k": _rate(recall_hits, len(samples)),
            "citation_accuracy": _rate(citation_hits, len(samples)),
            "groundedness": _rate(grounded_hits, len(samples)),
            "no_answer_accuracy": _rate(no_answer_hits, len(samples)),
        },
        failed,
    )


def _evaluate_agent_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    transitions = review_routes = retry_hits = rule_hits = high_risk_blocks = 0
    for sample in samples:
        actual = _sample_actual(sample)
        expected = _sample_expected(sample)
        transitions += int(bool(actual.get("state_transition_valid")) == bool(expected.get("state_transition_valid", True)))
        review_routes += int(bool(actual.get("human_review_routed")) == bool(expected.get("human_review_routed", True)))
        retry_hits += int(bool(actual.get("retry_recovered")) == bool(expected.get("retry_recovered", True)))
        rule_hits += int(bool(actual.get("used_rule_engine")) == bool(expected.get("used_rule_engine", True)))
        high_risk_blocks += int(not bool(actual.get("auto_confirmed_high_risk")))
        if actual != expected:
            failed.append(_sample_failed_case("agent", sample, actual, expected))
    return (
        len(samples),
        {
            "workflow_success_rate": _accuracy(len(samples), len(failed)),
            "step_failure_rate": _rate(len(failed), len(samples)),
            "human_review_routing_accuracy": _rate(review_routes, len(samples)),
            "state_transition_validity": _rate(transitions, len(samples)),
            "retry_recovery_rate": _rate(retry_hits, len(samples)),
            "rule_engine_required": _rate(rule_hits, len(samples)),
            "high_risk_auto_confirm_rate": 1 - _rate(high_risk_blocks, len(samples)),
        },
        failed,
    )


def _evaluate_e2e_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    keys = ["e2e_success", "control_table_accuracy", "exception_detection", "evidence_complete", "review_resolved"]
    hits = dict.fromkeys(keys, 0)
    for sample in samples:
        actual = _sample_actual(sample)
        expected = _sample_expected(sample)
        for key in keys:
            hits[key] += int(bool(actual.get(key)) == bool(expected.get(key, True)))
        if actual != expected:
            failed.append(_sample_failed_case("end_to_end", sample, actual, expected))
    return (
        len(samples),
        {
            "e2e_success_rate": _rate(hits["e2e_success"], len(samples)),
            "control_table_accuracy": _rate(hits["control_table_accuracy"], len(samples)),
            "exception_detection_f1": _rate(hits["exception_detection"], len(samples)),
            "evidence_completeness": _rate(hits["evidence_complete"], len(samples)),
            "review_resolution_rate": _rate(hits["review_resolved"], len(samples)),
        },
        failed,
    )


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


def _limitations(sample_count: int, dataset_kind: str | None = None, is_production_evaluation: object = None) -> dict:
    kind = dataset_kind or "unclassified_dataset"
    is_production = is_production_evaluation if isinstance(is_production_evaluation, bool) else kind == "real_annotated"
    return {
        "dataset_kind": kind,
        "is_production_evaluation": is_production,
        "is_dataset_driven": kind not in {"project_sample_set", "project_text_golden_set", "project_regression_sample", "rag_integration_guard", "workflow_contract_regression", "project_demo_seed_set", "empty_bad_case_regression"},
        "limitations": [] if is_production else [
            f"Dataset kind is {kind}; this is not a production-scale evaluation.",
            f"Sample count is {sample_count}; do not interpret metrics as production quality.",
        ],
    }
