import pytest

from src.api.endpoints import documents
from src.api import schemas
from src.components.vector_stores.pg_vector_store import PgVectorStore


class FakePgVectorStore(PgVectorStore):
    """PgVectorStore를 상속하지만 실제 DB 연결은 수행하지 않는 스파이."""

    def __init__(self):
        self.calls = []

    async def delete_documents(self, doc_id_or_prefix: str, permission_groups):
        self.calls.append((doc_id_or_prefix, tuple(permission_groups)))
        return 1


class FakeAgent:
    def __init__(self, store):
        self.vector_store = store


@pytest.mark.anyio
async def test_delete_document_auto_prefix_for_files():
    store = FakePgVectorStore()
    agent = FakeAgent(store)
    user = schemas.UserInDB(
        user_id=1,
        username="tester",
        is_active=True,
        permission_groups=["all_users"],
        hashed_password="hash",
    )
    body = schemas.DeleteDocumentRequest(doc_id_or_prefix="factories.py")

    result = await documents.delete_indexed_document(body, user, agent)

    assert result["status"] == "success"
    assert store.calls[0] == ("file-upload-factories.py", ("all_users",))


@pytest.mark.anyio
async def test_delete_document_keeps_repo_prefix():
    store = FakePgVectorStore()
    agent = FakeAgent(store)
    user = schemas.UserInDB(
        user_id=2,
        username="tester",
        is_active=True,
        permission_groups=["core"],
        hashed_password="hash",
    )
    body = schemas.DeleteDocumentRequest(
        doc_id_or_prefix="github-repo-sentinel-core/"
    )

    result = await documents.delete_indexed_document(body, user, agent)

    assert result["status"] == "success"
    assert store.calls[0] == ("github-repo-sentinel-core/", ("core",))
