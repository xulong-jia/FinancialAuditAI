from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.deps import enforce_task_scope, require_permission
from app.db.session import get_db
from app.models.user import User
from app.schemas.report import ReportGenerateRequest, ReportRead
from app.services import audit_log_service, report_service

router = APIRouter(tags=["reports"])


@router.post("/tasks/{task_id}/reports/control-table", response_model=ReportRead)
def generate_control_table_report(
    task_id: UUID,
    payload: ReportGenerateRequest | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("report:generate")),
):
    enforce_task_scope(db, user, task_id, write=True)
    return report_service.generate_control_table_report(
        db,
        task_id,
        generated_by=payload.generated_by if payload else None,
        file_format=payload.file_format if payload else "xlsx",
    )


@router.get("/tasks/{task_id}/reports", response_model=list[ReportRead])
def list_reports(task_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    enforce_task_scope(db, user, task_id)
    return report_service.list_reports(db, task_id)


@router.get("/reports/{report_id}/download")
def download_report(report_id: UUID, db: Session = Depends(get_db), user: User = Depends(require_permission("read"))):
    report = report_service.get_report(db, report_id)
    enforce_task_scope(db, user, report.task_id)
    audit_log_service.add_log(
        db,
        actor_name=user.full_name,
        task_id=report.task_id,
        action="report_downloaded",
        target_type="report",
        target_id=report.id,
        after_value={"file_format": report.file_format, "title": report.title},
    )
    db.commit()
    path = report_service.report_file_path(report)
    if report.file_format == "csv":
        return FileResponse(path, media_type="text/csv", filename=f"{report.title}.csv")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{report.title}.xlsx",
    )
