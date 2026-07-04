from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def create_rag_document(
    *,
    knowledge_base: str = "regulation",
    title: str = "Revenue Guidance",
    text: str = "Revenue recognition requires persuasive evidence and consistent policy.",
    metadata_json: str = '{"issuer":"SEC","topic":"revenue"}',
) -> dict:
    response = client.post(
        "/api/v1/rag/documents",
        data={
            "knowledge_base": knowledge_base,
            "title": title,
            "source_type": "synthetic_text",
            "metadata_json": metadata_json,
            "content_text": text,
            "created_by": "rag_test",
        },
    )
    assert response.status_code == 200
    return response.json()


def index_document(document_id: str) -> dict:
    response = client.post(f"/api/v1/rag/documents/{document_id}/index")
    assert response.status_code == 200
    return response.json()


def query_rag(query: str, knowledge_base: str = "regulation", metadata_filter: dict | None = None) -> dict:
    response = client.post(
        "/api/v1/rag/query",
        json={
            "query": query,
            "knowledge_base": knowledge_base,
            "top_k": 3,
            "metadata_filter": metadata_filter or {},
        },
    )
    assert response.status_code == 200
    return response.json()


def test_rag_document_index_query_and_citation_schema() -> None:
    document = create_rag_document(
        text=(
            "Section 1 Revenue recognition requires documented contract evidence.\n\n"
            "Section 2 The audit team should cite the source paragraph."
        )
    )
    index_result = index_document(document["id"])
    assert index_result["chunk_count"] == 2

    result = query_rag("revenue recognition contract evidence")

    assert result["status"] == "answer"
    assert result["citations"]
    citation = result["citations"][0]
    assert citation["chunk_id"]
    assert citation["document_id"] == document["id"]
    assert citation["knowledge_base"] == "regulation"
    assert citation["title"] == "Revenue Guidance"
    assert citation["score"] > 0
    assert "revenue" in citation["quote"].lower()
    assert citation["metadata"]["issuer"] == "SEC"

    chunk_response = client.get(f"/api/v1/rag/chunks/{citation['chunk_id']}")
    assert chunk_response.status_code == 200
    assert chunk_response.json()["rag_document_id"] == document["id"]


def test_rag_metadata_filter_limits_results() -> None:
    sec_doc = create_rag_document(
        title="SEC Revenue",
        text="Revenue recognition disclosure guidance for issuers.",
        metadata_json='{"issuer":"SEC","topic":"revenue"}',
    )
    fasb_doc = create_rag_document(
        title="FASB Revenue",
        text="Revenue recognition measurement guidance for contracts.",
        metadata_json='{"issuer":"FASB","topic":"revenue"}',
    )
    index_document(sec_doc["id"])
    index_document(fasb_doc["id"])

    result = query_rag("revenue recognition guidance", metadata_filter={"issuer": "FASB"})

    assert result["status"] == "answer"
    assert result["citations"]
    assert {citation["title"] for citation in result["citations"]} == {"FASB Revenue"}


def test_rag_no_answer_when_evidence_is_insufficient() -> None:
    document = create_rag_document(text="Inventory observation guidance covers stock count procedures.")
    index_document(document["id"])

    result = query_rag("cryptocurrency custody valuation")

    assert result["status"] == "no_answer"
    assert result["citations"] == []
    assert "Evidence insufficient" in result["answer"]


def test_workpaper_and_public_knowledge_bases_are_isolated() -> None:
    public_doc = create_rag_document(
        knowledge_base="regulation",
        title="Public Cash Rule",
        text="Cash disbursement approvals require supporting invoices.",
        metadata_json='{"scope":"public"}',
    )
    workpaper_doc = create_rag_document(
        knowledge_base="workpaper",
        title="Task Workpaper Cash",
        text="Cash disbursement approvals in task WP-001 include reviewer correction notes.",
        metadata_json='{"scope":"workpaper","task_id":"WP-001"}',
    )
    index_document(public_doc["id"])
    index_document(workpaper_doc["id"])

    public_result = query_rag("cash disbursement approvals", "regulation")
    workpaper_result = query_rag("cash disbursement approvals", "workpaper")

    assert public_result["status"] == "answer"
    assert {citation["knowledge_base"] for citation in public_result["citations"]} == {"regulation"}
    assert {citation["title"] for citation in public_result["citations"]} == {"Public Cash Rule"}
    assert workpaper_result["status"] == "answer"
    assert {citation["knowledge_base"] for citation in workpaper_result["citations"]} == {"workpaper"}
    assert {citation["title"] for citation in workpaper_result["citations"]} == {"Task Workpaper Cash"}


def test_invalid_metadata_json_is_rejected() -> None:
    response = client.post(
        "/api/v1/rag/documents",
        data={
            "knowledge_base": "regulation",
            "title": "Bad Metadata",
            "source_type": "synthetic_text",
            "metadata_json": "[]",
            "content_text": "Some content",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "metadata must be a JSON object"
