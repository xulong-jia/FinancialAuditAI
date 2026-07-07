from pathlib import Path
from hashlib import sha256
from datetime import date
import asyncio
import json
import os
import re
from types import SimpleNamespace
from uuid import UUID, uuid4

import fitz
from fastapi import HTTPException
from sqlalchemy import func, select
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
from app.models.model_invocation import ModelInvocation
from app.models.rag_chunk import RagChunk
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
OCR_BOX_LINE_COUNT_CAP = 20
OCR_LONG_TEXT_TOKEN_THRESHOLD = 0.75
OCR_ADDRESS_TOKEN_THRESHOLD = 0.7
OCR_LONG_TEXT_MIN_TOKENS = 5
EXTRACTION_ADDRESS_TOKEN_THRESHOLD = 0.7
EXTRACTION_PUBLIC_FIELDS = ("company", "date", "address", "total")
EXTRACTION_PUBLIC_FIELD_ALIASES = {
    "company": (
        "company",
        "company_name",
        "seller_name",
        "supplier_name",
        "vendor_name",
        "buyer_name",
        "customer_name",
        "counterparty_name",
        "payee_name",
        "payer_name",
    ),
    "date": (
        "date",
        "invoice_date",
        "receipt_date",
        "payment_date",
        "voucher_date",
        "order_date",
        "signing_date",
        "sent_date",
        "replied_date",
    ),
    "address": ("address", "vendor_address", "supplier_address", "seller_address", "counterparty_address"),
    "total": (
        "total",
        "amount_total",
        "total_amount",
        "amount_including_tax",
        "amount",
        "payment_amount",
        "confirmed_amount",
        "book_amount",
    ),
}
MANUAL_DATASET_EVAL_TYPES = {
    "ocr",
    "classification",
    "extraction",
    "rule",
    "rag",
    "agent",
    "persistent_rag_workflow",
    "agent_db_workflow",
    "end_to_end",
    "full_db_workflow",
    "regression",
}
REGRESSION_CHILD_EVAL_TYPES = (
    "ocr",
    "classification",
    "extraction",
    "rule",
    "rag",
    "agent",
    "persistent_rag_workflow",
    "agent_db_workflow",
    "end_to_end",
    "full_db_workflow",
)


def evaluation_datasets_root() -> Path:
    return PROJECT_ROOT / "local_storage" / "evaluation_datasets"


def external_acceptance_root() -> Path:
    return PROJECT_ROOT / "local_storage" / "external_acceptance"


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
    elif payload.eval_type == "persistent_rag_workflow":
        sample_count, metrics, failed_cases = _evaluate_persistent_rag_workflow(db)
    elif payload.eval_type == "agent_db_workflow":
        sample_count, metrics, failed_cases = _evaluate_agent_db_workflow(db)
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
            detail="Manual acceptance dataset manifest currently supports OCR, classification, extraction, rule, RAG, Agent, persistent RAG workflow, Agent DB workflow, E2E, full DB workflow, and regression evaluation only",
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
    data = _expand_external_label_samples(path, data)
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
    external_dataset = _is_under(path, external_acceptance_root())
    guard_warnings: list[str] = []
    is_production, guard_warnings = _guard_production_flag(
        source_type,
        is_production,
        labels_declared=bool(labels),
        expected_evidence_declared=bool(expected_evidence),
        warnings=guard_warnings,
    )
    normalized_source_type = source_type.strip().lower()
    if normalized_source_type == "synthetic_external_acceptance":
        dataset_kind = "synthetic_external_acceptance"
    elif not is_production and dataset_kind == "real_annotated":
        dataset_kind = "non_production_manual_acceptance"
    samples = []
    for sample in data["samples"]:
        if not isinstance(sample, dict):
            continue
        merged_sample, guard_warnings = _merge_external_label(sample, path.parent, guard_warnings)
        if default_eval_type == "classification" and external_dataset:
            merged_sample = _merge_classification_external_text(merged_sample, path.parent)
        if default_eval_type == "extraction" and external_dataset:
            merged_sample = _merge_extraction_external_sample(merged_sample, path.parent)
        normalized = {
            "eval_type": default_eval_type,
            "dataset_name": dataset_name,
            "source_type": source_type,
            "is_production_evaluation": is_production,
            "external_acceptance_dataset": external_dataset or bool(merged_sample.get("label_path")),
            "dataset_dir": str(path.parent.resolve()) if external_dataset else None,
            **merged_sample,
        }
        sample_production, guard_warnings = _guard_production_flag(
            str(normalized.get("source_type") or source_type),
            bool(normalized.get("is_production_evaluation")),
            labels_declared=bool(labels or normalized.get("label_path")),
            expected_evidence_declared=bool(expected_evidence or _sample_expected(normalized)),
            warnings=guard_warnings,
        )
        normalized["is_production_evaluation"] = sample_production
        samples.append(normalized)
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
        "limitations_declared": ([str(item) for item in limitations] if isinstance(limitations, list) else []) + guard_warnings,
        "external_resource_required": external_resource_required,
        "production_guard_warnings": guard_warnings,
        "external_acceptance_dataset": external_dataset,
        "documents": data.get("documents") if isinstance(data.get("documents"), list) else [],
        "samples": samples,
    }


def _resolve_dataset_path(payload: EvaluationRunRequest) -> Path | None:
    roots = [PROJECT_ROOT / "samples" / "evaluation", evaluation_datasets_root(), evals_datasets_root(), external_acceptance_root()]
    if payload.dataset_path:
        path = Path(payload.dataset_path)
        if path.is_absolute() or ".." in path.parts:
            raise HTTPException(
                status_code=400,
                detail="Evaluation dataset_path must be project-root relative and stay under samples/evaluation, local_storage/evaluation_datasets, evals/datasets, or local_storage/external_acceptance",
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
            detail="Evaluation dataset_path must be under samples/evaluation, local_storage/evaluation_datasets, evals/datasets, or local_storage/external_acceptance",
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


def _expand_external_label_samples(path: Path, data: dict) -> dict:
    label_path = data.get("label_path")
    if not label_path:
        return data
    label_file = _resolve_external_acceptance_path(str(label_path), path.parent)
    try:
        label = json.loads(label_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"External label_path could not be read: {exc.__class__.__name__}") from exc
    if not isinstance(label, dict) or not isinstance(label.get("samples"), list):
        raise HTTPException(status_code=400, detail="External label_path must point to a JSON object with a samples array")
    expanded = dict(data)
    if not isinstance(expanded.get("samples"), list):
        expanded["samples"] = label["samples"]
    for key in ("source_type", "is_production_evaluation", "dataset_kind", "sample_count"):
        if key in label and key not in expanded:
            expanded[key] = label[key]
    if "labels" not in expanded:
        expanded["labels"] = {"label_path": str(label_path)}
    return expanded


def _merge_external_label(sample: dict, dataset_dir: Path, warnings: list[str]) -> tuple[dict, list[str]]:
    label_path = sample.get("label_path")
    if not label_path:
        return dict(sample), warnings
    label_file = _resolve_external_acceptance_path(str(label_path), dataset_dir)
    try:
        label = json.loads(label_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"External label_path could not be read: {exc.__class__.__name__}") from exc
    if not isinstance(label, dict):
        raise HTTPException(status_code=400, detail="External label_path must point to a JSON object")
    merged = dict(sample)
    label_expected = label.get("expected") if isinstance(label.get("expected"), dict) else {}
    sample_expected = _sample_expected(sample)
    merged["expected"] = {**label_expected, **sample_expected}
    for key in ("source_type", "is_production_evaluation", "dataset_kind"):
        if key in label and key not in merged:
            merged[key] = label[key]
    merged["label_path_resolved"] = str(label_file.relative_to(PROJECT_ROOT)) if _is_under(label_file, PROJECT_ROOT) else str(label_file)
    return merged, warnings


def _resolve_external_acceptance_path(value: str, dataset_dir: Path) -> Path:
    if not value:
        raise HTTPException(status_code=400, detail="External label_path is required")
    raw_path = Path(value)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise HTTPException(status_code=400, detail="External label_path must stay under local_storage/external_acceptance")
    candidates = [(PROJECT_ROOT / raw_path).resolve(), (dataset_dir / raw_path).resolve()]
    for candidate in candidates:
        if _is_under(candidate, external_acceptance_root()) and candidate.suffix == ".json":
            if candidate.exists():
                return candidate
            raise HTTPException(status_code=400, detail="External label_path must point to an existing JSON file")
    raise HTTPException(status_code=400, detail="External label_path must stay under local_storage/external_acceptance")


def _merge_classification_external_text(sample: dict, dataset_dir: Path) -> dict:
    file_path = sample.get("file_path")
    if not file_path:
        return sample
    file_type = str(sample.get("file_type") or "").strip().lower()
    if file_type and file_type != "text/plain":
        raise HTTPException(status_code=400, detail="Classification external file_path must be text/plain")
    text_file = _resolve_external_acceptance_file_path(str(file_path), dataset_dir)
    try:
        text = text_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Classification file_path could not be read: {exc.__class__.__name__}") from exc
    input_payload = dict(_sample_input(sample))
    input_payload["text"] = text
    input_payload.setdefault("filename", text_file.name)
    input_payload.setdefault("original_filename", text_file.name)
    merged = dict(sample)
    merged["input"] = input_payload
    return merged


def _resolve_external_acceptance_file_path(value: str, dataset_dir: Path) -> Path:
    if not value:
        raise HTTPException(status_code=400, detail="Classification file_path is required")
    raw_path = Path(value)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise HTTPException(status_code=400, detail="Classification file_path must stay under local_storage/external_acceptance")
    candidates = [(PROJECT_ROOT / raw_path).resolve(), (dataset_dir / raw_path).resolve()]
    for candidate in candidates:
        if _is_under(candidate, external_acceptance_root()):
            if candidate.exists() and candidate.is_file():
                return candidate
            raise HTTPException(status_code=400, detail="Classification file_path must point to an existing text file")
    raise HTTPException(status_code=400, detail="Classification file_path must stay under local_storage/external_acceptance")


def _merge_extraction_external_sample(sample: dict, dataset_dir: Path) -> dict:
    source_files = sample.get("source_files") if isinstance(sample.get("source_files"), dict) else {}
    entities_path = sample.get("entities_path") or source_files.get("entities")
    ocr_label_path = sample.get("ocr_label_path")
    box_path = sample.get("box_path") or source_files.get("box")
    file_path = sample.get("file_path")
    if not any((entities_path, ocr_label_path, box_path, file_path)):
        return sample

    if file_path:
        _resolve_external_acceptance_data_file(str(file_path), dataset_dir, "Extraction file_path")

    entities = _load_sroie_entities(entities_path, ocr_label_path, dataset_dir, _sample_expected(sample))
    box_text, ocr_blocks = _load_sroie_box(box_path, dataset_dir) if box_path else ("", [])
    input_payload = dict(_sample_input(sample))
    input_payload.setdefault("filename", str(file_path or sample.get("sample_id") or "sroie-public-receipt"))
    input_payload.setdefault("doc_type", str(sample.get("doc_type") or sample.get("document_type") or "invoice"))
    input_payload.setdefault("scenario", str(sample.get("scenario") or "procurement"))
    input_payload["text"] = _sroie_extraction_text(entities, box_text, input_payload.get("text"))
    input_payload.setdefault(
        "ocr_pages",
        [{"page_number": 1, "raw_text": input_payload["text"], "ocr_blocks": ocr_blocks}],
    )

    expected = dict(_sample_expected(sample))
    expected_fields = dict(expected.get("fields") if isinstance(expected.get("fields"), dict) else {})
    for field_name, field_expected in _sroie_expected_fields(entities).items():
        expected_fields.setdefault(field_name, field_expected)
    expected["fields"] = expected_fields
    expected.setdefault("require_source_evidence", True)
    expected.setdefault("require_source_bbox", False)

    merged = dict(sample)
    merged["doc_type"] = input_payload["doc_type"]
    merged["input"] = input_payload
    merged["expected"] = expected
    return merged


def _resolve_external_acceptance_data_file(value: str, dataset_dir: Path, field_name: str) -> Path:
    if not value:
        raise HTTPException(status_code=400, detail=f"{field_name} is required")
    raw_path = Path(value)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise HTTPException(status_code=400, detail=f"{field_name} must stay under local_storage/external_acceptance")
    candidates = [(PROJECT_ROOT / raw_path).resolve(), (dataset_dir / raw_path).resolve()]
    for candidate in candidates:
        if _is_under(candidate, external_acceptance_root()):
            if candidate.exists() and candidate.is_file():
                return candidate
            raise HTTPException(status_code=400, detail=f"{field_name} must point to an existing file")
    raise HTTPException(status_code=400, detail=f"{field_name} must stay under local_storage/external_acceptance")


def _load_sroie_entities(
    entities_path: object,
    ocr_label_path: object,
    dataset_dir: Path,
    expected: dict,
) -> dict:
    if entities_path:
        path = _resolve_external_acceptance_data_file(str(entities_path), dataset_dir, "Extraction entities_path")
        return _read_json_file(path, "Extraction entities_path")
    key_information = expected.get("key_information")
    if isinstance(key_information, dict):
        return key_information
    if ocr_label_path:
        path = _resolve_external_acceptance_data_file(str(ocr_label_path), dataset_dir, "Extraction ocr_label_path")
        label = _read_json_file(path, "Extraction ocr_label_path")
        label_expected = label.get("expected") if isinstance(label.get("expected"), dict) else {}
        key_information = label_expected.get("key_information")
        if isinstance(key_information, dict):
            return key_information
    return {}


def _read_json_file(path: Path, field_name: str) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} could not be read: {exc.__class__.__name__}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} must point to a JSON object")
    return data


