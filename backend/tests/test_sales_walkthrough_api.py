from io import BytesIO
from uuid import UUID
from xml.etree import ElementTree
from zipfile import ZipFile

import fitz
import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.extracted_field import ExtractedField
from app.models.control_table_row import ControlTableRow


client = TestClient(app)


SALES_KEYWORDS = [
    ("sales_contract", "Sales Contract contract no customer payment terms delivery terms"),
    ("sales_order", "Sales Order order no customer related contract line item"),
    ("delivery_order", "Delivery Order delivery no customer warehouse related order"),
    ("logistics_receipt", "Logistics Receipt logistics no signed date receiver signer shipment"),
    ("sales_invoice", "Sales Invoice invoice no seller buyer tax amount total with tax"),
    ("receipt_voucher", "Receipt Voucher receipt no payer payee bank serial receipt purpose"),
    ("accounting_voucher", "Accounting Voucher voucher no debit credit summary customer"),
]


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    return document.tobytes()


def workbook_sheet_names(data: bytes) -> list[str]:
    with ZipFile(BytesIO(data)) as archive:
        workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    return [sheet.attrib["name"] for sheet in workbook.findall(".//main:sheet", namespace)]


def create_sales_task() -> dict:
    response = client.post("/api/v1/tasks", json={"name": "Sales walkthrough", "scenario": "sales"})
    assert response.status_code == 200
    assert response.json()["scenario"] == "sales"
    assert response.json()["task_no"].startswith("SALES-")
    return response.json()


def upload_pdf(task_id: str, doc_type: str, text: str | None = None) -> dict:
    response = client.post(
        f"/api/v1/tasks/{task_id}/documents",
        data={"doc_type_hint": doc_type},
        files={"file": (f"{doc_type}.pdf", make_pdf(text or doc_type), "application/pdf")},
    )
    assert response.status_code == 200
    return response.json()


