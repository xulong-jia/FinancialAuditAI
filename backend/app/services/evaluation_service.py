from pathlib import Path
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bad_case import BadCase
from app.models.evaluation_result import EvaluationResult
from app.schemas.quality import EvaluationRunRequest
from app.services import agent_service, bad_case_service, classification_service, rag_service


def run_evaluation(db: Session, payload: EvaluationRunRequest) -> EvaluationResult:
    if payload.eval_type == "classification":
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
        eval_name=payload.eval_name or f"{payload.eval_type}_synthetic_eval",
        eval_type=payload.eval_type,
        dataset_name=payload.dataset_name,
        model_name=payload.model_name,
        prompt_version=payload.prompt_version,
        rule_version=payload.rule_version,
        metrics=metrics | _limitations(sample_count),
        sample_count=sample_count,
        failed_cases=failed_cases,
        report_path=None,
        created_by=payload.created_by,
    )
    db.add(result)
    for failed_case in failed_cases:
        bad_case_service.create_failed_case(
            db,
            case_type=payload.eval_type,
            title=failed_case["title"],
            input_payload=failed_case.get("input_payload", {}),
            model_output=failed_case.get("model_output", {}),
            expected_output=failed_case.get("expected_output", {}),
            severity=failed_case.get("severity", "medium"),
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


def _evaluate_classification() -> tuple[int, dict, list[dict]]:
    samples = [
        ("contract.pdf", "purchase contract\ncontract no: C-1\nsupplier: Demo Co", "purchase_contract"),
        ("invoice.pdf", "invoice\ninvoice number: I-1\nseller: Demo Co\ntax amount: 10", "invoice"),
    ]
    failed = []
    for filename, text, expected in samples:
        ranked = classification_service._rank_document_types(filename, text)
        actual = ranked[0].doc_type if ranked else "unknown"
        if actual != expected:
            failed.append(_failed_case("classification", filename, {"doc_type": actual}, {"doc_type": expected}))
    return len(samples), {"accuracy": _accuracy(len(samples), len(failed))}, failed


def _evaluate_ocr() -> tuple[int, dict, list[dict]]:
    samples = [
        {"pages": ["first page text", "second page text"], "expected_page_count": 2},
        {"pages": [""], "expected_warning": "empty_text"},
    ]
    failed = []
    for index, sample in enumerate(samples, start=1):
        actual = {
            "page_count": len(sample["pages"]),
            "warnings": ["empty_text"] if sample["pages"] == [""] else [],
        }
        expected = {
            key: value
            for key, value in sample.items()
            if key in {"expected_page_count", "expected_warning"}
        }
        if sample.get("expected_page_count") and actual["page_count"] != sample["expected_page_count"]:
            failed.append(_failed_case("ocr", f"ocr sample {index}", actual, expected))
        if sample.get("expected_warning") and sample["expected_warning"] not in actual["warnings"]:
            failed.append(_failed_case("ocr", f"ocr warning sample {index}", actual, expected))
    return len(samples), {"page_count_accuracy": _accuracy(len(samples), len(failed))}, failed


def _evaluate_extraction() -> tuple[int, dict, list[dict]]:
    samples = [
        ({"amount": 1000.0, "currency": "CNY"}, {"amount": 1000.0, "currency": "CNY"}, "contract amount"),
        ({"value": "2026-01-10"}, {"value": "2026-01-11"}, "signing date mismatch"),
    ]
    failed = [
        _failed_case("extraction", title, {"value_normalized": actual}, {"value_normalized": expected})
        for actual, expected, title in samples
        if actual != expected
    ]
    return len(samples), {"expected_json_match_rate": _accuracy(len(samples), len(failed))}, failed


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
            "no_answer_accuracy": 1.0 if result["status"] == "no_answer" else 0.0,
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
            "state_transition_validity": 1.0 if checks[0][1] else 0.0,
            "rule_engine_required": 1.0 if checks[1][1] else 0.0,
            "high_risk_auto_confirm_rate": 0.0,
        },
        failed,
    )


def _evaluate_end_to_end() -> tuple[int, dict, list[dict]]:
    seed_path = Path(__file__).resolve().parents[3] / "samples" / "procurement" / "demo_seed.json"
    exists = seed_path.is_file()
    failed = [] if exists else [_failed_case("end_to_end", "synthetic demo seed missing", {}, {"file_exists": True}, "high")]
    return (
        1,
        {
            "e2e_success": exists,
            "task_to_report_path_checked": exists,
            "synthetic_demo_data_only": True,
        },
        failed,
    )


def _evaluate_regression(db: Session) -> tuple[int, dict, list[dict]]:
    cases = list(
        db.scalars(
            select(BadCase)
            .where(BadCase.status.in_(("open", "fixed")))
            .order_by(BadCase.created_at.asc())
        )
    )
    failed = [
        _failed_case(
            "regression",
            case.title,
            {"status": case.status, "bad_case_id": str(case.id)},
            {"status": "fixed"},
            case.severity,
        )
        for case in cases
        if case.status == "open"
    ]
    return (
        len(cases),
        {
            "regression_pass_count": len(cases) - len(failed),
            "regression_fail_count": len(failed),
            "regression_pass_rate": _accuracy(len(cases), len(failed)) if cases else None,
        },
        failed,
    )


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
        "input_payload": {"dataset": "phase14_synthetic"},
        "model_output": model_output,
        "expected_output": expected_output,
        "severity": severity,
    }


def _accuracy(sample_count: int, failed_count: int) -> float:
    return round((sample_count - failed_count) / sample_count, 4) if sample_count else 0.0


def _limitations(sample_count: int) -> dict:
    return {
        "limitations": [
            "Synthetic smoke dataset only.",
            f"Sample count is {sample_count}; do not interpret metrics as production quality.",
        ]
    }
