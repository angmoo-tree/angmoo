"""Dedicated NanoGPT/OpenRouter image API, with per-endpoint admission."""
import base64
from io import BytesIO
from urllib.parse import quote
import httpx
from PIL import Image, UnidentifiedImageError
from app.domains.media.api_image_policy import endpoint_parameters, validate_api_options, validate_reference_metadata
from app.domains.media.generation_contracts import GenerationRequest, ImageResult, ImagePreparationError, ImageSubmissionError, MODEL_CATALOG
from app.integrations.media.images import validate_generated_media_content
from app.domains.media.contracts import InvalidProfileMediaError

API_ROOTS = {"nanogpt": "https://api.nano-gpt.com/api/v1/images", "openrouter": "https://openrouter.ai/api/v1/images"}


class ImageHttp:
    def __init__(self, client: httpx.AsyncClient | None = None):
        self.client = client

    async def request(self, method, url, *, key=None, timeout=120.0, **kwargs):
        headers = {**kwargs.pop("headers", {}), **({"Authorization": f"Bearer {key}"} if key else {})}
        limit = 24 * 1024 * 1024 if method == "POST" or "/view" in url else 2 * 1024 * 1024
        owned = self.client is None
        client = self.client or httpx.AsyncClient(follow_redirects=False, trust_env=False)
        try:
            async with client.stream(method, url, headers=headers, timeout=timeout, **kwargs) as response:
                if response.status_code >= 300:
                    # Never put remote bodies, URLs with secrets or headers into exceptions.
                    raise ImageSubmissionError(f"provider_http_{response.status_code}", outcome_unknown=method == "POST" and response.status_code >= 500)
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > limit:
                        raise ImageSubmissionError("provider_response_too_large", outcome_unknown=method == "POST")
                return httpx.Response(response.status_code, headers=response.headers, content=bytes(data))
        except httpx.TransportError as exc:
            raise ImageSubmissionError("provider_transport_error", outcome_unknown=method == "POST") from exc
        finally:
            if owned:
                await client.aclose()


class ImageApiClient:
    def __init__(self, provider, http=None):
        if provider not in API_ROOTS:
            raise ValueError("image_api_provider_invalid")
        self.provider, self.http = provider, http or ImageHttp()

    async def discover(self, model):
        if f"{self.provider}:{model}" not in MODEL_CATALOG:
            raise ImagePreparationError("model_not_supported")
        response = await self.http.request("GET", f"{API_ROOTS[self.provider]}/models/{quote(model, safe='/')}/endpoints")
        payload = response.json()
        if payload.get("id") != model or not payload.get("endpoints"):
            raise ImagePreparationError("model_endpoint_unavailable")
        endpoints = payload["endpoints"]
        # Select one real endpoint. The routing identity is persisted with the request.
        endpoint = endpoints[0]
        if self.provider == "openrouter" and not endpoint.get("provider_tag"):
            raise ImagePreparationError("provider_route_unverified")
        return endpoint

    async def generate(self, request: GenerationRequest, key, reference: bytes | None, *, on_submit=None):
        if request.provider != self.provider or f"{self.provider}:{request.model}" not in MODEL_CATALOG:
            raise ImagePreparationError("model_not_supported")
        endpoint = request.endpoint
        if not endpoint:
            raise ImagePreparationError("model_endpoint_unavailable")
        options = validate_api_options(self.provider, endpoint, request.options)
        payload = {"model": request.model, "prompt": request.positive, "n": 1, **options}
        if reference:
            support = endpoint_parameters(self.provider, endpoint).get("input_references", {})
            if not MODEL_CATALOG[f"{self.provider}:{request.model}"][2] or support.get("max", 0) < 1:
                raise ImagePreparationError("reference_not_supported")
            try:
                with Image.open(BytesIO(reference)) as decoded:
                    mime = Image.MIME.get(decoded.format)
                    if mime != "image/png" or getattr(decoded, "n_frames", 1) != 1:
                        raise ImagePreparationError("reference_format_invalid")
                    validate_reference_metadata(endpoint, width=decoded.width, height=decoded.height,
                        byte_size=len(reference), content_type=mime)
                    decoded.verify()
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
                raise ImagePreparationError("reference_pixels_invalid") from exc
            payload["input_references"] = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(reference).decode()}}]
        if self.provider == "openrouter":
            tag = endpoint.get("provider_tag")
            if not tag:
                raise ImagePreparationError("provider_route_unverified")
            payload["provider"] = {"only": [tag], "allow_fallbacks": False}
        if on_submit:
            await on_submit()
        response = await self.http.request("POST", API_ROOTS[self.provider], key=key, json=payload)
        try:
            body = response.json()
            images = body["data"]
            if len(images) != 1:
                raise ValueError()
            image = images[0]
            content = base64.b64decode(image["b64_json"], validate=True)
            if len(content) > 12 * 1024 * 1024:
                raise ValueError()
            content_type = image.get("media_type") or "image/png"
            validate_generated_media_content(content_type, content, max_bytes=12 * 1024 * 1024)
            usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
        except (KeyError, ValueError, TypeError, InvalidProfileMediaError) as exc:
            raise ImageSubmissionError("provider_image_invalid") from exc
        return ImageResult(content, content_type, usage=usage)
