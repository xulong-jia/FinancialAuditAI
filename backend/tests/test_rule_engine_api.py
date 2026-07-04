from uuid import UUID

from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.document import Document
from app.models.extracted_field import ExtractedField


client = TestClient(app)
BUSINESS_KEY = "CONTRACT-C-900"


def create_task() -> dict:
    response = client.post(
        "/api/v1/tasks",
        json={"name": "Rule engine task", "scenario": "procurement"},
    )
    assert response.status_code == 200
    return response.json()


def upload_document(task_id: str, filename: str, doc_type: str) -> dict:
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        data={"doc_type_hint": doc_type},
        files={"file": (filename, b"%PDF-1.4\nrule test\n", "application/pdf")},
    )
    assert response.status_code == 200
    document = response.json()
    with SessionLocal() as db:
        db_document = db.get(Document, UUID(document["id"]))
        assert db_document is not None
        db_document.business_key = BUSINESS_KEY
        db.commit()
    return document


def add_field(
    task_id: str,
    document_id: str,
    field_name: str,
    value: str | None,
    *,
    normalized: dict | None = None,
    field_type: str = "text",
    is_required: bool = True,
    confidence: float = 0.85,
    warnings: list[str] | None = None,
) -> None:
    with SessionLocal() as db:
        db.add(
            ExtractedField(
                task_id=UUID(task_id),
                document_id=UUID(document_id),
                field_name=field_name,
                field_label=field_name.replace("_", " ").title(),
                field_type=field_type,
                value_text=value,
                value_normalized=normalized if normalized is not None else ({"value": value} if value else None),
                unit=None,
                currency=normalized.get("currency") if normalized else None,
                confidence=confidence,
                source_page=1,
                source_text=f"{field_name}: {value}" if value else None,
                source_bbox=None,
                extraction_method="test",
                is_required=is_required,
                is_verified=False,
                corrected_by=None,
                corrected_at=None,
                warnings=warnings or [],
            )
        )
        db.commit()


def add_money(task_id: str, document_id: str, field_name: str, amount: float) -> None:
    add_field(
        task_id,
        document_id,
        field_name,
        str(amount),
        normalized={"amount": amount, "currency": "CNY"},
        field_type="money",
    )


def add_date(task_id: str, document_id: str, field_name: str, value: str) -> None:
    add_field(task_id, document_id, field_name, value, normalized={"value": value}, field_type="date")


def add_rate(task_id: str, document_id: str, field_name: str, rate: float) -> None:
    add_field(task_id, document_id, field_name, f"{rate * 100:.0f}%", normalized={"rate": rate}, field_type="tax_rate")


def add_items(task_id: str, document_id: str, quantity: float) -> None:
    add_field(
        task_id,
        document_id,
        "item_lines",
        f"Item: Widget; Quantity: {quantity}; Unit: pcs",
        normalized={"items": [{"item_name": "Widget", "quantity": quantity, "unit": "pcs"}]},
        field_type="line_items",
    )


