from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.schemas.report import ReportGenerateRequest, ReportRead
from app.services import report_service

router = APIRouter(tags=["reports"])


@router.post("/tasks/{task_id}/reports/control-table", response_model=ReportRead, dependencies=[Depends(require_permission("report:generate"))])
def generate_control_table_report(
    task_id: UUID,
    payload: ReportGenerateRequest | None = None,
    db: Session = Depends(get_db),
):
    return report_service.generate_control_table_report(
        db,
        task_id,
        generated_by=payload.generated_by if payload else None,
    )


@router.get("/tasks/{task_id}/reports", response_model=list[ReportRead], dependencies=[Depends(require_permission("read"))])
def list_reports(task_id: UUID, db: Session = Depends(get_db)):
    return report_service.list_reports(db, task_id)


@router.get("/reports/{report_id}/download", dependencies=[Depends(require_permission("read"))])
def download_report(report_id: UUID, db: Session = Depends(get_db)):
    report = report_service.get_report(db, report_id)
    path = report_service.report_file_path(report)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{report.title}.xlsx",
    )