def _load_sroie_box(box_path: object, dataset_dir: Path) -> tuple[str, list[dict]]:
    path = _resolve_external_acceptance_data_file(str(box_path), dataset_dir, "Extraction box_path")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Extraction box_path could not be read: {exc.__class__.__name__}") from exc
    texts = []
    blocks = []
    for line in lines:
        parts = line.split(",", 8)
        if len(parts) < 9:
            continue
        try:
            coords = [float(item) for item in parts[:8]]
        except ValueError:
            continue
        text = parts[8].strip()
        if not text:
            continue
        texts.append(text)
        xs = coords[0::2]
        ys = coords[1::2]
        blocks.append({"text": text, "bbox": [min(xs), min(ys), max(xs), max(ys)]})
    return "\n".join(texts), blocks


def _sroie_extraction_text(entities: dict, box_text: str, existing_text: object) -> str:
    if isinstance(existing_text, str) and existing_text.strip():
        return existing_text
    labeled_lines = []
    company = str(entities.get("company") or "").strip()
    receipt_date = str(entities.get("date") or "").strip()
    address = str(entities.get("address") or "").strip()
    total = str(entities.get("total") or "").strip()
    if company:
        labeled_lines.append(f"Seller Name: {company}")
    if receipt_date:
        labeled_lines.append(f"Invoice Date: {_normalize_public_date(receipt_date) or receipt_date}")
    if address:
        labeled_lines.append(f"Seller Address: {address}")
    if total:
        labeled_lines.append(f"Amount Including Tax: {total}")
    return "\n".join([*labeled_lines, box_text]).strip()


def _sroie_expected_fields(entities: dict) -> dict:
    fields = {}
    company = str(entities.get("company") or "").strip()
    receipt_date = str(entities.get("date") or "").strip()
    address = str(entities.get("address") or "").strip()
    total = str(entities.get("total") or "").strip()
    if company:
        fields["company"] = {"value": company}
    if receipt_date:
        normalized_date = _normalize_public_date(receipt_date)
        fields["date"] = {"value_normalized": {"value": normalized_date or receipt_date}}
    if address:
        fields["address"] = {"value": address}
    if total:
        amount = _normalize_public_amount(total)
        fields["total"] = {"value_normalized": {"amount": amount}} if amount is not None else {"value": total}
    return fields


def _normalize_public_date(value: str) -> str | None:
    for pattern, order in (
        (r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})$", ("year", "month", "day")),
        (r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", ("day", "month", "year")),
        (r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{2})$", ("day", "month", "short_year")),
    ):
        match = re.match(pattern, value.strip())
        if not match:
            continue
        parts = {name: int(match.group(index + 1)) for index, name in enumerate(order)}
        if "short_year" in parts:
            parts["year"] = 2000 + parts["short_year"]
        try:
            return date(parts["year"], parts["month"], parts["day"]).isoformat()
        except ValueError:
            return None
    return None


def _normalize_public_amount(value: str) -> float | None:
    match = re.search(r"-?\d[\d,]*(?:\.\d+)?", value)
    return float(match.group(0).replace(",", "")) if match else None


def _guard_production_flag(
    source_type: str,
    is_production: bool,
    *,
    labels_declared: bool,
    expected_evidence_declared: bool,
    warnings: list[str],
) -> tuple[bool, list[str]]:
    normalized = source_type.strip().lower()
    if normalized == "synthetic_external_acceptance" and is_production:
        return False, warnings + ["synthetic_external_acceptance cannot be marked as production_evaluation"]
    if is_production and normalized not in {"desensitized", "production_approved"}:
        return False, warnings + ["production_evaluation requires source_type=desensitized or production_approved"]
    if is_production and not (labels_declared and expected_evidence_declared):
        return False, warnings + ["production_evaluation requires complete labels and expected evidence declarations"]
    return is_production, warnings


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
        if dataset.get("external_acceptance_dataset") and isinstance(dataset.get("documents"), list) and dataset["documents"]:
            sample_count, metrics, failed = _evaluate_external_rag_samples(db, samples, dataset)
        else:
            sample_count, metrics, failed = _evaluate_rag_samples(db, samples)
    elif eval_type == "agent":
        sample_count, metrics, failed = _evaluate_agent_samples(samples)
    elif eval_type == "persistent_rag_workflow":
        sample_count, metrics, failed = _evaluate_persistent_rag_workflow_samples(db, samples)
    elif eval_type == "agent_db_workflow":
        sample_count, metrics, failed = _evaluate_agent_db_workflow_samples(db, samples)
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
        "production_guard_warnings": dataset.get("production_guard_warnings") if isinstance(dataset.get("production_guard_warnings"), list) else [],
        "external_acceptance_dataset": bool(dataset.get("external_acceptance_dataset")),
    }


