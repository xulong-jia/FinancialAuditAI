from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import can_access_task_scope, enforce_document_scope, enforce_task_scope, require_permission
from app.db.session import get_db
from app.models.bad_case import BadCase
from app.models.evaluation_result import EvaluationResult
from app.models.user import User
from app.schemas.quality import (
    BadCaseCreate,
    BadCaseRead,
    BadCaseType,
    BadCaseUpdate,
    EvaluationResultRead,
    EvaluationRunRequest,
    EvalType,
)
from app.services import auth_service, bad_case_service, evaluation_service

router = APIRouter(tags=["quality"])


@router.post("/bad-cases", response_model=BadCaseRead)
def create_bad_case(
    payload: BadCaseCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("quality:manage")),
):
    payload = _scoped_bad_case_payload(db, user, payload, write=True)
    if payload.owner_name is None:
        payload = payload.model_copy(update={"owner_name": user.full_name})
    return bad_case_service.create_case(db, payload)


@router.get("/bad-cases", response_model=list[BadCaseRead])
def list_bad_cases(
    case_type: BadCaseType | None = None,
    status: str | None = None,
    severity: str | None = None,
    owner_name: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("evaluation:read")),
):
    cases = bad_case_service.list_cases(db, case_type=case_type, status=status, severity=severity, owner_name=owner_name)
    return [case for case in cases if _can_read_bad_case(db, user, case)]


@router.get("/bad-cases/{case_id}", response_model=BadCaseRead)
def get_bad_case(
    case_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("evaluation:read")),
):
    case = bad_case_service.get_case(db, case_id)
    _enforce_bad_case_scope(db, user, case)
    return case


@router.patch("/bad-cases/{case_id}", response_model=BadCaseRead)
def update_bad_case(
    case_id: UUID,
    payload: BadCaseUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("quality:manage")),
):
    case = bad_case_service.get_case(db, case_id)
    _enforce_bad_case_scope(db, user, case, write=True)
    if payload.owner_name is None:
        payload = payload.model_copy(update={"owner_name": user.full_name})
    return bad_case_service.update_case(db, case_id, payload)


@router.post("/evaluations/run", response_model=EvaluationResultRead)
def run_evaluation(
    payload: EvaluationRunRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("quality:manage")),
):
    if payload.task_id is not None:
        enforce_task_scope(db, user, payload.task_id, write=True)
    if payload.created_by is None:
        payload = payload.model_copy(update={"created_by": user.full_name})
    return evaluation_service.run_evaluation(db, payload)


@router.get("/evaluations/results", response_model=list[EvaluationResultRead])
def list_evaluation_results(
    eval_type: EvalType | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("evaluation:read")),
):
    return [
        result
        for result in evaluation_service.list_results(db, eval_type)
        if _can_read_evaluation_result(db, user, result)
    ]


@router.get("/evaluations/results/{result_id}", response_model=EvaluationResultRead)
def get_evaluation_result(
    result_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("evaluation:read")),
):
    result = evaluation_service.get_result(db, result_id)
    _enforce_evaluation_result_scope(db, user, result)
    return result


def _scoped_bad_case_payload(db: Session, user: User, payload: BadCaseCreate, *, write: bool) -> BadCaseCreate:
    task_id = payload.task_id
    if payload.document_id is not None:
        document = enforce_document_scope(db, user, payload.document_id, write=write)
        if task_id is not None and document.task_id != task_id:
            raise HTTPException(status_code=400, detail="Bad case document does not belong to task")
        task_id = document.task_id
    if task_id is not None:
        enforce_task_scope(db, user, task_id, write=write)
    return payload.model_copy(update={"task_id": task_id})


def _enforce_bad_case_scope(db: Session, user: User, case: BadCase, *, write: bool = False) -> None:
    if case.task_id is not None:
        enforce_task_scope(db, user, case.task_id, write=write)
    elif case.document_id is not None:
        enforce_document_scope(db, user, case.document_id, write=write)


def _can_read_bad_case(db: Session, user: User, case: BadCase) -> bool:
    if case.task_id is None:
        return case.document_id is None
    return can_access_task_scope(db, user, case.task_id)


def _enforce_evaluation_result_scope(db: Session, user: User, result: EvaluationResult) -> None:
    if result.task_id is not None:
        enforce_task_scope(db, user, result.task_id)
        return
    permissions = auth_service.user_permissions(db, user)
    if "*" in permissions or "quality:manage" in permissions or "project:manage" in permissions:
        return
    raise HTTPException(status_code=403, detail="Evaluation result access denied")


def _can_read_evaluation_result(db: Session, user: User, result: EvaluationResult) -> bool:
    if result.task_id is not None:
        return can_access_task_scope(db, user, result.task_id)
    permissions = auth_service.user_permissions(db, user)
    return "*" in permissions or "quality:manage" in permissions or "project:manage" in permissions