def add_field(
    task_id: str,
    document_id: str,
    field_name: str,
    value: str | None,
    *,
    normalized: dict | None = None,
    field_type: str = "text",
    is_required: bool = True,
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
                confidence=0.85 if value else 0.0,
                source_page=1 if value else None,
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


def add_date(task_id: str, document_id: str, field_name: str, value: str) -> None:
    add_field(task_id, document_id, field_name, value, normalized={"value": value}, field_type="date")


def add_money(task_id: str, document_id: str, field_name: str, amount: float) -> None:
    add_field(
        task_id,
        document_id,
        field_name,
        str(amount),
        normalized={"amount": amount, "currency": "CNY"},
        field_type="money",
    )


def add_items(task_id: str, document_id: str, quantity: float) -> None:
    add_field(
        task_id,
        document_id,
        "item_lines",
        f"Item: Demo goods; Quantity: {quantity}; Unit: pcs; Amount: 1000.00",
        normalized={"items": [{"item_name": "Demo goods", "quantity": quantity, "unit": "pcs"}]},
        field_type="line_items",
    )


def build_sales_scenario(invoice_amount: float = 1200.0) -> tuple[dict, dict[str, dict]]:
    task = create_sales_task()
    docs = {doc_type: upload_pdf(task["id"], doc_type) for doc_type, _ in SALES_KEYWORDS}

    contract = docs["sales_contract"]
    add_field(task["id"], contract["id"], "contract_no", "SC-001")
    add_date(task["id"], contract["id"], "signing_date", "2026-01-01")
    add_field(task["id"], contract["id"], "customer_name", "Customer Co")
    add_field(task["id"], contract["id"], "seller_name", "Seller Co")
    add_items(task["id"], contract["id"], 10.0)
    add_money(task["id"], contract["id"], "amount_including_tax", 1000.0)

    order = docs["sales_order"]
    add_field(task["id"], order["id"], "order_no", "SO-001")
    add_date(task["id"], order["id"], "order_date", "2026-01-02")
    add_field(task["id"], order["id"], "customer_name", "Customer Co")
    add_field(task["id"], order["id"], "related_contract_no", "SC-001", is_required=False)
    add_items(task["id"], order["id"], 10.0)
    add_money(task["id"], order["id"], "amount", 1000.0)

    delivery = docs["delivery_order"]
    add_field(task["id"], delivery["id"], "delivery_no", "DO-001")
    add_date(task["id"], delivery["id"], "delivery_date", "2026-01-05")
    add_field(task["id"], delivery["id"], "customer_name", "Customer Co")
    add_field(task["id"], delivery["id"], "related_order_no", "SO-001", is_required=False)
    add_field(task["id"], delivery["id"], "related_contract_no", "SC-001", is_required=False)
    add_items(task["id"], delivery["id"], 10.0)

    logistics = docs["logistics_receipt"]
    add_field(task["id"], logistics["id"], "logistics_no", "LG-001")
    add_date(task["id"], logistics["id"], "shipment_date", "2026-01-05")
    add_date(task["id"], logistics["id"], "signed_date", "2026-01-06")
    add_field(task["id"], logistics["id"], "receiver_name", "Customer Co")
    add_field(task["id"], logistics["id"], "customer_name", "Customer Co", is_required=False)
    add_field(task["id"], logistics["id"], "related_delivery_no", "DO-001", is_required=False)
    add_items(task["id"], logistics["id"], 10.0)

    invoice = docs["sales_invoice"]
    add_field(task["id"], invoice["id"], "invoice_no", "SINV-001")
    add_date(task["id"], invoice["id"], "invoice_date", "2026-01-10")
    add_field(task["id"], invoice["id"], "seller_name", "Seller Co")
    add_field(task["id"], invoice["id"], "buyer_name", "Customer Co")
    add_items(task["id"], invoice["id"], 10.0)
    add_money(task["id"], invoice["id"], "amount_excluding_tax", invoice_amount - 100.0)
    add_money(task["id"], invoice["id"], "tax_amount", 100.0)
    add_money(task["id"], invoice["id"], "amount_including_tax", invoice_amount)

    receipt = docs["receipt_voucher"]
    add_field(task["id"], receipt["id"], "receipt_no", "RV-001")
    add_date(task["id"], receipt["id"], "receipt_date", "2026-01-15")
    add_field(task["id"], receipt["id"], "payer_name", "Customer Co")
    add_field(task["id"], receipt["id"], "payee_name", "Seller Co")
    add_money(task["id"], receipt["id"], "amount", invoice_amount)
    add_field(task["id"], receipt["id"], "currency", "CNY", normalized={"value": "CNY"}, field_type="currency")
    add_field(task["id"], receipt["id"], "receipt_purpose", "Receipt for contract SC-001", is_required=False)
    add_field(task["id"], receipt["id"], "related_contract_no", "SC-001", is_required=False)

    voucher = docs["accounting_voucher"]
    add_field(task["id"], voucher["id"], "voucher_no", "AV-001")
    add_date(task["id"], voucher["id"], "voucher_date", "2026-01-20")
    add_field(task["id"], voucher["id"], "summary", "Sales invoice SINV-001")
    add_field(task["id"], voucher["id"], "debit_subject", "Accounts Receivable")
    add_field(task["id"], voucher["id"], "credit_subject", "Revenue")
    add_money(task["id"], voucher["id"], "amount", invoice_amount)
    add_field(task["id"], voucher["id"], "customer_name", "Customer Co", is_required=False)
    add_field(task["id"], voucher["id"], "related_invoice_no", "SINV-001", is_required=False)
    return task, docs


@pytest.mark.parametrize(("doc_type", "text"), SALES_KEYWORDS)
def test_classifies_sales_document_types(doc_type: str, text: str) -> None:
    task = create_sales_task()
    document = upload_pdf(task["id"], doc_type, text)
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/classify")

    assert response.status_code == 200
    assert response.json()["doc_type"] == doc_type
    assert response.json()["confidence"] >= 0.6


def test_extracts_sales_contract_schema_fields() -> None:
    task = create_sales_task()
    document = upload_pdf(
        task["id"],
        "sales_contract",
        "\n".join(
            [
                "Contract No: SC-001",
                "Signing Date: 2026-01-01",
                "Customer Name: Customer Co",
                "Seller Name: Seller Co",
                "Item: Demo goods; Quantity: 10; Unit: pcs; Amount: 1000.00",
                "Amount Including Tax: CNY 1000.00",
            ]
        ),
    )
    assert client.post(f"/api/v1/documents/{document['id']}/ocr").status_code == 200

    response = client.post(f"/api/v1/documents/{document['id']}/extract")

    assert response.status_code == 200
    fields = {field["field_name"]: field for field in response.json()}
    assert set(fields) >= {"contract_no", "customer_name", "seller_name", "amount_including_tax"}
    assert fields["contract_no"]["value_text"] == "SC-001"
    assert fields["amount_including_tax"]["value_normalized"]["amount"] == 1000.0


def test_sales_walkthrough_links_audits_reviews_and_exports_report() -> None:
    task, _ = build_sales_scenario(invoice_amount=1200.0)

    link_response = client.post(f"/api/v1/tasks/{task['id']}/link-documents")
    assert link_response.status_code == 200
    assert link_response.json()["linked_document_count"] >= 6
    assert link_response.json()["relations"]

    audit_response = client.post(f"/api/v1/tasks/{task['id']}/audit")
    assert audit_response.status_code == 200
    results = {result["rule_code"]: result for result in audit_response.json()}
    assert set(results) >= {
        "SALES_MISSING_001",
        "SALES_TIME_001",
        "SALES_AMOUNT_001",
        "SALES_NAME_001",
        "SALES_QTY_001",
    }
    assert results["SALES_AMOUNT_001"]["status"] == "fail"
    assert results["SALES_AMOUNT_001"]["evidence"]["refs"]

    queue_response = client.get(f"/api/v1/review/queue?task_id={task['id']}")
    assert queue_response.status_code == 200
    assert any(item["audit_result"]["rule_code"] == "SALES_AMOUNT_001" for item in queue_response.json())

    report_response = client.post(f"/api/v1/tasks/{task['id']}/reports/control-table")
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["report_type"] == "sales_control_table"
    assert report["summary"]["scenario"] == "sales"
    assert report["summary"]["control_table_preview"][0]["customer_name"] == "Customer Co"

    with SessionLocal() as db:
        rows = db.query(ControlTableRow).filter(ControlTableRow.task_id == UUID(task["id"])).all()
        assert rows
        assert rows[0].scenario == "sales"

    download = client.get(f"/api/v1/reports/{report['id']}/download")
    assert download.status_code == 200
    assert "Sales Control Table" in workbook_sheet_names(download.content)
