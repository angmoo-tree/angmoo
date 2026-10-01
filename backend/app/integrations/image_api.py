"""Dedicated NanoGPT/OpenRouter image API, with per-endpoint admission."""
import base64
from io import BytesIO
from urllib.parse import quote
import httpx
from PIL import Image
from app.domains.media.api_image_policy import endpoint_parameters, validate_api_options, validate_reference_metadata
from app.domains.media.generation_contracts import GenerationRequest, ImageResult, ImagePreparationError, ImageSubmissionError, MODEL_CATALOG
from app.integrations.media.images import ImageBytesError, inspect_image_bytes

API_ROOTS = {"nanogpt": "https://api.nano-gpt.com/api/v1/images", "openrouter": "https://openrouter.ai/api/v1/images"}
MAX_RESULT_BYTES = 12 * 1024 * 1024


def prepare_api_reference(endpoint, content):
    """Endpoint-specific send-time encoding; the owned asset stays immutable."""
    try:
        info = inspect_image_bytes(content, max_bytes=10 * 1024 * 1024)
    except ImageBytesError as exc:
        raise ImagePreparationError("reference_pixels_invalid") from exc
    constraints = endpoint.get("input_reference_constraints") or {}
    if not isinstance(constraints, dict) or not isinstance(constraints.get("route", constraints), dict):
        raise ImagePreparationError("reference_constraints_unverified")
    route = constraints.get("route", constraints)
    formats = route.get("formats", ["png"])
    if not isinstance(formats, list) or not all(isinstance(item, str) for item in formats):
        raise ImagePreparationError("reference_constraints_unverified")
    if info.content_type.removeprefix("image/") not in formats:
        if "png" not in formats:
            raise ImagePreparationError("reference_format_invalid")
        with Image.open(BytesIO(content)) as image:
            output = BytesIO()
            image.save(output, "PNG")
            content = output.getvalue()
        try:
            info = inspect_image_bytes(content, max_bytes=10 * 1024 * 1024, declared_mime="image/png")
        except ImageBytesError as exc:
            raise ImagePreparationError("reference_pixels_invalid") from exc
    validate_reference_metadata(endpoint, width=info.width, height=info.height,
        byte_size=info.byte_size, content_type=info.content_type)
    return content, info


def parse_image_result(response):
    """The dedicated images endpoint returns one strict base64 image object."""
    def invalid(stage):
        return ImageSubmissionError("provider_image_invalid", stage=stage)
    try:
        body = response.json()
    except (ValueError, UnicodeError) as exc:
        raise invalid("json") from exc
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise invalid("envelope")
    if len(body["data"]) != 1:
        raise invalid("cardinality")
    image = body["data"][0]
    if not isinstance(image, dict):
        raise invalid("envelope")
    encoded = image.get("b64_json")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_RESULT_BYTES + 2) // 3):
        raise invalid("base64")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeError) as exc:
        raise invalid("base64") from exc
    try:
        info = inspect_image_bytes(content, max_bytes=MAX_RESULT_BYTES, declared_mime=image.get("media_type"))
    except ImageBytesError as exc:
        raise invalid(exc.stage) from exc
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else None
    return ImageResult(content, info.content_type, usage=usage)


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
                # aiter_bytes already decoded HTTP content encoding. Reusing
                # gzip/br headers would make the materialized Response decode
                # the same body again; its original wire length is also stale.
                headers = {name: value for name, value in response.headers.items()
                    if name.lower() not in {"content-encoding", "content-length", "transfer-encoding"}}
                return httpx.Response(response.status_code, headers=headers, content=bytes(data))
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
        if reference is not None:
            support = endpoint_parameters(self.provider, endpoint).get("input_references", {})
            if not MODEL_CATALOG[f"{self.provider}:{request.model}"][2] or support.get("max", 0) < 1:
                raise ImagePreparationError("reference_not_supported")
            reference, info = prepare_api_reference(endpoint, reference)
            payload["input_references"] = [{"type": "image_url", "image_url": {"url": f"data:{info.content_type};base64," + base64.b64encode(reference).decode()}}]
        if self.provider == "openrouter":
            tag = endpoint.get("provider_tag")
            if not tag:
                raise ImagePreparationError("provider_route_unverified")
            payload["provider"] = {"only": [tag], "allow_fallbacks": False}
        if on_submit:
            await on_submit()
        response = await self.http.request("POST", API_ROOTS[self.provider], key=key, json=payload)
        return parse_image_result(response)