def build_scenario(
    *,
    omit: tuple[str, str] | None = None,
    receipt_date: str = "2026-01-20",
    invoice_date: str = "2026-01-25",
    payment_date: str = "2026-02-05",
    contract_amount: float = 1000.0,
    invoice_amounts: tuple[float, ...] = (800.0,),
    payment_amounts: tuple[float, ...] = (800.0,),
    voucher_amount: float = 800.0,
    invoice_seller: str = "Supplier Co",
    payment_payee: str = "Supplier Co",
    invoice_quantity: float = 10.0,
    tax_amount: float = 72.73,
    amount_excluding_tax: float = 727.27,
    amount_including_tax: float = 800.0,
) -> tuple[dict, dict[str, list[dict]]]:
    task = create_task()
    docs: dict[str, list[dict]] = {
        "purchase_request": [upload_document(task["id"], "request.pdf", "purchase_request")],
        "purchase_contract": [upload_document(task["id"], "contract.pdf", "purchase_contract")],
        "warehouse_receipt": [upload_document(task["id"], "receipt.pdf", "warehouse_receipt")],
        "invoice": [
            upload_document(task["id"], f"invoice-{index}.pdf", "invoice")
            for index, _ in enumerate(invoice_amounts, start=1)
        ],
        "accounting_voucher": [upload_document(task["id"], "voucher.pdf", "accounting_voucher")],
        "payment_receipt": [
            upload_document(task["id"], f"payment-{index}.pdf", "payment_receipt")
            for index, _ in enumerate(payment_amounts, start=1)
        ],
    }

    def maybe(doc_type: str, doc: dict, field_name: str, add) -> None:
        if omit == (doc_type, field_name):
            add_field(
                task["id"],
                doc["id"],
                field_name,
                None,
                warnings=["required_field_missing"],
            )
            return
        add()

    request = docs["purchase_request"][0]
    maybe("purchase_request", request, "request_no", lambda: add_field(task["id"], request["id"], "request_no", "PR-001"))
    maybe("purchase_request", request, "request_date", lambda: add_date(task["id"], request["id"], "request_date", "2026-01-01"))
    maybe("purchase_request", request, "approval_date", lambda: add_date(task["id"], request["id"], "approval_date", "2026-01-05"))
    maybe("purchase_request", request, "approval_status", lambda: add_field(task["id"], request["id"], "approval_status", "approved"))
    maybe("purchase_request", request, "item_lines", lambda: add_items(task["id"], request["id"], 10.0))
    maybe("purchase_request", request, "total_estimated_amount", lambda: add_money(task["id"], request["id"], "total_estimated_amount", 1000.0))

    contract = docs["purchase_contract"][0]
    maybe("purchase_contract", contract, "contract_no", lambda: add_field(task["id"], contract["id"], "contract_no", "C-900"))
    maybe("purchase_contract", contract, "signing_date", lambda: add_date(task["id"], contract["id"], "signing_date", "2026-01-10"))
    maybe("purchase_contract", contract, "buyer_name", lambda: add_field(task["id"], contract["id"], "buyer_name", "Buyer Co"))
    maybe("purchase_contract", contract, "supplier_name", lambda: add_field(task["id"], contract["id"], "supplier_name", "Supplier Co"))
    maybe("purchase_contract", contract, "item_lines", lambda: add_items(task["id"], contract["id"], 10.0))
    maybe("purchase_contract", contract, "amount_including_tax", lambda: add_money(task["id"], contract["id"], "amount_including_tax", contract_amount))
    add_rate(task["id"], contract["id"], "tax_rate", 0.1)

    receipt = docs["warehouse_receipt"][0]
    maybe("warehouse_receipt", receipt, "receipt_no", lambda: add_field(task["id"], receipt["id"], "receipt_no", "WR-001"))
    maybe("warehouse_receipt", receipt, "receipt_date", lambda: add_date(task["id"], receipt["id"], "receipt_date", receipt_date))
    maybe("warehouse_receipt", receipt, "supplier_name", lambda: add_field(task["id"], receipt["id"], "supplier_name", "Supplier Co"))
    maybe("warehouse_receipt", receipt, "item_lines", lambda: add_items(task["id"], receipt["id"], 10.0))

    for index, invoice in enumerate(docs["invoice"]):
        amount = invoice_amounts[index]
        maybe("invoice", invoice, "invoice_no", lambda invoice=invoice, index=index: add_field(task["id"], invoice["id"], "invoice_no", f"INV-{index + 1:03d}"))
        maybe("invoice", invoice, "invoice_date", lambda invoice=invoice: add_date(task["id"], invoice["id"], "invoice_date", invoice_date))
        maybe("invoice", invoice, "seller_name", lambda invoice=invoice: add_field(task["id"], invoice["id"], "seller_name", invoice_seller))
        maybe("invoice", invoice, "buyer_name", lambda invoice=invoice: add_field(task["id"], invoice["id"], "buyer_name", "Buyer Co"))
        maybe("invoice", invoice, "item_lines", lambda invoice=invoice: add_items(task["id"], invoice["id"], invoice_quantity))
        maybe("invoice", invoice, "amount_excluding_tax", lambda invoice=invoice: add_money(task["id"], invoice["id"], "amount_excluding_tax", amount_excluding_tax if index == 0 else amount))
        maybe("invoice", invoice, "tax_amount", lambda invoice=invoice: add_money(task["id"], invoice["id"], "tax_amount", tax_amount if index == 0 else 0.0))
        maybe("invoice", invoice, "amount_including_tax", lambda invoice=invoice, amount=amount: add_money(task["id"], invoice["id"], "amount_including_tax", amount if index != 0 else amount_including_tax))
        add_rate(task["id"], invoice["id"], "tax_rate", 0.1)

    voucher = docs["accounting_voucher"][0]
    maybe("accounting_voucher", voucher, "voucher_no", lambda: add_field(task["id"], voucher["id"], "voucher_no", "V-001"))
    maybe("accounting_voucher", voucher, "voucher_date", lambda: add_date(task["id"], voucher["id"], "voucher_date", "2026-01-30"))
    maybe("accounting_voucher", voucher, "summary", lambda: add_field(task["id"], voucher["id"], "summary", "Invoice INV-001"))
    maybe("accounting_voucher", voucher, "debit_subject", lambda: add_field(task["id"], voucher["id"], "debit_subject", "Inventory"))
    maybe("accounting_voucher", voucher, "credit_subject", lambda: add_field(task["id"], voucher["id"], "credit_subject", "Accounts Payable"))
    maybe("accounting_voucher", voucher, "amount", lambda: add_money(task["id"], voucher["id"], "amount", voucher_amount))
    add_field(task["id"], voucher["id"], "supplier_name", "Supplier Co", is_required=False)

    for index, payment in enumerate(docs["payment_receipt"]):
        amount = payment_amounts[index]
        maybe("payment_receipt", payment, "payment_no", lambda payment=payment, index=index: add_field(task["id"], payment["id"], "payment_no", f"PAY-{index + 1:03d}"))
        maybe("payment_receipt", payment, "payment_date", lambda payment=payment: add_date(task["id"], payment["id"], "payment_date", payment_date))
        maybe("payment_receipt", payment, "payer_name", lambda payment=payment: add_field(task["id"], payment["id"], "payer_name", "Buyer Co"))
        maybe("payment_receipt", payment, "payee_name", lambda payment=payment: add_field(task["id"], payment["id"], "payee_name", payment_payee))
        maybe("payment_receipt", payment, "amount", lambda payment=payment, amount=amount: add_money(task["id"], payment["id"], "amount", amount))
        maybe("payment_receipt", payment, "currency", lambda payment=payment: add_field(task["id"], payment["id"], "currency", "CNY", normalized={"value": "CNY"}, field_type="currency"))

    return task, docs


