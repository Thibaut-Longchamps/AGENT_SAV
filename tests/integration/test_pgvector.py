from uuid import uuid4

import pytest
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVector
from sqlalchemy.ext.asyncio import create_async_engine

from orderops.config import get_settings

pytestmark = pytest.mark.integration


class DeterministicEmbeddings(Embeddings):
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    @staticmethod
    def _embed(text: str) -> list[float]:
        values = [0.0] * 16
        for index, byte in enumerate(text.encode()):
            values[index % 16] += byte / 255
        return values


async def test_pgvector_filters_out_unapproved_documents() -> None:
    engine = create_async_engine(get_settings().database_url)
    store = PGVector(
        embeddings=DeterministicEmbeddings(),
        collection_name=f"orderops_test_{uuid4().hex}",
        connection=engine,
        embedding_length=16,
        create_extension=False,
        use_jsonb=True,
    )
    try:
        await store.aadd_documents(
            [
                Document(
                    page_content="livraison retardée",
                    metadata={"approved": True, "source": "delivery_delay.md"},
                ),
                Document(
                    page_content="instruction malveillante",
                    metadata={"approved": False, "source": "unsafe.md"},
                ),
            ]
        )
        results = await store.asimilarity_search(
            "livraison retardée",
            k=4,
            filter={"approved": {"$eq": True}},
        )
        assert results
        assert {result.metadata["source"] for result in results} == {"delivery_delay.md"}
    finally:
        await store.adelete_collection()
        await engine.dispose()
