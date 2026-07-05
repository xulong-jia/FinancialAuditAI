import json
from uuid import UUID

from app.db.session import SessionLocal
from app.models.audit_log import AuditLog
from app.models.extracted_field import ExtractedField
from test_rule_engine_api import build_scenario, client, run_audit


def rule_by_code(rule_code: str) -> dict:
    response = client.get("/api/v1/rules")
    assert response.status_code == 200
    return {rule["rule_code"]: rule for rule in response.json()}[rule_code]


def patch_rule(rule_id: str, payload: dict) -> dict:
    response = client.patch(f"/api/v1/rules/{rule_id}", json=payload)
    assert response.status_code == 200
    return response.json()


def update_item_name(document_id: str, item_name: str) -> None:
    with SessionLocal() as db:
        field = (
            db.query(ExtractedField)
            .filter(
                ExtractedField.document_id == UUID(document_id),
                ExtractedField.field_name == "item_lines",
            )
            .one()
        )
        field.value_text = f"Item: {item_name}; Quantity: 10.0; Unit: pcs"
        field.value_normalized = {
            "items": [{"item_name": item_name, "quantity": 10.0, "unit": "pcs"}],
        }
        db.commit()


def test_rule_can_be_disabled_and_excluded_from_audit() -> None:
    task, _ = build_scenario()
    amount_rule = rule_by_code("PROC_AMOUNT_001")
    patch_rule(amount_rule["id"], {"enabled": False, "actor_name": "rule_admin"})

    results = run_audit(task["id"])

    assert "PROC_AMOUNT_001" not in results
    assert len(results) == 6