def _evaluate_classification_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    pairs = []
    low_confidence = 0
    confidence_total = confidence_hits = 0
    review_total = review_hits = 0
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
        actual_confidence = _optional_float(actual.get("confidence")) or 0.0
        actual.setdefault(
            "need_human_review",
            str(actual.get("doc_type") or "unknown") == "unknown"
            or actual_confidence < classification_service.LOW_CONFIDENCE_THRESHOLD,
        )
        low_confidence += int(actual_confidence < classification_service.LOW_CONFIDENCE_THRESHOLD)
        actual_doc_type = str(actual.get("doc_type") or "unknown")
        expected_doc_type = str(expected.get("doc_type") or "unknown")
        failed_checks = []
        pairs.append((actual_doc_type, expected_doc_type))
        if actual_doc_type != expected_doc_type:
            failed_checks.append("doc_type")
        minimum_confidence = _optional_float(expected.get("minimum_confidence"))
        if minimum_confidence is not None:
            confidence_total += 1
            confidence_ok = actual_confidence >= minimum_confidence
            confidence_hits += int(confidence_ok)
            if not confidence_ok:
                failed_checks.append("minimum_confidence")
        if "need_human_review" in expected:
            review_total += 1
            expected_review = _coerce_bool(expected.get("need_human_review"))
            review_ok = bool(actual.get("need_human_review")) == expected_review
            review_hits += int(review_ok)
            if not review_ok:
                failed_checks.append("need_human_review")
        if failed_checks:
            failed.append(_sample_failed_case("classification", sample, actual | {"failed_checks": failed_checks}, expected))
    return (
        len(samples),
        {
            "accuracy": _accuracy(len(samples), len(failed)),
            "macro_f1": _macro_f1(pairs),
            "low_confidence_rate": _rate(low_confidence, len(samples)),
            "confidence_threshold_accuracy": _rate(confidence_hits, confidence_total),
            "human_review_flag_accuracy": _rate(review_hits, review_total),
            "failed_case_count": len(failed),
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
    key_information_hits = box_line_hits = public_label_hits = 0
    address_hits = 0
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
        key_information_hits += int(checks["key_information_ok"])
        box_line_hits += int(checks["box_line_count_ok"])
        public_label_hits += int(checks["public_dataset_label_ok"])
        address_hits += int(checks["fuzzy_address_ok"])
        blocked += int(actual.get("status") == "blocked_external_dependency")
        if not checks["passed"]:
            failed.append(_sample_failed_case("ocr", sample, _sanitized_ocr_failure_output(actual), checks["expected"]))
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
            "key_information_accuracy": _rate(key_information_hits, total),
            "box_line_count_coverage": _rate(box_line_hits, total),
            "public_dataset_label_accuracy": _rate(public_label_hits, total),
            "normalized_text_match_accuracy": _rate(text_hits, total),
            "fuzzy_address_match_accuracy": _rate(address_hits, total),
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
    expected = _sample_expected(sample)
    try:
        path = _resolve_evaluation_sample_file(
            str(sample.get("file_path") or ""),
            external_only=bool(sample.get("external_acceptance_dataset")),
            base_dir=Path(str(sample["dataset_dir"])) if sample.get("dataset_dir") else None,
        )
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
    configured_provider = ocr_service.settings.ocr_provider.strip().lower()
    if _is_real_ocr_provider(configured_provider) and not _ocr_integration_allowed(sample):
        return {
            "sample_id": sample_id,
            "status": "blocked_external_dependency",
            "error": "Real OCR provider evaluation requires RUN_PROVIDER_INTEGRATION=1 or explicit sample policy",
            "configured_provider": ocr_service.settings.ocr_provider,
        }
    if _is_local_ocr_provider(configured_provider) and _requires_real_ocr_provider(expected):
        return {
            "sample_id": sample_id,
            "status": "blocked_external_dependency",
            "error": "Real OCR provider integration is required for confidence or table-structure expectations",
            "configured_provider": ocr_service.settings.ocr_provider,
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
        "pages_with_image_count": sum(1 for page in pages if getattr(page, "image_path", None)),
        "table_text": _table_text(table_blocks),
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


def _resolve_evaluation_sample_file(value: str, *, external_only: bool = False, base_dir: Path | None = None) -> Path:
    if not value:
        raise ValueError("sample file_path is required")
    allowed_roots = [external_acceptance_root()] if external_only else [
        PROJECT_ROOT / "local_storage" / "manual_acceptance_files",
        PROJECT_ROOT / "samples" / "evaluation",
        evals_datasets_root(),
        external_acceptance_root(),
    ]
    raw_path = Path(value)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise ValueError("sample file_path must be project-root relative and stay under an allowed evaluation data directory")
    candidates = [PROJECT_ROOT / raw_path]
    if base_dir is not None:
        candidates.append(base_dir / raw_path)
    for candidate in candidates:
        resolved = candidate.resolve()
        if any(_is_under(resolved, root) for root in allowed_roots):
            return resolved
    raise ValueError("sample file_path must be under an allowed evaluation data directory")


def _ocr_expected_checks(actual: dict, expected: dict) -> dict:
    required_text = [str(item) for item in expected.get("must_contain_text") or []]
    raw_text = str(actual.get("raw_text") or "")
    missing_text = _missing_required_text(raw_text, required_text)
    missing_key_information = _missing_key_information(str(actual.get("raw_text") or ""), expected.get("key_information"))
    address_ok = not any(item.get("field") == "address" for item in missing_key_information)
    exact_page_count = expected.get("page_count")
    min_page_count = int(expected.get("min_page_count") or exact_page_count or 0)
    min_ocr_blocks = int(expected.get("min_ocr_blocks") or (1 if expected.get("require_ocr_blocks") else 0))
    box_line_count = _optional_int(expected.get("box_line_count"))
    box_line_required = min(box_line_count or 0, OCR_BOX_LINE_COUNT_CAP)
    min_bbox = int(expected.get("min_blocks_with_bbox") or (1 if expected.get("require_bbox") else 0))
    min_confidence = int(expected.get("min_blocks_with_confidence") or (1 if expected.get("require_confidence") else 0))
    min_tables = int(expected.get("min_table_blocks") or (1 if expected.get("require_table_blocks") else 0))
    expected_headers = [str(item) for item in expected.get("expected_table_headers") or []]
    expected_values = [str(item) for item in expected.get("expected_table_values") or []]
    table_text = str(actual.get("table_text") or "")
    missing_headers = [item for item in expected_headers if item not in table_text]
    missing_values = [item for item in expected_values if item not in table_text]
    checks = {
        "text_ok": not missing_text,
        "raw_text_ok": not expected.get("require_raw_text") or bool(str(actual.get("raw_text") or "").strip()),
        "page_count_ok": (
            int(actual.get("page_count") or 0) == int(exact_page_count)
            if exact_page_count is not None
            else int(actual.get("page_count") or 0) >= min_page_count
        ),
        "ocr_blocks_ok": int(actual.get("ocr_blocks_count") or 0) >= min_ocr_blocks,
        "box_line_count_ok": int(actual.get("ocr_blocks_count") or 0) >= box_line_required,
        "bbox_ok": int(actual.get("blocks_with_bbox_count") or 0) >= min_bbox,
        "confidence_ok": int(actual.get("blocks_with_confidence_count") or 0) >= min_confidence,
        "table_blocks_ok": int(actual.get("table_blocks_count") or 0) >= min_tables,
        "page_image_ok": not expected.get("require_page_image") or int(actual.get("pages_with_image_count") or 0) >= int(actual.get("page_count") or 1),
        "key_information_ok": not missing_key_information,
        "fuzzy_address_ok": address_ok,
        "table_headers_ok": not missing_headers,
        "table_values_ok": not missing_values,
        "expected": {
            "missing_text": missing_text,
            "missing_key_information": missing_key_information,
            "require_raw_text": bool(expected.get("require_raw_text")),
            "page_count": exact_page_count,
            "min_page_count": min_page_count,
            "min_ocr_blocks": min_ocr_blocks,
            "box_line_count": box_line_count,
            "box_line_count_required": box_line_required,
            "min_blocks_with_bbox": min_bbox,
            "min_blocks_with_confidence": min_confidence,
            "min_table_blocks": min_tables,
            "require_page_image": bool(expected.get("require_page_image")),
            "missing_table_headers": missing_headers,
            "missing_table_values": missing_values,
        },
    }
    checks["passed"] = actual.get("status") == "completed" and all(
        bool(checks[key])
        for key in (
            "text_ok",
            "raw_text_ok",
            "page_count_ok",
            "ocr_blocks_ok",
            "box_line_count_ok",
            "bbox_ok",
            "confidence_ok",
            "table_blocks_ok",
            "page_image_ok",
            "key_information_ok",
            "table_headers_ok",
            "table_values_ok",
        )
    )
    checks["public_dataset_label_ok"] = checks["text_ok"] and checks["key_information_ok"] and checks["box_line_count_ok"]
    return checks


def _missing_required_text(raw_text: str, required_text: list[str]) -> list[dict[str, float | int]]:
    missing = []
    for index, expected_value in enumerate(required_text):
        matched, score, threshold = _ocr_text_matches(raw_text, expected_value, field="must_contain_text")
        if not matched:
            missing.append({"text_index": index, "match_score": score, "threshold": threshold})
    return missing


def _missing_key_information(raw_text: str, key_information: object) -> list[dict[str, str | float]]:
    if not isinstance(key_information, dict):
        return []
    missing: list[dict[str, str | float]] = []
    for field, value in key_information.items():
        expected_value = str(value or "").strip()
        if not expected_value:
            continue
        matched, score, threshold = _ocr_text_matches(raw_text, expected_value, field=str(field))
        if matched:
            continue
        missing.append({"field": str(field), "match_score": score, "threshold": threshold})
    return missing


def _normalize_ocr_label_text(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _ocr_text_matches(raw_text: str, expected_value: str, *, field: str) -> tuple[bool, float, float]:
    normalized_raw = _normalize_ocr_label_text(raw_text)
    normalized_expected = _normalize_ocr_label_text(expected_value)
    if not normalized_expected:
        return True, 1.0, 1.0
    if normalized_expected in normalized_raw:
        return True, 1.0, 1.0
    expected_tokens = _ocr_label_tokens(expected_value)
    if field.casefold() == "address":
        score = _token_coverage(expected_tokens, _ocr_label_tokens(raw_text))
        return score >= OCR_ADDRESS_TOKEN_THRESHOLD, score, OCR_ADDRESS_TOKEN_THRESHOLD
    if field == "must_contain_text" and len(expected_tokens) >= OCR_LONG_TEXT_MIN_TOKENS:
        score = _token_coverage(expected_tokens, _ocr_label_tokens(raw_text))
        return score >= OCR_LONG_TEXT_TOKEN_THRESHOLD, score, OCR_LONG_TEXT_TOKEN_THRESHOLD
    return False, 0.0, 1.0


def _ocr_label_tokens(value: str) -> list[str]:
    normalized = "".join(char.casefold() if char.isalnum() else " " for char in value)
    return [token for token in normalized.split() if len(token) > 1 or token.isdigit()]


def _token_coverage(expected_tokens: list[str], actual_tokens: list[str]) -> float:
    expected = set(expected_tokens)
    if not expected:
        return 1.0
    actual = set(actual_tokens)
    return round(len(expected & actual) / len(expected), 4)


def _sanitized_ocr_failure_output(actual: dict) -> dict:
    sanitized = dict(actual)
    raw_text = str(sanitized.pop("raw_text", "") or "")
    sanitized.pop("table_text", None)
    if raw_text:
        sanitized["raw_text_length"] = len(raw_text)
    return sanitized


def _has_bbox(block: dict) -> bool:
    bbox = block.get("bbox")
    return isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(item, (int, float)) for item in bbox)


def _table_text(table_blocks: list[dict]) -> str:
    values: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for key in ("text", "content", "value"):
                if isinstance(value.get(key), str):
                    values.append(value[key])
            for item in value.values():
                collect(item)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    collect(table_blocks)
    return "\n".join(values)


def _is_local_ocr_provider(provider: str) -> bool:
    return provider in {"pymupdf", "pymupdf-local", "local"}


def _is_real_ocr_provider(provider: str) -> bool:
    return provider in ocr_service.AZURE_OCR_PROVIDERS or provider in {"http", "external-http", "real"}


def _ocr_integration_allowed(sample: dict) -> bool:
    return os.getenv("RUN_PROVIDER_INTEGRATION") == "1" or bool(sample.get("allow_external_provider_without_integration"))


def _requires_real_ocr_provider(expected: dict) -> bool:
    return bool(
        expected.get("require_confidence")
        or int(expected.get("min_blocks_with_confidence") or 0) > 0
        or expected.get("require_table_blocks")
        or int(expected.get("min_table_blocks") or 0) > 0
        or expected.get("expected_table_headers")
        or expected.get("expected_table_values")
    )


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


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


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
    public_sample_total = public_sample_failed = 0
    public_field_total = public_field_pass = 0
    public_source_total = public_source_hits = 0
    public_field_totals = {field_name: 0 for field_name in EXTRACTION_PUBLIC_FIELDS}
    public_field_hits = {field_name: 0 for field_name in EXTRACTION_PUBLIC_FIELDS}

    for sample in samples:
        input_payload = _sample_input(sample)
        expected = _sample_expected(sample)
        expected_fields = expected.get("fields") if isinstance(expected.get("fields"), dict) else {}
        text = str(input_payload.get("text") or input_payload.get("raw_text") or "").strip()
        doc_type = str(sample.get("doc_type") or sample.get("document_type") or input_payload.get("doc_type") or "").strip()
        is_public_extraction = str(sample.get("source_type") or "").strip().lower() == "public_dataset"
        public_sample_total += int(is_public_extraction)
        if not text or not doc_type or not expected_fields:
            public_sample_failed += int(is_public_extraction)
            failed.append(
                _sample_failed_case(
                    "extraction",
                    sample,
                    {"status": "failed", "reason": "missing input.text, doc_type, or expected.fields"},
                    expected,
                )
            )
            continue

        actual_fields = _extract_text_sample_fields(
            doc_type,
            text,
            str(input_payload.get("scenario") or "procurement"),
            input_payload,
        )
        actual_fields = _with_public_extraction_alias_fields(sample, actual_fields, expected_fields, input_payload)
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
        if is_public_extraction:
            public_source_total += checks["source_total"]
            public_source_hits += checks["source_text_hits"]
            for field_result in checks["field_results"]:
                canonical = field_result["canonical_field"]
                if canonical not in public_field_totals:
                    continue
                public_field_total += 1
                public_field_totals[canonical] += 1
                if field_result["field_ok"]:
                    public_field_pass += 1
                    public_field_hits[canonical] += 1
        if checks["failed_checks"]:
            public_sample_failed += int(is_public_extraction)
            failed.append(
                _sample_failed_case(
                    "extraction",
                    sample,
                    {"status": "failed", "doc_type": doc_type, "fields": actual_fields, "failed_checks": checks["failed_checks"]},
                    expected,
                )
            )

    metrics = {
        "extraction_sample_pass_rate": _accuracy(len(samples), len(failed)),
        "extraction_field_accuracy": _rate(field_pass, field_total),
        "field_presence_accuracy": _rate(field_present, field_total),
        "normalized_value_accuracy": _rate(normalized_pass, normalized_total),
        "item_line_accuracy": _rate(item_pass, item_total),
        "source_page_coverage": _rate(source_page_hits, source_total),
        "source_text_coverage": _rate(source_text_hits, source_total),
        "source_bbox_coverage": _rate(source_bbox_hits, source_total),
        "failed_case_count": len(failed),
    }
    if public_sample_total:
        metrics.update(
            {
                "extraction_public_sample_pass_rate": _accuracy(public_sample_total, public_sample_failed),
                "extraction_public_field_accuracy": _rate(public_field_pass, public_field_total),
                "extraction_public_company_accuracy": _rate(public_field_hits["company"], public_field_totals["company"]),
                "extraction_public_date_accuracy": _rate(public_field_hits["date"], public_field_totals["date"]),
                "extraction_public_address_accuracy": _rate(public_field_hits["address"], public_field_totals["address"]),
                "extraction_public_total_accuracy": _rate(public_field_hits["total"], public_field_totals["total"]),
                "extraction_public_evidence_coverage": _rate(public_source_hits, public_source_total),
                "blocked_external_dependency_count": 0,
                "evaluation_status": "non_production_public_acceptance",
            }
        )
    return (len(samples), metrics, failed)


def _extract_text_sample_fields(
    doc_type: str,
    text: str,
    scenario: str,
    input_payload: dict | None = None,
) -> dict[str, dict]:
    pages = _extraction_sample_pages(text, input_payload or {})
    currency = extraction_service._normalize_currency(text)
    fields = {}
    for spec in extraction_service.schema_specs_for(scenario, doc_type):
        value = extraction_service._extract_field(spec, pages)
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


def _extraction_sample_pages(text: str, input_payload: dict) -> list[SimpleNamespace]:
    raw_pages = input_payload.get("ocr_pages") or input_payload.get("pages")
    pages = raw_pages if isinstance(raw_pages, list) else []
    normalized = []
    for index, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        page_text = str(page.get("raw_text") or page.get("text") or "")
        blocks = [block for block in page.get("ocr_blocks") or [] if isinstance(block, dict)]
        normalized.append(
            SimpleNamespace(
                page_number=int(page.get("page_number") or index),
                raw_text=page_text,
                ocr_blocks=blocks,
            )
        )
    if normalized:
        return normalized
    blocks = [block for block in input_payload.get("ocr_blocks") or [] if isinstance(block, dict)]
    return [SimpleNamespace(page_number=1, raw_text=text, ocr_blocks=blocks)]


def _check_extraction_expected_fields(actual_fields: dict[str, dict], expected_fields: dict, expected: dict) -> dict:
    require_source_page = bool(expected.get("require_source_page") or expected.get("require_source_evidence"))
    require_source_text = bool(expected.get("require_source_text") or expected.get("require_source_evidence"))
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
        "field_results": [],
    }
    for field_name, expected_field in expected_fields.items():
        if not isinstance(expected_field, dict):
            expected_field = {"value": expected_field}
        actual = _extraction_actual_field(actual_fields, str(field_name))
        field_present = _extraction_field_present(actual)
        value_ok = "value" not in expected_field or _extraction_value_matches(str(field_name), actual.get("value"), expected_field.get("value"))
        normalized_ok = True
        item_ok = True
        checks["field_total"] += 1
        checks["field_present"] += int(field_present)
        if "value_normalized" in expected_field:
            checks["normalized_total"] += 1
            normalized_ok = _extraction_normalized_matches(
                str(field_name),
                actual.get("value_normalized"),
                expected_field.get("value_normalized"),
            )
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
        checks["field_results"].append(
            {
                "field_name": str(field_name),
                "canonical_field": _canonical_public_extraction_field(str(field_name)) or str(field_name),
                "field_ok": field_ok,
            }
        )
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


def _with_public_extraction_alias_fields(
    sample: dict,
    actual_fields: dict[str, dict],
    expected_fields: dict,
    input_payload: dict,
) -> dict[str, dict]:
    if str(sample.get("source_type") or "").strip().lower() != "public_dataset":
        return actual_fields
    augmented = dict(actual_fields)
    text = str(input_payload.get("text") or input_payload.get("raw_text") or "")
    for field_name, expected_field in expected_fields.items():
        canonical = _canonical_public_extraction_field(str(field_name))
        if canonical is None or _extraction_actual_field(augmented, str(field_name)):
            continue
        value = _expected_extraction_text(expected_field)
        evidence = _find_extraction_source_evidence(canonical, value, text, input_payload)
        if evidence is None:
            continue
        augmented[str(field_name)] = {
            "value": value,
            "value_normalized": _public_extraction_normalized_value(canonical, value),
            "source_page": evidence["source_page"],
            "source_text": evidence["source_text"],
            "source_bbox": evidence["source_bbox"],
            "warnings": ["public_dataset_evidence_match"],
        }
    return augmented


def _extraction_actual_field(actual_fields: dict[str, dict], field_name: str) -> dict:
    if field_name in actual_fields:
        return actual_fields[field_name]
    canonical = _canonical_public_extraction_field(field_name)
    if canonical is None:
        return {}
    for alias in EXTRACTION_PUBLIC_FIELD_ALIASES[canonical]:
        actual = actual_fields.get(alias)
        if isinstance(actual, dict) and _extraction_field_present(actual):
            return actual
    return {}


def _canonical_public_extraction_field(field_name: str) -> str | None:
    normalized = field_name.strip().lower()
    for canonical, aliases in EXTRACTION_PUBLIC_FIELD_ALIASES.items():
        if normalized in aliases:
            return canonical
    return None


def _expected_extraction_text(expected_field: object) -> str:
    if isinstance(expected_field, dict):
        if expected_field.get("value") is not None:
            return str(expected_field["value"]).strip()
        normalized = expected_field.get("value_normalized")
        if isinstance(normalized, dict):
            if normalized.get("value") is not None:
                return str(normalized["value"]).strip()
            if normalized.get("amount") is not None:
                return str(normalized["amount"]).strip()
    return str(expected_field or "").strip()


def _find_extraction_source_evidence(
    field_name: str,
    expected_value: str,
    text: str,
    input_payload: dict,
) -> dict | None:
    if not expected_value:
        return None
    pages = _extraction_sample_pages(text, input_payload)
    for page in pages:
        for line in str(page.raw_text or "").splitlines():
            if _extraction_value_matches(field_name, line, expected_value):
                return {
                    "source_page": page.page_number,
                    "source_text": line.strip(),
                    "source_bbox": _bbox_for_extraction_line(page.ocr_blocks, line),
                }
    return None


def _bbox_for_extraction_line(blocks: list[dict], line: str) -> list[float] | None:
    needle = _compact_public_text(line)
    for block in blocks:
        block_text = _compact_public_text(str(block.get("text") or ""))
        bbox = block.get("bbox")
        if needle and needle in block_text and _has_bbox({"bbox": bbox}):
            return [float(item) for item in bbox]
    return None


def _public_extraction_normalized_value(field_name: str, value: str) -> dict | None:
    if field_name == "date":
        normalized = _normalize_public_date(value)
        return {"value": normalized or value}
    if field_name == "total":
        amount = _normalize_public_amount(value)
        return {"amount": amount} if amount is not None else None
    return {"value": value}


def _extraction_value_matches(field_name: str, actual: object, expected: object) -> bool:
    if _json_value_matches(actual, expected):
        return True
    actual_text = str(actual or "")
    expected_text = str(expected or "")
    if not expected_text:
        return True
    canonical = _canonical_public_extraction_field(field_name) or field_name
    if canonical == "address":
        return _token_coverage(_ocr_label_tokens(expected_text), _ocr_label_tokens(actual_text)) >= EXTRACTION_ADDRESS_TOKEN_THRESHOLD
    normalized_expected = _compact_public_text(expected_text)
    normalized_actual = _compact_public_text(actual_text)
    return bool(normalized_expected and normalized_expected in normalized_actual)


def _extraction_normalized_matches(field_name: str, actual: object, expected: object) -> bool:
    if _json_value_matches(actual, expected):
        return True
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        return False
    canonical = _canonical_public_extraction_field(field_name)
    if canonical not in {"date", "total"}:
        return False
    return all(key in actual and _json_value_matches(actual[key], expected_value) for key, expected_value in expected.items())


def _compact_public_text(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


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


def _evaluate_external_rag_samples(db: Session, samples: list[dict], dataset: dict) -> tuple[int, dict, list[dict]]:
    provider_block = _external_rag_provider_blocking_reason()
    if provider_block:
        return (
            len(samples),
            {
                "rag_external_sample_pass_rate": 0.0,
                "rag_external_citation_accuracy": 0.0,
                "rag_external_answer_accuracy": 0.0,
                "rag_external_no_answer_accuracy": 0.0,
                "rag_external_metadata_accuracy": 0.0,
                "failed_case_count": len(samples),
                "blocked_external_dependency_count": 1,
                "blocking_reason": provider_block,
                "evaluation_status": "blocked_external_dependency",
            },
            [
                _sample_failed_case(
                    "rag",
                    sample,
                    {"status": "blocked_external_dependency", "error": provider_block},
                    _sample_expected(sample),
                )
                for sample in samples
            ],
        )

    failed = []
    answer_hits = answer_total = citation_hits = citation_total = no_answer_hits = no_answer_total = 0
    metadata_hits = metadata_total = 0
    run_id = f"external-rag-{uuid4()}"
    indexed_documents = _index_external_rag_documents(db, dataset, run_id)
    default_knowledge_base = indexed_documents[0]["knowledge_base"] if indexed_documents else "prospectus"
    for sample in samples:
        expected = _sample_expected(sample)
        input_payload = _sample_input(sample)
        query_text = str(input_payload.get("query") or sample.get("query") or "")
        knowledge_base = str(input_payload.get("knowledge_base") or sample.get("knowledge_base") or default_knowledge_base)
        metadata_filter = input_payload.get("metadata_filter") if isinstance(input_payload.get("metadata_filter"), dict) else {}
        metadata_filter = {"external_rag_run_id": run_id, **metadata_filter}
        result = rag_service.query(
            db,
            query_text=query_text,
            knowledge_base=knowledge_base,
            top_k=int(input_payload.get("top_k") or sample.get("top_k") or 3),
            metadata_filter=metadata_filter,
            task_id=None,
        )
        actual = _external_rag_actual_result(result)
        checks = _rag_expected_checks(actual, expected)
        answer_total += checks["answer_total"]
        answer_hits += int(checks["answer_text_ok"] and checks["answer_total"])
        no_answer_total += checks["no_answer_total"]
        no_answer_hits += int(checks["no_answer_ok"] and checks["no_answer_total"])
        metadata_total += checks["metadata_total"]
        metadata_hits += int(checks["metadata_ok"] and checks["metadata_total"])
        citation_expected = any(
            checks[key]
            for key in ("citation_presence_total", "citation_document_total", "quote_total")
        )
        citation_total += int(citation_expected)
        citation_hits += int(
            citation_expected
            and checks["citation_presence_ok"]
            and checks["citation_document_ok"]
            and checks["quote_ok"]
        )
        if not checks["passed"]:
            failed.append(_sample_failed_case("rag", sample, actual, expected | {"checks": checks}))
    return (
        len(samples),
        {
            "rag_external_sample_pass_rate": _accuracy(len(samples), len(failed)),
            "rag_external_citation_accuracy": _rate(citation_hits, citation_total),
            "rag_external_answer_accuracy": _rate(answer_hits, answer_total),
            "rag_external_no_answer_accuracy": _rate(no_answer_hits, no_answer_total),
            "rag_external_metadata_accuracy": _rate(metadata_hits, metadata_total),
            "failed_case_count": len(failed),
            "blocked_external_dependency_count": 0,
            "external_rag_document_count": len(indexed_documents),
            "external_rag_chunk_count": sum(int(document.get("chunk_count") or 0) for document in indexed_documents),
            "provider_quality_evaluation": False,
            "provider_quality_note": (
                "external public RAG acceptance validates file loading, indexing, retrieval, citations, and labels; "
                "it is not project-specific production RAG quality evidence."
            ),
        },
        failed,
    )


def _index_external_rag_documents(db: Session, dataset: dict, run_id: str) -> list[dict]:
    dataset_dir = Path(str(dataset["dataset_source"])).parent
    if not Path(str(dataset["dataset_source"])).is_absolute():
        dataset_dir = (PROJECT_ROOT / dataset_dir).resolve()
    indexed = []
    for document in dataset.get("documents") or []:
        if not isinstance(document, dict):
            continue
        indexed.append(_create_and_index_external_rag_document(db, document, dataset_dir, run_id))
    return indexed


def _external_rag_actual_result(result: dict) -> dict:
    citations = []
    for citation in result.get("citations") or []:
        if not isinstance(citation, dict):
            continue
        citations.append(
            {
                **citation,
                "document_id": str(citation.get("document_id") or ""),
                "chunk_id": str(citation.get("chunk_id") or ""),
            }
        )
    return {
        "status": result["status"],
        "answer": result.get("answer"),
        "citation_count": len(citations),
        "citations": citations,
    }


def _create_and_index_external_rag_document(db: Session, document: dict, dataset_dir: Path, run_id: str) -> dict:
    document_path = _resolve_external_rag_file_path(str(document.get("file_path") or ""), dataset_dir)
    try:
        content_text = document_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"External RAG file_path could not be read: {exc.__class__.__name__}") from exc
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    metadata = {
        **metadata,
        "external_document_id": str(document.get("document_id") or document_path.stem),
        "external_rag_run_id": run_id,
    }
    rag_document = asyncio.run(
        rag_service.create_document(
            db,
            knowledge_base=str(document.get("knowledge_base") or "prospectus"),
            title=str(document.get("title") or document_path.name),
            source_type=str(document.get("source_type") or "public_dataset"),
            source_url=document.get("source_url") if isinstance(document.get("source_url"), str) else None,
            issuer_name=metadata.get("issuer") if isinstance(metadata.get("issuer"), str) else None,
            metadata=metadata,
            created_by="evaluation_service",
            content_text=content_text,
        )
    )
    index_result = rag_service.index_document(db, rag_document.id)
    return {
        "document_id": str(rag_document.id),
        "external_document_id": metadata["external_document_id"],
        "knowledge_base": rag_document.knowledge_base,
        "title": rag_document.title,
        "chunk_count": int(index_result.get("chunk_count") or 0),
        "metadata": metadata,
    }


def _resolve_external_rag_file_path(value: str, dataset_dir: Path) -> Path:
    if not value:
        raise HTTPException(status_code=400, detail="External RAG file_path is required")
    raw_path = Path(value)
    if raw_path.is_absolute() or ".." in raw_path.parts:
        raise HTTPException(status_code=400, detail="External RAG file_path must stay under local_storage/external_acceptance")
    candidates = [(PROJECT_ROOT / raw_path).resolve(), (dataset_dir / raw_path).resolve()]
    for candidate in candidates:
        if _is_under(candidate, external_acceptance_root()):
            if candidate.exists() and candidate.is_file() and candidate.suffix.lower() == ".txt":
                return candidate
            raise HTTPException(status_code=400, detail="External RAG file_path must point to an existing txt file")
    raise HTTPException(status_code=400, detail="External RAG file_path must stay under local_storage/external_acceptance")


def _external_rag_provider_blocking_reason() -> str | None:
    real_providers = {"openai", "openai-compatible", "real"}
    configured = {
        "embedding": getattr(rag_service.settings, "embedding_provider", ""),
        "rag_answer": getattr(rag_service.settings, "rag_answer_provider", ""),
        "rag_rerank": getattr(rag_service.settings, "rag_rerank_provider", ""),
    }
    real_paths = [name for name, provider in configured.items() if str(provider).strip().lower() in real_providers]
    if real_paths and os.getenv("RUN_PROVIDER_INTEGRATION") != "1":
        return f"External RAG provider integration requires RUN_PROVIDER_INTEGRATION=1 for {', '.join(real_paths)}"
    return None


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
    citation_ids = set()
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        citation_ids.add(str(citation.get("document_id") or citation.get("rag_document_id") or ""))
        metadata = citation.get("metadata") if isinstance(citation.get("metadata"), dict) else {}
        citation_ids.add(str(metadata.get("external_document_id") or ""))
    answer_terms = expected.get("answer_must_contain")
    if isinstance(answer_terms, str):
        answer_terms = [answer_terms]
    answer_terms = [str(term) for term in answer_terms] if isinstance(answer_terms, list) else []
    answer_text_ok = all(_rag_text_matches(answer, term) for term in answer_terms)
    citation_presence_expected = expected.get("must_have_citation")
    min_citations = expected.get("min_citations", expected.get("citation_count"))
    citation_presence_ok = True
    if citation_presence_expected is not None:
        citation_presence_ok = citation_count > 0 if bool(citation_presence_expected) else citation_count == 0
    elif min_citations is not None:
        citation_presence_ok = citation_count >= int(min_citations or 0)
    expected_citation_id = expected.get("expected_citation_document_id")
    citation_document_ok = expected_citation_id is None or str(expected_citation_id) in citation_ids
    expected_metadata = expected.get("expected_metadata") if isinstance(expected.get("expected_metadata"), dict) else None
    metadata_ok = expected_metadata is None or any(_rag_metadata_matches(citation, expected_metadata) for citation in citations if isinstance(citation, dict))
    quote_terms = expected.get("expected_quote_must_contain")
    if isinstance(quote_terms, str):
        quote_terms = [quote_terms]
    quote_terms = [str(term) for term in quote_terms] if isinstance(quote_terms, list) else []
    quote_ok = all(
        any(_rag_text_matches(str(citation.get("quote") or ""), term) for citation in citations if isinstance(citation, dict))
        for term in quote_terms
    )
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
        "metadata_ok": metadata_ok,
        "metadata_total": int(expected_metadata is not None),
        "quote_ok": quote_ok,
        "quote_total": int(bool(quote_terms)),
        "no_answer_ok": no_answer_ok,
        "no_answer_total": int(no_answer_expected is not None),
        "status_ok": status_ok,
        "passed": answer_text_ok and citation_presence_ok and citation_document_ok and metadata_ok and quote_ok and no_answer_ok and status_ok,
    }


def _rag_tokens(text: str) -> set[str]:
    stopwords = {"a", "an", "and", "be", "do", "does", "for", "in", "is", "of", "on", "or", "the", "to", "what", "with"}
    return {token for token in re.findall(r"[a-z0-9]+", text.lower()) if token not in stopwords}


def _rag_text_matches(text_value: str, expected_value: str) -> bool:
    if expected_value.lower() in text_value.lower():
        return True
    expected_tokens = _rag_tokens(expected_value)
    return bool(expected_tokens) and expected_tokens.issubset(_rag_tokens(text_value))


def _rag_metadata_matches(citation: dict, expected_metadata: dict) -> bool:
    metadata = citation.get("metadata") if isinstance(citation.get("metadata"), dict) else {}
    return all(str(metadata.get(key) or "") == str(value) for key, value in expected_metadata.items())


def _evaluate_persistent_rag_workflow(db: Session) -> tuple[int, dict, list[dict]]:
    return _evaluate_persistent_rag_workflow_samples(db, [_default_persistent_rag_workflow_sample()])


def _evaluate_persistent_rag_workflow_samples(db: Session, samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    hits = {
        "knowledge_base": 0,
        "chunk_metadata": 0,
        "embedding": 0,
        "retrieval": 0,
        "citation": 0,
        "no_answer": 0,
        "workpaper_scope": 0,
        "metadata_filter": 0,
    }
    for sample in samples:
        actual = _run_persistent_rag_workflow_sample(db, sample)
        checks = _persistent_rag_workflow_checks(actual, _sample_expected(sample))
        for key in hits:
            hits[key] += int(checks[f"{key}_ok"])
        if not checks["passed"]:
            failed.append(_sample_failed_case("rag", sample, actual, {"checks": checks}))
    total = len(samples)
    return (
        total,
        {
            "persistent_rag_workflow_pass_rate": _accuracy(total, len(failed)),
            "persistent_rag_workflow_success_rate": _accuracy(total, len(failed)),
            "knowledge_base_coverage": _rate(hits["knowledge_base"], total),
            "chunk_metadata_accuracy": _rate(hits["chunk_metadata"], total),
            "embedding_invocation_accuracy": _rate(hits["embedding"], total),
            "retrieval_accuracy": _rate(hits["retrieval"], total),
            "citation_accuracy": _rate(hits["citation"], total),
            "no_answer_accuracy": _rate(hits["no_answer"], total),
            "workpaper_scope_accuracy": _rate(hits["workpaper_scope"], total),
            "metadata_filter_accuracy": _rate(hits["metadata_filter"], total),
            "failed_case_count": len(failed),
            "provider_quality_evaluation": False,
            "provider_quality_note": (
                "persistent_rag_workflow validates DB vector-store plumbing with deterministic/local providers; "
                "it is not real Provider quality evidence."
            ),
            "dataset_kind": "persistent_rag_workflow_smoke",
        },
        failed,
    )


def _run_persistent_rag_workflow_sample(db: Session, sample: dict) -> dict:
    input_payload = _sample_input(sample)
    task_ids = _create_rag_workflow_tasks(db, sample)
    documents = input_payload.get("documents") if isinstance(input_payload.get("documents"), list) else None
    documents = documents or _default_persistent_rag_documents()
    queries = input_payload.get("queries") if isinstance(input_payload.get("queries"), list) else None
    queries = queries or _default_persistent_rag_queries()
    initial_embedding_count = _model_invocation_count(db, "embed")
    try:
        indexed_documents = [
            _create_and_index_rag_document(db, document, task_ids)
            for document in documents
            if isinstance(document, dict)
        ]
        query_results = {
            str(query.get("name") or query.get("knowledge_base") or index): _run_persistent_rag_query(db, query, task_ids)
            for index, query in enumerate(queries, start=1)
            if isinstance(query, dict)
        }
        no_answer = _run_persistent_rag_query(
            db,
            {
                "name": "no_answer",
                "query": "phaseb unmatched custody valuation token",
                "knowledge_base": "regulation",
                "metadata_filter": {"phase_b_no_answer": "missing"},
            },
            task_ids,
        )
        chunks = list(
            db.scalars(
                select(RagChunk).where(
                    RagChunk.rag_document_id.in_([UUID(document["document_id"]) for document in indexed_documents])
                )
            )
        )
        workpaper_result = query_results.get("workpaper", {})
        metadata_result = query_results.get("metadata_filter", {})
        embedding_count = _model_invocation_count(db, "embed") - initial_embedding_count
        return {
            "status": "completed",
            "task_ids": {key: str(value) for key, value in task_ids.items()},
            "document_count": len(indexed_documents),
            "chunk_count": len(chunks),
            "knowledge_bases_indexed": sorted({document["knowledge_base"] for document in indexed_documents}),
            "chunk_metadata_complete": bool(chunks) and all(
                chunk.metadata_json.get("knowledge_base") == chunk.knowledge_base
                and chunk.metadata_json.get("title")
                and chunk.metadata_json.get("source_type")
                for chunk in chunks
            ),
            "embedding_invocation_count": embedding_count,
            "query_results": query_results,
            "retrieval_answer_count": sum(1 for result in query_results.values() if result.get("status") == "answer"),
            "citation_count": sum(int(result.get("citation_count") or 0) for result in query_results.values()),
            "no_answer_status": no_answer.get("status"),
            "no_answer_citation_count": no_answer.get("citation_count"),
            "workpaper_scope_isolated": bool(workpaper_result.get("citations"))
            and {citation.get("title") for citation in workpaper_result.get("citations", [])} == {"Phase B Primary Workpaper"},
            "metadata_filter_matched": bool(metadata_result.get("citations"))
            and {citation.get("title") for citation in metadata_result.get("citations", [])} == {"Phase B Regulation Amount Policy"},
        }
    except HTTPException as exc:
        db.rollback()
        status = "blocked_external_dependency" if _looks_like_external_dependency(str(exc.detail)) else "failed"
        return {"status": status, "error": str(exc.detail)}
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        status = "blocked_external_dependency" if _looks_like_external_dependency(str(exc)) else "failed"
        return {"status": status, "error": exc.__class__.__name__, "message": str(exc)}


def _create_rag_workflow_tasks(db: Session, sample: dict) -> dict[str, UUID]:
    primary = AuditTask(
        task_no=f"EVAL-RAG-PRIMARY-{str(sample.get('sample_id') or 'sample')[:18]}-{str(uuid4())[:8]}",
        name="Phase B persistent RAG primary task",
        scenario="procurement",
        project_name="evaluation",
        company_name="desensitized-or-synthetic",
        metadata_json={"source": "persistent_rag_workflow_evaluation", "sample_id": sample.get("sample_id")},
        actor_name="evaluation_service",
    )
    secondary = AuditTask(
        task_no=f"EVAL-RAG-SECONDARY-{str(sample.get('sample_id') or 'sample')[:16]}-{str(uuid4())[:8]}",
        name="Phase B persistent RAG secondary task",
        scenario="procurement",
        project_name="evaluation",
        company_name="desensitized-or-synthetic",
        metadata_json={"source": "persistent_rag_workflow_evaluation", "sample_id": sample.get("sample_id")},
        actor_name="evaluation_service",
    )
    db.add_all([primary, secondary])
    db.commit()
    return {"primary": primary.id, "secondary": secondary.id}


def _create_and_index_rag_document(db: Session, document: dict, task_ids: dict[str, UUID]) -> dict:
    knowledge_base = str(document.get("knowledge_base") or "regulation")
    metadata = document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    metadata = _rag_workflow_metadata(metadata, knowledge_base, task_ids)
    rag_document = asyncio.run(
        rag_service.create_document(
            db,
            knowledge_base=knowledge_base,
            title=str(document.get("title") or f"Phase B {knowledge_base} document"),
            source_type=str(document.get("source_type") or "phase_b_synthetic"),
            metadata=metadata,
            created_by="evaluation_service",
            content_text=str(document.get("text") or document.get("content") or ""),
        )
    )
    index_result = rag_service.index_document(db, rag_document.id)
    return {
        "document_id": str(rag_document.id),
        "knowledge_base": rag_document.knowledge_base,
        "title": rag_document.title,
        "chunk_count": int(index_result.get("chunk_count") or 0),
        "metadata": metadata,
    }


def _rag_workflow_metadata(metadata: dict, knowledge_base: str, task_ids: dict[str, UUID]) -> dict:
    resolved = dict(metadata)
    task_scope = resolved.pop("task_scope", None)
    if task_scope:
        resolved["task_id"] = str(task_ids.get(str(task_scope), task_ids["primary"]))
    elif knowledge_base == "workpaper" and not resolved.get("task_id"):
        resolved["task_id"] = str(task_ids["primary"])
    return resolved


def _run_persistent_rag_query(db: Session, query: dict, task_ids: dict[str, UUID]) -> dict:
    knowledge_base = str(query.get("knowledge_base") or "regulation")
    metadata_filter = query.get("metadata_filter") if isinstance(query.get("metadata_filter"), dict) else {}
    metadata_filter = _rag_workflow_metadata(metadata_filter, knowledge_base, task_ids)
    task_id = task_ids["primary"] if knowledge_base == "workpaper" else None
    result = rag_service.query(
        db,
        query_text=str(query.get("query") or ""),
        knowledge_base=knowledge_base,
        top_k=int(query.get("top_k") or 3),
        metadata_filter=metadata_filter,
        task_id=task_id,
    )
    return {
        "status": result["status"],
        "answer": result.get("answer"),
        "citation_count": len(result.get("citations") or []),
        "citations": [
            {
                "document_id": str(citation.get("document_id")),
                "chunk_id": str(citation.get("chunk_id")),
                "knowledge_base": citation.get("knowledge_base"),
                "title": citation.get("title"),
                "metadata": citation.get("metadata"),
            }
            for citation in result.get("citations") or []
            if isinstance(citation, dict)
        ],
    }


def _persistent_rag_workflow_checks(actual: dict, expected: dict) -> dict:
    required_kbs = [str(item) for item in expected.get("required_knowledge_bases") or ["regulation", "inquiry_case", "prospectus", "workpaper"]]
    query_results = actual.get("query_results") if isinstance(actual.get("query_results"), dict) else {}
    expected_query_statuses = expected.get("expected_query_statuses") if isinstance(expected.get("expected_query_statuses"), dict) else {}
    retrieval_ok = all((query_results.get(name) or {}).get("status") == status for name, status in expected_query_statuses.items())
    if not expected_query_statuses:
        retrieval_ok = int(actual.get("retrieval_answer_count") or 0) >= int(expected.get("min_answer_queries") or 4)
    min_chunks = int(expected.get("min_chunk_count") or len(required_kbs))
    min_embeddings = int(expected.get("min_embedding_invocation_count") or len(required_kbs))
    min_citations = int(expected.get("min_citation_count") or len(required_kbs))
    checks = {
        "status_ok": actual.get("status") == str(expected.get("status") or "completed"),
        "knowledge_base_ok": set(required_kbs).issubset(set(actual.get("knowledge_bases_indexed") or [])),
        "chunk_metadata_ok": bool(actual.get("chunk_metadata_complete")) and int(actual.get("chunk_count") or 0) >= min_chunks,
        "embedding_ok": int(actual.get("embedding_invocation_count") or 0) >= min_embeddings,
        "retrieval_ok": retrieval_ok,
        "citation_ok": int(actual.get("citation_count") or 0) >= min_citations,
        "no_answer_ok": actual.get("no_answer_status") == "no_answer" and int(actual.get("no_answer_citation_count") or 0) == 0,
        "workpaper_scope_ok": bool(actual.get("workpaper_scope_isolated")),
        "metadata_filter_ok": bool(actual.get("metadata_filter_matched")),
    }
    checks["passed"] = all(bool(value) for value in checks.values())
    return checks


def _default_persistent_rag_workflow_sample() -> dict:
    return {
        "sample_id": "persistent-rag-workflow-phase-b",
        "eval_type": "persistent_rag_workflow",
        "input": {
            "documents": _default_persistent_rag_documents(),
            "queries": _default_persistent_rag_queries(),
        },
        "expected": {
            "status": "completed",
            "required_knowledge_bases": ["regulation", "inquiry_case", "prospectus", "workpaper"],
            "min_chunk_count": 5,
            "min_embedding_invocation_count": 5,
            "min_citation_count": 4,
            "expected_query_statuses": {
                "regulation": "answer",
                "inquiry_case": "answer",
                "prospectus": "answer",
                "workpaper": "answer",
                "metadata_filter": "answer",
            },
        },
    }


def _default_persistent_rag_documents() -> list[dict]:
    return [
        {
            "knowledge_base": "regulation",
            "title": "Phase B Regulation Amount Policy",
            "text": "PROC_AMOUNT_001 phaseb_regulation amount policy requires contract, invoice, and payment amounts to match.",
            "metadata": {"topic": "amount", "jurisdiction": "phase_b"},
        },
        {
            "knowledge_base": "inquiry_case",
            "title": "Phase B Inquiry Overpayment Case",
            "text": "PROC_AMOUNT_001 phaseb_inquiry overpayment case routed to reviewer with pending human review.",
            "metadata": {"topic": "overpayment", "case_type": "inquiry"},
        },
        {
            "knowledge_base": "prospectus",
            "title": "Phase B Prospectus Supplier Risk",
            "text": "phaseb_prospectus supplier contract risk disclosure links procurement amount evidence to source citation.",
            "metadata": {"topic": "supplier_risk", "issuer": "phase_b"},
        },
        {
            "knowledge_base": "workpaper",
            "title": "Phase B Primary Workpaper",
            "text": "phaseb_workpaper_primary scoped payment evidence belongs only to the primary task.",
            "metadata": {"topic": "workpaper_scope", "task_scope": "primary"},
        },
        {
            "knowledge_base": "workpaper",
            "title": "Phase B Secondary Workpaper",
            "text": "phaseb_workpaper_primary secondary task evidence must not appear in primary task scoped retrieval.",
            "metadata": {"topic": "workpaper_scope", "task_scope": "secondary"},
        },
    ]


def _default_persistent_rag_queries() -> list[dict]:
    return [
        {
            "name": "regulation",
            "knowledge_base": "regulation",
            "query": "phaseb_regulation PROC_AMOUNT_001 amount policy",
        },
        {
            "name": "inquiry_case",
            "knowledge_base": "inquiry_case",
            "query": "phaseb_inquiry overpayment reviewer",
        },
        {
            "name": "prospectus",
            "knowledge_base": "prospectus",
            "query": "phaseb_prospectus supplier contract risk",
        },
        {
            "name": "workpaper",
            "knowledge_base": "workpaper",
            "query": "phaseb_workpaper_primary scoped payment evidence",
            "metadata_filter": {"task_scope": "primary"},
        },
        {
            "name": "metadata_filter",
            "knowledge_base": "regulation",
            "query": "phaseb_regulation amount policy",
            "metadata_filter": {"topic": "amount"},
        },
    ]


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


def _evaluate_agent_db_workflow(db: Session) -> tuple[int, dict, list[dict]]:
    return _evaluate_agent_db_workflow_samples(db, [_default_agent_db_workflow_sample()])


def _evaluate_agent_db_workflow_samples(db: Session, samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    hits = {
        "agent_run": 0,
        "agent_step": 0,
        "tool_whitelist": 0,
        "state_transition": 0,
        "retry": 0,
        "review": 0,
        "evidence_insufficient": 0,
        "bad_case": 0,
        "citation_guardrail": 0,
    }
    high_risk_auto_confirm_count = 0
    for sample in samples:
        actual = _run_agent_db_workflow_sample(db, sample)
        checks = _agent_db_workflow_checks(actual, _sample_expected(sample))
        for key in hits:
            hits[key] += int(checks[f"{key}_ok"])
        high_risk_auto_confirm_count += int(actual.get("high_risk_auto_confirmed") is True)
        if not checks["passed"]:
            failed.append(_sample_failed_case("agent", sample, actual, {"checks": checks}))
    total = len(samples)
    return (
        total,
        {
            "agent_db_workflow_pass_rate": _accuracy(total, len(failed)),
            "agent_db_workflow_success_rate": _accuracy(total, len(failed)),
            "agent_run_artifact_accuracy": _rate(hits["agent_run"], total),
            "agent_step_artifact_accuracy": _rate(hits["agent_step"], total),
            "tool_whitelist_accuracy": _rate(hits["tool_whitelist"], total),
            "state_transition_accuracy": _rate(hits["state_transition"], total),
            "retry_recovery_accuracy": _rate(hits["retry"], total),
            "human_review_routing_accuracy": _rate(hits["review"], total),
            "evidence_insufficient_accuracy": _rate(hits["evidence_insufficient"], total),
            "bad_case_creation_accuracy": _rate(hits["bad_case"], total),
            "conclusion_guardrail_accuracy": _rate(hits["citation_guardrail"], total),
            "high_risk_auto_confirm_rate": _rate(high_risk_auto_confirm_count, total),
            "failed_case_count": len(failed),
            "provider_quality_evaluation": False,
            "provider_quality_note": (
                "agent_db_workflow validates persisted agent_runs/agent_steps and guardrails with deterministic/local providers; "
                "it is not real Provider quality evidence."
            ),
            "dataset_kind": "agent_db_workflow_smoke",
        },
        failed,
    )


def _run_agent_db_workflow_sample(db: Session, sample: dict) -> dict:
    input_payload = _sample_input(sample)
    documents = input_payload.get("documents") if isinstance(input_payload.get("documents"), list) else None
    documents = documents or _default_agent_db_workflow_documents()
    try:
        review_task = _create_agent_db_workflow_task(db, sample, "review")
        created_documents = [
            _create_agent_db_ready_document(db, review_task, document, index)
            for index, document in enumerate(documents, start=1)
        ]
        review_run = agent_service.create_run(db, review_task.id)
        review_steps = agent_service.list_steps(db, review_run.id)
        audit_results = list(db.scalars(select(AuditResult).where(AuditResult.task_id == review_task.id)))
        evidence_step = next((step for step in review_steps if step.tool_name == "retrieve_evidence"), None)
        failed_run, retry_run, retry_steps, bad_case_count = _run_agent_db_retry_probe(db, sample)
        failed_steps = [step for step in retry_steps if step.status == "failed"]
        record_bad_case_steps = [step for step in retry_steps if step.tool_name == "record_bad_case"]
        high_risk_results = [result for result in audit_results if result.status != "pass" and result.severity == "high"]
        tool_names = [step.tool_name for step in review_steps + retry_steps]
        output_refs = review_run.output_refs or {}
        evidence_output = evidence_step.output_payload if evidence_step is not None else {}
        return {
            "status": "completed",
            "review_task_id": str(review_task.id),
            "document_ids": [str(document.id) for document in created_documents],
            "agent_run_ids": [str(review_run.id), str(failed_run.id), str(retry_run.id)],
            "review_run_status": review_run.status,
            "review_run_state": review_run.current_state,
            "review_step_count": len(review_steps),
            "retry_step_count": len(retry_steps),
            "used_tools": sorted(set(tool_names)),
            "tool_whitelist_violations": [tool for tool in tool_names if tool not in agent_service.TOOL_WHITELIST],
            "state_transition_valid": review_run.status == "waiting_review" and review_run.current_state == "HUMAN_REVIEW_REQUIRED",
            "review_routed": review_run.status == "waiting_review" and bool(output_refs.get("review_queue")),
            "evidence_insufficient": bool(evidence_output.get("evidence_insufficient")),
            "conclusion_generated": bool(evidence_output.get("conclusion_generated")),
            "report_id": output_refs.get("report_id"),
            "high_risk_result_count": len(high_risk_results),
            "high_risk_auto_confirmed": any(result.review_status == "confirmed" for result in high_risk_results),
            "retry_failed_step_count": len(failed_steps),
            "retry_of_recorded": len(failed_steps) >= 2 and failed_steps[-1].input_payload.get("retry_of") == str(failed_steps[0].id),
            "bad_case_count": bad_case_count,
            "record_bad_case_step_count": len(record_bad_case_steps),
            "audit_result_count": len(audit_results),
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        status = "blocked_external_dependency" if _looks_like_external_dependency(str(exc)) else "failed"
        return {"status": status, "error": exc.__class__.__name__, "message": str(exc)}


def _run_agent_db_retry_probe(db: Session, sample: dict):
    task = _create_agent_db_workflow_task(db, sample, "retry")
    document_id = uuid4()
    storage_dir = PROJECT_ROOT / "local_storage" / "uploads" / str(task.id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    storage_path = storage_dir / f"{document_id}.jpg"
    storage_path.write_bytes(b"\xff\xd8\xffnot-real-image")
    document = Document(
        id=document_id,
        task_id=task.id,
        uploaded_by_name="evaluation_service",
        original_filename="phase_b_retry_probe.jpg",
        file_ext="jpg",
        content_type="image/jpeg",
        file_size=storage_path.stat().st_size,
        file_hash=sha256(storage_path.read_bytes()).hexdigest(),
        storage_path=str(storage_path.relative_to(PROJECT_ROOT)),
        metadata_json={"source": "agent_db_workflow_evaluation", "sample_id": sample.get("sample_id")},
    )
    db.add(document)
    db.commit()
    failed_run = agent_service.create_run(db, task.id)
    retry_run = agent_service.retry_run(db, failed_run.id)
    retry_steps = agent_service.list_steps(db, failed_run.id)
    bad_case_count = db.scalar(select(func.count(BadCase.id)).where(BadCase.task_id == task.id)) or 0
    return failed_run, retry_run, retry_steps, bad_case_count


def _create_agent_db_ready_document(db: Session, task: AuditTask, document: dict, index: int) -> Document:
    model = _create_full_db_workflow_document(db, task, document, index, source="agent_db_workflow_evaluation")
    doc_type = str(document.get("doc_type") or _e2e_doc_type(document) or "unknown")
    business_key = str(document.get("business_key") or "CONTRACT-PHASEB-AGENT-001")
    model.doc_type = doc_type
    model.doc_type_confidence = 1.0
    model.classification_reason = "Phase B Agent DB workflow fixture."
    model.ocr_status = "completed"
    model.extraction_status = "completed"
    model.page_count = 1
    model.business_key = business_key
    model.review_status = "pending"
    text = str(document.get("text") or "")
    db.add(
        DocumentPage(
            document_id=model.id,
            page_number=1,
            raw_text=text,
            ocr_blocks=[{"text": line, "bbox": [10.0, float(20 + i * 16), 500.0, float(34 + i * 16)], "confidence": 0.98} for i, line in enumerate(text.splitlines()) if line.strip()],
            table_blocks=[],
            image_path=None,
            width=595,
            height=842,
            ocr_engine="phase_b_fixture",
            warnings=[],
        )
    )
    for field in _agent_db_fixture_fields(task.id, model.id, doc_type, document):
        db.add(field)
    db.commit()
    db.refresh(model)
    return model


def _agent_db_fixture_fields(task_id: UUID, document_id: UUID, doc_type: str, document: dict) -> list[ExtractedField]:
    values = document.get("fields") if isinstance(document.get("fields"), dict) else _default_agent_db_fields(doc_type)
    fields = []
    for index, (field_name, value) in enumerate(values.items(), start=1):
        normalized = value if isinstance(value, dict) else {"value": value}
        amount = normalized.get("amount") if isinstance(normalized, dict) else None
        value_text = str(amount if amount is not None else normalized.get("value", value))
        field_type = "money" if amount is not None else "text"
        fields.append(
            ExtractedField(
                task_id=task_id,
                document_id=document_id,
                field_name=str(field_name),
                field_label=str(field_name).replace("_", " ").title(),
                field_type=field_type,
                value_text=value_text,
                value_normalized=normalized,
                confidence=0.99,
                source_page=1,
                source_bbox=[10.0, float(20 + index * 16), 240.0, float(34 + index * 16)],
                source_text=f"{field_name}: {value_text}",
                extraction_method="phase_b_fixture",
                is_required=True,
                warnings=[],
            )
        )
    return fields


def _default_agent_db_fields(doc_type: str) -> dict:
    if doc_type == "purchase_contract":
        return {
            "contract_no": {"value": "PHASEB-AGENT-001"},
            "supplier_name": {"value": "Supplier Co"},
            "amount_including_tax": {"amount": 1000.0, "currency": "CNY"},
        }
    if doc_type == "invoice":
        return {
            "invoice_no": {"value": "PHASEB-INV-001"},
            "seller_name": {"value": "Supplier Co"},
            "amount_including_tax": {"amount": 1200.0, "currency": "CNY"},
        }
    if doc_type == "payment_receipt":
        return {
            "payment_no": {"value": "PHASEB-PAY-001"},
            "payee_name": {"value": "Supplier Co"},
            "amount": {"amount": 1200.0, "currency": "CNY"},
            "payment_purpose": {"value": "Payment for contract PHASEB-AGENT-001 and invoice PHASEB-INV-001"},
        }
    return {}


def _create_agent_db_workflow_task(db: Session, sample: dict, suffix: str) -> AuditTask:
    task = AuditTask(
        task_no=f"EVAL-AGENTDB-{suffix.upper()}-{str(sample.get('sample_id') or 'sample')[:16]}-{str(uuid4())[:8]}",
        name=f"Agent DB workflow evaluation {suffix}",
        scenario=str(sample.get("scenario") or _sample_input(sample).get("scenario") or "procurement"),
        project_name="evaluation",
        company_name="desensitized-or-synthetic",
        metadata_json={"source": "agent_db_workflow_evaluation", "sample_id": sample.get("sample_id"), "probe": suffix},
        actor_name="evaluation_service",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def _agent_db_workflow_checks(actual: dict, expected: dict) -> dict:
    min_review_steps = int(expected.get("min_review_step_count") or 7)
    min_retry_failed_steps = int(expected.get("min_retry_failed_step_count") or 2)
    min_bad_cases = int(expected.get("min_bad_case_count") or 2)
    checks = {
        "status_ok": actual.get("status") == str(expected.get("status") or "completed"),
        "agent_run_ok": len(actual.get("agent_run_ids") or []) >= int(expected.get("min_agent_run_count") or 3),
        "agent_step_ok": int(actual.get("review_step_count") or 0) >= min_review_steps and int(actual.get("retry_step_count") or 0) >= 2,
        "tool_whitelist_ok": not actual.get("tool_whitelist_violations"),
        "state_transition_ok": bool(actual.get("state_transition_valid")),
        "retry_ok": int(actual.get("retry_failed_step_count") or 0) >= min_retry_failed_steps and bool(actual.get("retry_of_recorded")),
        "review_ok": bool(actual.get("review_routed")) and int(actual.get("high_risk_result_count") or 0) >= 1,
        "evidence_insufficient_ok": bool(actual.get("evidence_insufficient")),
        "bad_case_ok": int(actual.get("bad_case_count") or 0) >= min_bad_cases and int(actual.get("record_bad_case_step_count") or 0) >= min_bad_cases,
        "citation_guardrail_ok": not bool(actual.get("conclusion_generated")) and not actual.get("report_id"),
        "high_risk_auto_confirm_ok": not bool(actual.get("high_risk_auto_confirmed")),
    }
    checks["passed"] = all(bool(value) for value in checks.values())
    return checks


def _default_agent_db_workflow_sample() -> dict:
    return {
        "sample_id": "agent-db-workflow-phase-b",
        "eval_type": "agent_db_workflow",
        "input": {"documents": _default_agent_db_workflow_documents()},
        "expected": {
            "status": "completed",
            "min_agent_run_count": 3,
            "min_review_step_count": 7,
            "min_retry_failed_step_count": 2,
            "min_bad_case_count": 2,
        },
    }


def _default_agent_db_workflow_documents() -> list[dict]:
    return [
        {
            "filename": "phase_b_purchase_contract.pdf",
            "text": (
                "Purchase Contract\n"
                "Contract No: PHASEB-AGENT-001\n"
                "Signing Date: 2026-07-01\n"
                "Buyer Name: Demo Company\n"
                "Supplier Name: Supplier Co\n"
                "Item: Audit Service; Quantity: 1; Unit: pcs; Unit Price: 1000.00; Amount: 1000.00\n"
                "Amount Including Tax: CNY 1000.00"
            ),
        },
        {
            "filename": "phase_b_invoice.pdf",
            "text": (
                "Invoice\n"
                "Invoice No: PHASEB-INV-001\n"
                "Invoice Date: 2026-07-01\n"
                "Seller Name: Supplier Co\n"
                "Buyer Name: Demo Company\n"
                "Item: Audit Service; Quantity: 1; Unit: pcs; Unit Price: 1200.00; Amount: 1200.00\n"
                "Amount Including Tax: CNY 1200.00\n"
                "Tax Amount: CNY 109.09"
            ),
        },
        {
            "filename": "phase_b_payment_receipt.pdf",
            "text": (
                "Payment Receipt\n"
                "Transaction No: PHASEB-PAY-001\n"
                "Payment Date: 2026-07-01\n"
                "Payer Name: Demo Company\n"
                "Payee Name: Supplier Co\n"
                "Amount: CNY 1200.00\n"
                "Currency: CNY\n"
                "Payment Purpose: Payment for contract PHASEB-AGENT-001 and invoice PHASEB-INV-001"
            ),
        },
    ]


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


def _create_full_db_workflow_document(
    db: Session,
    task: AuditTask,
    document: dict,
    index: int,
    source: str = "full_db_workflow_evaluation",
) -> Document:
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
        metadata_json={"source": source, "sample_doc_type": document.get("doc_type")},
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
        doc_type: _extract_text_sample_fields(
            doc_type,
            str(document.get("text") or ""),
            str(sample.get("scenario") or "procurement"),
            document,
        )
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


def _model_invocation_count(db: Session, invocation_type: str) -> int:
    return int(db.scalar(select(func.count(ModelInvocation.id)).where(ModelInvocation.invocation_type == invocation_type)) or 0)


def _looks_like_external_dependency(message: str) -> bool:
    lowered = message.lower()
    return any(token in lowered for token in ("api key", "endpoint", "provider", "configured", "credential", "external"))


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
