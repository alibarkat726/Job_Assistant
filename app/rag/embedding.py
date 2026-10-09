"""Fail-closed, batched embeddings. Synthetic vectors require explicit test mode."""
import hashlib
import math
from functools import cached_property

from openai import AsyncOpenAI
from app.config.settings import settings


class ProviderUnavailable(RuntimeError):
    pass


class EmbeddingService:
    dimension = 768

    @property
    def version(self) -> str:
        if settings.RAG_TEST_MODE:
            if settings.ENVIRONMENT != 'testing':
                raise ProviderUnavailable('Synthetic embeddings are restricted to testing.')
            return 'test-hash-v1:768'
        return f'openai:{settings.OPENAI_EMBEDDING_MODEL}:{self.dimension}'

    @cached_property
    def client(self):
        if not settings.OPENAI_API_KEY:
            raise ProviderUnavailable('OpenAI embeddings are not configured.')
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY,
                           timeout=settings.RAG_PROVIDER_TIMEOUT_SECONDS, max_retries=settings.RAG_PROVIDER_MAX_RETRIES)

    def validate(self, vector):
        if len(vector) != self.dimension or any(not math.isfinite(v) for v in vector):
            raise ProviderUnavailable('Invalid embedding response.')
        norm = math.sqrt(sum(v * v for v in vector))
        if norm == 0:
            raise ProviderUnavailable('Empty embedding response.')
        return [v / norm for v in vector]

    async def generate_embedding(self, text: str) -> list[float]:
        return (await self.generate_batch_embeddings([text]))[0]

    async def generate_batch_embeddings(self, texts: list[str]) -> list[list[float]]:
        version = self.version  # Validate mode before doing any work.
        if any(not text.strip() for text in texts):
            raise ValueError('Embedding input cannot be empty.')
        if version.startswith('test-'):
            return [self._generate_fallback_embedding(text) for text in texts]
        vectors = []
        batch_size = settings.RAG_EMBEDDING_BATCH_SIZE
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset:offset + batch_size]
            try:
                response = await self.client.embeddings.create(
                    input=batch, model=settings.OPENAI_EMBEDDING_MODEL, dimensions=self.dimension)
                items = sorted(response.data, key=lambda item: item.index)
                if [item.index for item in items] != list(range(len(batch))):
                    raise ProviderUnavailable('Incomplete embedding response.')
                vectors.extend(self.validate(item.embedding) for item in items)
            except ProviderUnavailable:
                raise
            except Exception as exc:
                raise ProviderUnavailable('Embedding provider unavailable.') from exc
        return vectors

    def _generate_fallback_embedding(self, text):
        if not settings.RAG_TEST_MODE or settings.ENVIRONMENT != 'testing':
            raise ProviderUnavailable('Synthetic embeddings are restricted to testing.')
        vector = []
        for index in range(self.dimension):
            digest = hashlib.sha256(f'{text.strip().lower()}:{index}'.encode()).digest()
            vector.append((int.from_bytes(digest[:4], 'big') / 0xFFFFFFFF) * 2 - 1)
        return self.validate(vector)


embedding_service = EmbeddingService()
