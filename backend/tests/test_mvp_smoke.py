from uuid import UUID

from app.db.session import SessionLocal
from app.models.model_invocation import ModelInvocation
from test_review_api import field_by_name
from test_rule_engine_api import build_scenario, client, run_audit


def test_procurement_mvp_demo_smoke_path() -> None:
    task, docs = build_scenario(
        contract_amount=1000.0,
        invoice_amounts=(1200.0,),
        payment_amounts=(1200.0,),
    )
    results = run_audit(task["id"])
    amount_result = results["PROC_AMOUNT_001"]
    assert amount_result["status"] == "fail"

    field = field_by_name(docs["purchase_contract"][0]["id"], "supplier_name")
    correction = client.patch(
        f"/api/v1/fields/{field.id}",
        json={
            "value_text": "Supplier Smoke Demo Co",
            "value_normalized": {"value": "Supplier Smoke Demo Co"},
            "confidence": 0.97,
            "actor_name": "demo_reviewer",
            "comment": "Smoke demo field correction.",
        },
    )
    assert correction.status_code == 200
    assert correction.json()["is_verified"] is True

    confirm = client.post(
        f"/api/v1/audit-results/{amount_result['id']}/confirm",
        json={"actor_name": "demo_reviewer", "reason": "Smoke demo confirms overpayment exception."},
    )
    assert confirm.status_code == 200
    assert confirm.json()["review_status"] == "confirmed"

    report = client.post(
        f"/api/v1/tasks/{task['id']}/reports/control-table",
        json={"generated_by": "demo_reviewer"},
    )
    assert report.status_code == 200
    assert report.json()["summary"]["audit_result_count"] == 7

    download = client.get(f"/api/v1/reports/{report.json()['id']}/download")
    assert download.status_code == 200
    assert download.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert download.content.startswith(b"PK")

    with SessionLocal() as db:
        db.add(
            ModelInvocation(
                task_id=UUID(task["id"]),
                document_id=UUID(docs["invoice"][0]["id"]),
                provider="mock",
                model_name="heuristic-mvp",
                invocation_type="classification",
                prompt_version=None,
                input_hash="demo",
                output_schema="ClassificationRead",
                status="completed",
            )
        )
        db.commit()
        assert db.query(ModelInvocation).count() == 1
