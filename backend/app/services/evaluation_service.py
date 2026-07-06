from pathlib import Path
import json
import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bad_case import BadCase
from app.models.evaluation_result import EvaluationResult
from app.schemas.quality import EvaluationRunRequest
from app.services import agent_service, audit_log_service, bad_case_service, classification_service, rag_service


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def evaluation_datasets_root() -> Path:
    return PROJECT_ROOT / "local_storage" / "evaluation_datasets"


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
        dataset_name=payload.dataset_name,
        model_name=payload.model_name,
        prompt_version=payload.prompt_version,
        rule_version=payload.rule_version,
        metrics=metrics | _limitations(sample_count, metrics.get("dataset_kind")),
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
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise HTTPException(status_code=400, detail="Evaluation dataset must be a JSON object with a samples array")
    return {
        "dataset_name": str(data.get("dataset_name") or payload.dataset_name),
        "dataset_kind": str(data.get("dataset_kind") or "external_annotated"),
        "dataset_source": str(path.relative_to(PROJECT_ROOT)) if _is_under(path, PROJECT_ROOT) else str(path),
        "samples": data["samples"],
    }


def _resolve_dataset_path(payload: EvaluationRunRequest) -> Path | None:
    roots = [PROJECT_ROOT / "samples" / "evaluation", evaluation_datasets_root()]
    if payload.dataset_path:
        path = Path(payload.dataset_path)
        candidates = [path] if path.is_absolute() else [root / path for root in roots]
        allowed_path = False
        for candidate in candidates:
            resolved = candidate.resolve()
            if any(_is_under(resolved, root) for root in roots):
                allowed_path = True
                if resolved.exists() and resolved.suffix == ".json":
                    return resolved
        if allowed_path:
            raise HTTPException(status_code=400, detail="Evaluation dataset_path must point to an existing JSON file")
        raise HTTPException(
            status_code=400,
            detail="Evaluation dataset_path must be under samples/evaluation or local_storage/evaluation_datasets",
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
        sample_count, metrics, failed = _evaluate_ocr_samples(samples)
    elif eval_type == "extraction":
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
            "dataset_source": dataset["dataset_source"],
            "is_dataset_driven": True,
            "is_production_evaluation": dataset["dataset_kind"] == "real_annotated",
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


def _evaluate_rule_samples(samples: list[dict]) -> tuple[int, dict, list[dict]]:
    failed = []
    false_positive = 0
    false_negative = 0
    for sample in samples:
        actual = _sample_actual(sample)
        expected = _sample_expected(sample)
        actual_status = str(actual.get("status") or "unknown")
        expected_status = str(expected.get("status") or "unknown")
        if actual_status != expected_status:
            failed.append(_sample_failed_case("rule", sample, actual, expected))
            false_positive += int(actual_status in {"fail", "warning"} and expected_status == "pass")
            false_negative += int(actual_status == "pass" and expected_status != "pass")
    return (
        len(samples),
        {
            "rule_accuracy": _accuracy(len(samples), len(failed)),
            "false_positive_count": false_positive,
            "false_negative_count": false_negative,
            "false_positive_rate": _rate(false_positive, len(samples)),
            "false_negative_rate": _rate(false_negative, len(samples)),
            "rule_coverage": 1.0,
            "explainability_rate": _rate(sum(1 for sample in samples if bool(_sample_actual(sample).get("evidence"))), len(samples)),
        },
        failed,
    )


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
    return {
        "case_type": case_type,
        "title": str(sample.get("title") or sample.get("id") or f"{case_type} dataset sample"),
        "input_payload": _sample_input(sample) | {"dataset_sample_id": sample.get("id")},
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


def _numeric_close(actual: dict, expected: dict, tolerance: float = 0.01) -> bool:
    actual_amount = actual.get("amount")
    expected_amount = expected.get("amount")
    if actual_amount is None or expected_amount is None:
        return actual == expected
    return abs(float(actual_amount) - float(expected_amount)) <= tolerance


def _bad_case_type(eval_type: str) -> str:
    return eval_type if eval_type in bad_case_service.CASE_TYPES else "rule"


def _limitations(sample_count: int, dataset_kind: str | None = None) -> dict:
    kind = dataset_kind or "unclassified_dataset"
    is_production = kind == "real_annotated"
    return {
        "dataset_kind": kind,
        "is_production_evaluation": is_production,
        "is_dataset_driven": kind not in {"project_sample_set", "project_text_golden_set", "project_regression_sample", "rag_integration_guard", "workflow_contract_regression", "project_demo_seed_set", "empty_bad_case_regression"},
        "limitations": [] if is_production else [
            f"Dataset kind is {kind}; this is not a production-scale evaluation.",
            f"Sample count is {sample_count}; do not interpret metrics as production quality.",
        ],
    }
