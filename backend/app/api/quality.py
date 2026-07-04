from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.quality import (
    BadCaseCreate,
    BadCaseRead,
    BadCaseUpdate,
    EvaluationResultRead,
    EvaluationRunRequest,
    EvalType,
)
from app.services import bad_case_service, evaluation_service

router = APIRouter(tags=["quality"])


@router.post("/bad-cases", response_model=BadCaseRead)
def create_bad_case(payload: BadCaseCreate, db: Session = Depends(get_db)):
    return bad_case_service.create_case(db, payload)


@router.get("/bad-cases", response_model=list[BadCaseRead])
def list_bad_cases(
    case_type: EvalType | None = None,
    status: str | None = None,
    severity: str | None = None,
    owner_name: str | None = None,
    db: Session = Depends(get_db),
):
    return bad_case_service.list_cases(
        db,
        case_type=case_type,
        status=status,
        severity=severity,
        owner_name=owner_name,
    )


@router.get("/bad-cases/{case_id}", response_model=BadCaseRead)
def get_bad_case(case_id: UUID, db: Session = Depends(get_db)):
    return bad_case_service.get_case(db, case_id)


@router.patch("/bad-cases/{case_id}", response_model=BadCaseRead)
def update_bad_case(case_id: UUID, payload: BadCaseUpdate, db: Session = Depends(get_db)):
    return bad_case_service.update_case(db, case_id, payload)


@router.post("/evaluations/run", response_model=EvaluationResultRead)
def run_evaluation(payload: EvaluationRunRequest, db: Session = Depends(get_db)):
    return evaluation_service.run_evaluation(db, payload)


@router.get("/evaluations/results", response_model=list[EvaluationResultRead])
def list_evaluation_results(eval_type: EvalType | None = None, db: Session = Depends(get_db)):
    return evaluation_service.list_results(db, eval_type)


@router.get("/evaluations/results/{result_id}", response_model=EvaluationResultRead)
def get_evaluation_result(result_id: UUID, db: Session = Depends(get_db)):
    return evaluation_service.get_result(db, result_id)
