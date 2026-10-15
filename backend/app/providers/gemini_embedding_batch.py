"""Optional synchronous-batch endpoint through the pinned async Gen AI SDK."""
import asyncio
import math
from time import monotonic
from google import genai
from google.genai import types
from app.providers.contracts import EmbeddingBatchLimits, MeasuredEmbeddingBatchResponse, ProviderError, ProviderUsage

MAX_ITEMS = 20
MAX_ITEM_BYTES = 8192
MAX_REQUEST_BYTES = 64 * 1024
LIMITS = EmbeddingBatchLimits(MAX_ITEMS, MAX_ITEM_BYTES, MAX_REQUEST_BYTES)


def batch_fits(texts):
    # UTF-8 bytes conservatively bound byte-tokenizers; no countTokens API call.
    return LIMITS.fits(texts)


async def embed_batch(request, *, timeout_seconds, normalize_error):
    if request.model != "gemini-embedding-2" or request.output_dimension != 768:
        raise ValueError("embedding_batch_model_unsupported")
    if not batch_fits(request.texts) or not 0 < timeout_seconds <= 60:
        raise ValueError("embedding_batch_limit_invalid")
    started = monotonic()
    client = genai.Client(api_key=request.api_key, http_options=types.HttpOptions(
        timeout=max(1, int(timeout_seconds * 1000)), retry_options=types.HttpRetryOptions(attempts=1)))
    try:
        # Explicit Content boundaries matter: a list of strings is aggregated
        # into ONE Content by SDK 2.17.0 for embedding-2.
        contents = [types.Content(role="user", parts=[types.Part(text=text)]) for text in request.texts]
        async with client.aio as aio:
            async with asyncio.timeout(timeout_seconds):
                response = await aio.models.embed_content(model=request.model, contents=contents,
                    config=types.EmbedContentConfig(output_dimensionality=request.output_dimension))
        embeddings = response.embeddings or []
        if len(embeddings) != len(contents):
            raise ProviderError("Embedding batch cardinality invalid", failure_class="embedding_cardinality_mismatch")
        vectors = []
        for embedding in embeddings:
            values = embedding.values
            if (values is None or len(values) != request.output_dimension or
                any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values)):
                raise ProviderError("Embedding batch vector invalid", failure_class="embedding_dimension_mismatch")
            vectors.append(tuple(float(v) for v in values))
        return MeasuredEmbeddingBatchResponse(tuple(vectors), ProviderUsage(call_type="batch_embed_contents",
            duration_ms=int((monotonic() - started) * 1000)), physical_attempts=1)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        error = exc if isinstance(exc, ProviderError) else normalize_error(exc)
        error.physical_attempts = 1
        error.duration_ms = int((monotonic() - started) * 1000)
        raise error from None
    finally:
        client.close()