def result_by_code(results: list[dict]) -> dict[str, dict]:
    return {result["rule_code"]: result for result in results}


def run_audit(task_id: str) -> dict[str, dict]:
    response = client.post(f"/api/v1/tasks/{task_id}/audit")
    assert response.status_code == 200
    results = response.json()
    assert all(result["evidence"]["refs"] for result in results)
    return result_by_code(results)


def test_audit_api_runs_all_rules_and_persists_results() -> None:
    task, _ = build_scenario()

    results = run_audit(task["id"])

    assert set(results) == {
        "PROC_MISSING_001",
        "PROC_TIME_001",
        "PROC_AMOUNT_001",
        "PROC_NAME_001",
        "PROC_QTY_001",
        "PROC_TAX_001",
    }
    assert all(result["status"] == "pass" for result in results.values())

    list_response = client.get(f"/api/v1/tasks/{task['id']}/audit-results")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 6

    detail_response = client.get(f"/api/v1/audit-results/{list_response.json()[0]['id']}")
    assert detail_response.status_code == 200
    assert detail_response.json()["rule_code"]

    rules_response = client.get("/api/v1/rules")
    assert rules_response.status_code == 200
    rule_codes = {rule["rule_code"] for rule in rules_response.json()}
    assert set(results).issubset(rule_codes)
    assert "SALES_AMOUNT_001" in rule_codes


def test_missing_required_field_needs_review_and_never_passes() -> None:
    task, _ = build_scenario(omit=("invoice", "tax_amount"))

    results = run_audit(task["id"])

    assert results["PROC_MISSING_001"]["status"] == "need_review"
    assert results["PROC_MISSING_001"]["review_status"] == "pending"
    assert results["PROC_MISSING_001"]["actual_value"]["missing_fields"]


def test_time_rule_fails_on_date_inversion() -> None:
    task, _ = build_scenario(receipt_date="2026-02-10", invoice_date="2026-01-25")

    results = run_audit(task["id"])

    assert results["PROC_TIME_001"]["status"] == "fail"
    assert results["PROC_TIME_001"]["severity"] == "high"


def test_amount_rule_fails_on_overpayment_and_supports_many_invoices_payments() -> None:
    task, _ = build_scenario(
        contract_amount=1000.0,
        invoice_amounts=(700.0, 600.0),
        payment_amounts=(800.0, 500.0),
        voucher_amount=700.0,
    )

    results = run_audit(task["id"])

    assert results["PROC_AMOUNT_001"]["status"] == "fail"
    assert results["PROC_AMOUNT_001"]["actual_value"]["invoice_total"] > 1000.0
    assert results["PROC_AMOUNT_001"]["actual_value"]["payment_total"] > 1000.0


def test_name_rule_needs_review_when_subject_missing() -> None:
    task, _ = build_scenario(omit=("payment_receipt", "payee_name"))

    results = run_audit(task["id"])

    assert results["PROC_NAME_001"]["status"] == "need_review"


def test_low_confidence_evidence_outputs_warning_for_review() -> None:
    task, docs = build_scenario()
    contract_id = UUID(docs["purchase_contract"][0]["id"])
    with SessionLocal() as db:
        field = (
            db.query(ExtractedField)
            .filter(
                ExtractedField.document_id == contract_id,
                ExtractedField.field_name == "signing_date",
            )
            .one()
        )
        field.confidence = 0.5
        db.commit()

    results = run_audit(task["id"])

    assert results["PROC_TIME_001"]["status"] == "warning"
    assert results["PROC_TIME_001"]["review_status"] == "pending"


def test_quantity_rule_fails_on_basic_quantity_mismatch() -> None:
    task, _ = build_scenario(invoice_quantity=9.0)

    results = run_audit(task["id"])

    assert results["PROC_QTY_001"]["status"] == "fail"
    assert results["PROC_QTY_001"]["actual_value"]["invoice"] == 9.0


def test_tax_rule_fails_when_tax_arithmetic_does_not_reconcile() -> None:
    task, _ = build_scenario(tax_amount=80.0, amount_excluding_tax=727.27, amount_including_tax=800.0)

    results = run_audit(task["id"])

    assert results["PROC_TAX_001"]["status"] == "fail"
    assert results["PROC_TAX_001"]["message"] == "Invoice tax arithmetic does not reconcile."
