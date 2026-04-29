from __future__ import annotations

from types import SimpleNamespace

from app.infrastructure.knowledge import DashScopeEmbeddings


def test_embed_documents_splits_requests_into_supported_batch_sizes():
    calls: list[list[str]] = []

    class FakeEmbeddingsClient:
        def create(
            self,
            *,
            model: str,
            input: list[str],
            dimensions: int,
            encoding_format: str,
        ) -> SimpleNamespace:
            calls.append(input)
            return SimpleNamespace(
                data=[
                    SimpleNamespace(embedding=[float(index), float(len(text))])
                    for index, text in enumerate(input)
                ]
            )

    service = DashScopeEmbeddings(api_key="test-key")
    service.client = SimpleNamespace(embeddings=FakeEmbeddingsClient())

    texts = [f"doc-{index}" for index in range(26)]

    embeddings = service.embed_documents(texts)

    assert len(embeddings) == 26
    assert [len(batch) for batch in calls] == [10, 10, 6]
