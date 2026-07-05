from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def auth_headers(email: str, password: str = "test-password") -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def create_user(email: str, role_codes: list[str]) -> None:
    response = client.post(
        "/api/v1/users",
        json={
            "email": email,
            "password": "test-password",
            "full_name": email.split("@")[0],
            "role_codes": role_codes,
        },
    )
    assert response.status_code == 200


def create_rag_document(
    *,
    knowledge_base: str = "regulation",
    title: str = "Revenue Guidance",
    text: str = "Revenue recognition requires persuasive evidence and consistent policy.",
    metadata_json: str = '{"issuer":"SEC","topic":"revenue"}',
    headers: dict[str, str] | None = None,
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
        headers=headers,
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
    assert "Revenue Guidance" in result["answer"]
    assert "Revenue recognition requires documented contract evidence" in result["answer"]
    assert result["citations"]
    assert result["provider_info"]["embedding_provider_kind"] == "deterministic_fallback"
    assert result["provider_info"]["answer_provider_kind"] == "deterministic_fallback"
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
    task = client.post("/api/v1/tasks", json={"name": "RAG scoped task", "scenario": "procurement"}).json()
    public_doc = create_rag_document(
        knowledge_base="regulation",
        title="Public Cash Rule",
        text="Cash disbursement approvals require supporting invoices.",
        metadata_json='{"scope":"public"}',
    )
    workpaper_doc = create_rag_document(
        knowledge_base="workpaper",
        title="Task Workpaper Cash",
        text="Cash disbursement approvals in the scoped task include reviewer correction notes.",
        metadata_json=f'{{"scope":"workpaper","task_id":"{task["id"]}"}}',
    )
    index_document(public_doc["id"])
    index_document(workpaper_doc["id"])

    public_result = query_rag("cash disbursement approvals", "regulation")
    workpaper_result = query_rag("cash disbursement approvals", "workpaper", metadata_filter={"task_id": task["id"]})

    assert public_result["status"] == "answer"
    assert {citation["knowledge_base"] for citation in public_result["citations"]} == {"regulation"}
    assert {citation["title"] for citation in public_result["citations"]} == {"Public Cash Rule"}
    assert workpaper_result["status"] == "answer"
    assert {citation["knowledge_base"] for citation in workpaper_result["citations"]} == {"workpaper"}
    assert {citation["title"] for citation in workpaper_result["citations"]} == {"Task Workpaper Cash"}


def test_workpaper_documents_require_task_scope_and_filter_by_user_scope() -> None:
    create_user("owner-one@example.com", ["analyst"])
    create_user("owner-two@example.com", ["analyst"])
    owner_one_headers = auth_headers("owner-one@example.com")
    owner_two_headers = auth_headers("owner-two@example.com")
    task_one = client.post("/api/v1/tasks", json={"name": "Owner one task", "scenario": "procurement"}, headers=owner_one_headers).json()
    task_two = client.post("/api/v1/tasks", json={"name": "Owner two task", "scenario": "procurement"}, headers=owner_two_headers).json()

    missing_scope = client.post(
        "/api/v1/rag/documents",
        data={
            "knowledge_base": "workpaper",
            "title": "Missing Scope",
            "source_type": "synthetic_text",
            "content_text": "workpaper text",
        },
    )
    assert missing_scope.status_code == 400
    assert missing_scope.json()["detail"] == "workpaper RAG documents require metadata.task_id"

    doc_one = create_rag_document(
        knowledge_base="workpaper",
        title="Owner One Workpaper",
        text="scope guarded evidence for owner one",
        metadata_json=f'{{"task_id":"{task_one["id"]}"}}',
    )
    doc_two = create_rag_document(
        knowledge_base="workpaper",
        title="Owner Two Workpaper",
        text="scope guarded evidence for owner two",
        metadata_json=f'{{"task_id":"{task_two["id"]}"}}',
    )
    index_document(doc_one["id"])
    index_document(doc_two["id"])

    owner_one_docs = client.get("/api/v1/rag/documents?knowledge_base=workpaper", headers=owner_one_headers)
    assert owner_one_docs.status_code == 200
    assert {document["title"] for document in owner_one_docs.json()} == {"Owner One Workpaper"}

    admin_result = query_rag("scope guarded owner two", "workpaper", metadata_filter={"task_id": task_two["id"]})
    chunk_id = admin_result["citations"][0]["chunk_id"]
    forbidden_chunk = client.get(f"/api/v1/rag/chunks/{chunk_id}", headers=owner_one_headers)
    assert forbidden_chunk.status_code == 403


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