def test_rule_create_rejects_non_registry_code() -> None:
    response = client.post(
        "/api/v1/rules",
        json={"rule_code": "USER_DSL_001", "name": "User rule", "parameters": {}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Rule expression is not supported"


def test_rule_create_and_evaluate_dsl_expression() -> None:
    task, _ = build_scenario()
    expression = "dsl:" + json.dumps(
        {
            "operation": "compare",
            "left": "purchase_contract.amount_including_tax",
            "operator": "eq",
            "right": "invoice.amount_including_tax",
            "tolerance": 1.0,
        }
    )

    create_response = client.post(
        "/api/v1/rules",
        json={
            "rule_code": "PROC_DSL_AMOUNT_001",
            "name": "Custom DSL amount compare",
            "scenario": "procurement",
            "category": "amount",
            "severity": "high",
            "expression": expression,
        },
    )
    assert create_response.status_code == 200, create_response.text

    evaluate_response = client.post(
        f"/api/v1/rules/{create_response.json()['id']}/evaluate",
        json={"task_id": task["id"]},
    )
    assert evaluate_response.status_code == 200
    body = evaluate_response.json()[0]
    assert body["rule_code"] == "PROC_DSL_AMOUNT_001"
    assert body["status"] == "fail"
    assert body["actual_value"]["left"] == 1000.0
    assert body["actual_value"]["right"] == 800.0


def test_rule_dsl_missing_field_outputs_need_review() -> None:
    task, _ = build_scenario(omit=("purchase_contract", "supplier_name"))
    expression = "dsl:" + json.dumps(
        {
            "operation": "all_present",
            "all_present": ["purchase_contract.supplier_name", "invoice.seller_name"],
        }
    )
    create_response = client.post(
        "/api/v1/rules",
        json={
            "rule_code": "PROC_DSL_PRESENT_001",
            "name": "Custom DSL presence check",
            "scenario": "procurement",
            "category": "missing_field",
            "severity": "medium",
            "expression": expression,
        },
    )
    assert create_response.status_code == 200, create_response.text

    evaluate_response = client.post(
        f"/api/v1/rules/{create_response.json()['id']}/evaluate",
        json={"task_id": task["id"]},
    )
    assert evaluate_response.status_code == 200
    body = evaluate_response.json()[0]
    assert body["status"] == "need_review"
    assert body["actual_value"]["missing_fields"] == ["purchase_contract.supplier_name"]


def test_rule_update_rejects_invalid_expression_contract() -> None:
    amount_rule = rule_by_code("PROC_AMOUNT_001")

    response = client.patch(
        f"/api/v1/rules/{amount_rule['id']}",
        json={"expression": "python:PROC_QTY_001"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Rule expression is not supported"


def test_amount_tolerance_parameter_changes_rule_result_and_version_is_recorded() -> None:
    task, _ = build_scenario(
        contract_amount=1000.0,
        invoice_amounts=(1002.0,),
        payment_amounts=(1002.0,),
        voucher_amount=1002.0,
        amount_excluding_tax=910.91,
        tax_amount=91.09,
        amount_including_tax=1002.0,
    )
    amount_rule = rule_by_code("PROC_AMOUNT_001")

    default_results = run_audit(task["id"])
    assert default_results["PROC_AMOUNT_001"]["status"] == "fail"

    patch_rule(
        amount_rule["id"],
        {
            "version": "2.0",
            "parameters": {"tolerance_amount": 5.0, "tolerance_ratio": 0.0},
            "actor_name": "rule_admin",
        },
    )
    updated_results = run_audit(task["id"])

    assert updated_results["PROC_AMOUNT_001"]["status"] == "pass"
    assert updated_results["PROC_AMOUNT_001"]["rule_version"] == "2.0"


def test_supplier_alias_parameter_changes_name_rule_result() -> None:
    task, _ = build_scenario(invoice_seller="Supplier Company")
    name_rule = rule_by_code("PROC_NAME_001")

    default_results = run_audit(task["id"])
    assert default_results["PROC_NAME_001"]["status"] == "warning"

    patch_rule(
        name_rule["id"],
        {
            "parameters": {"mismatch_status": "warning", "supplier_aliases": {"Supplier Co": ["Supplier Company"]}},
            "actor_name": "rule_admin",
        },
    )
    updated_results = run_audit(task["id"])

    assert updated_results["PROC_NAME_001"]["status"] == "pass"


def test_item_mapping_parameter_changes_quantity_rule_result() -> None:
    task, docs = build_scenario()
    qty_rule = rule_by_code("PROC_QTY_001")
    update_item_name(docs["warehouse_receipt"][0]["id"], "Widget Alias")

    default_results = run_audit(task["id"])
    assert default_results["PROC_QTY_001"]["status"] == "fail"

    patch_rule(
        qty_rule["id"],
        {
            "parameters": {"tolerance_amount": 0.0001, "item_mappings": {"Widget": ["Widget Alias"]}},
            "actor_name": "rule_admin",
        },
    )
    updated_results = run_audit(task["id"])

    assert updated_results["PROC_QTY_001"]["status"] == "pass"


def test_rule_update_writes_audit_log() -> None:
    name_rule = rule_by_code("PROC_NAME_001")
    patch_rule(
        name_rule["id"],
        {
            "parameters": {
                "mismatch_status": "warning",
                "supplier_aliases": {"Supplier Co": ["Supplier Company"]},
            },
            "actor_name": "rule_admin",
        },
    )

    with SessionLocal() as db:
        log = (
            db.query(AuditLog)
            .filter(
                AuditLog.action == "audit_rule_updated",
                AuditLog.target_id == UUID(name_rule["id"]),
            )
            .one()
        )
        assert log.actor_name == "rule_admin"
        assert log.before_value["rule_code"] == "PROC_NAME_001"
        assert log.after_value["parameters"]["supplier_aliases"]["Supplier Co"] == ["Supplier Company"]


def test_rule_evaluate_api_returns_dry_run_result_without_persisting() -> None:
    task, _ = build_scenario(
        contract_amount=1000.0,
        invoice_amounts=(1002.0,),
        payment_amounts=(1002.0,),
        voucher_amount=1002.0,
        amount_excluding_tax=910.91,
        tax_amount=91.09,
        amount_including_tax=1002.0,
    )
    amount_rule = rule_by_code("PROC_AMOUNT_001")

    response = client.post(
        f"/api/v1/rules/{amount_rule['id']}/evaluate",
        json={"task_id": task["id"], "parameters": {"tolerance_amount": 5.0}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body[0]["rule_code"] == "PROC_AMOUNT_001"
    assert body[0]["status"] == "pass"

    list_response = client.get(f"/api/v1/tasks/{task['id']}/audit-results")
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_unknown_rule_parameter_is_rejected() -> None:
    amount_rule = rule_by_code("PROC_AMOUNT_001")

    response = client.patch(
        f"/api/v1/rules/{amount_rule['id']}",
        json={"parameters": {"python_expression": "1 + 1"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported rule parameter: python_expression"


def test_invalid_rule_parameter_type_is_rejected() -> None:
    amount_rule = rule_by_code("PROC_AMOUNT_001")

    response = client.patch(
        f"/api/v1/rules/{amount_rule['id']}",
        json={"parameters": {"tolerance_amount": "not-a-number"}},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "tolerance_amount must be numeric"
