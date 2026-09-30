"""V4.5 Full: account checks, conservative local preflight and precise reference."""
import base64
import hashlib
import re
import secrets
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
import sentencepiece
from app.domains.media.generation_contracts import NovelOptions, ImagePreparationError, ImageSubmissionError, ImageResult
from app.integrations.image_api import ImageHttp
from app.integrations.media.images import validate_generated_media_content

MODEL = "nai-diffusion-4-5-full"
TOKENIZER_HASH = "d60acb128cf7b7f2536e8f38a5b18a05535c9e14c7a355904270e15b0945ea86"
PREFLIGHT_VERSION = "v4.5-t5-weight-spans-v1"
WEIGHT_MARKUP = re.compile(r"(?:[+-]?(?:\d+(?:\.\d*)?|\.\d+))?::|[{}\[\]]")


def validate_t5_prompt(text):
    """Check the pinned local resource; return an estimate, not a server count.

    Documented weight operators delimit text spans for this local estimate.
    The original prompt is sent unchanged. This neither truncates nor certifies
    the deployed V4.5 parser/tokenizer. Live comparison remains separate.
    """
    path = Path(__file__).with_name("novelai_resources") / "t5.spiece.model"
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != TOKENIZER_HASH:
        raise ImagePreparationError("novelai_tokenizer_unavailable")
    tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(path))
    # Independently implement only the documented {}, [] and numerical ::
    # operators for preflight. Encoding each span avoids merging words across
    # weight boundaries. We do not evaluate weights or rewrite the API prompt.
    spans = [span for span in WEIGHT_MARKUP.split(text) if span.strip()]
    if not spans:
        raise ImagePreparationError("novelai_prompt_empty")
    ids = [token for span in spans for token in tokenizer.encode(span)]
    if tokenizer.unk_id() in ids:
        raise ImagePreparationError("novelai_prompt_contains_unsupported_text")
    # Reserve EOS; never truncate or silently translate the user's text.
    if len(ids) + 1 > 512:
        raise ImagePreparationError("novelai_t5_prompt_limit")
    return len(ids) + 1


def precise_pixels(content):
    with Image.open(BytesIO(content)) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        size = (1024,1536) if image.height > image.width else (1536,1024) if image.width > image.height else (1472,1472)
        image = ImageOps.pad(image, size, color="black")
        output = BytesIO()
        image.save(output, "PNG")
        return base64.b64encode(output.getvalue()).decode()


def _caption(text):
    return {"caption": {"base_caption": text, "char_captions": []}, "use_coords": False, "use_order": True}


class NovelImageClient:
    def __init__(self, http=None):
        self.http = http or ImageHttp()

    @staticmethod
    def prompt_validation():
        path = Path(__file__).with_name("novelai_resources") / "t5.spiece.model"
        resource_verified = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == TOKENIZER_HASH
        # Resource integrity authorizes local preflight, not a claim of exact
        # server equivalence. A valid key can exercise the actual API without
        # changing that evidence status or introducing an override switch.
        return {"model": MODEL, "state": "local_preflight" if resource_verified else "unavailable",
            "exact_verified": False, "generation_available": resource_verified,
            "resource_verified": resource_verified, "resource_sha256": TOKENIZER_HASH,
            "preflight_version": PREFLIGHT_VERSION,
            "local_token_budget": 512, "server_equivalence": "unverified",
            "reason": "novelai_prompt_validation_unverified" if resource_verified else "novelai_tokenizer_unavailable"}

    async def subscription(self, key):
        response = await self.http.request("GET", "https://api.novelai.net/user/subscription", key=key, timeout=15)
        payload = response.json()
        expiry = payload.get("expiresAt")
        now = datetime.now(timezone.utc).timestamp()
        valid = payload.get("active") is True and payload.get("tier") == 3 and isinstance(expiry, (float,int)) and expiry > now
        return {"opus_verified": valid, "expires_at": expiry if isinstance(expiry,(float,int)) else None,
            "checked_at": now, "model": MODEL, "max_steps": 28, "max_area": 1048576}

    async def generate(self, request, key, reference, *, on_submit=None):
        if request.model != MODEL or request.provider != "novelai":
            raise ImagePreparationError("novelai_model_not_supported")
        options = NovelOptions.model_validate(request.options)
        validate_t5_prompt(request.positive)
        if request.negative:
            validate_t5_prompt(request.negative)
        if options.mode == "opus_free":
            if reference is not None:
                raise ImagePreparationError("opus_free_reference_forbidden")
            if not (await self.subscription(key))["opus_verified"]:
                raise ImagePreparationError("opus_benefit_unverified")
        params = {"params_version": 3, "width": options.width, "height": options.height,
            "steps": options.steps, "scale": options.scale, "sampler": options.sampler,
            "noise_schedule": options.noise_schedule, "cfg_rescale": options.cfg_rescale,
            "seed": secrets.randbits(32) if options.seed == -1 else options.seed, "n_samples": 1,
            "negative_prompt": request.negative or "", "v4_prompt": _caption(request.positive),
            "v4_negative_prompt": _caption(request.negative or ""), "sm": False, "sm_dyn": False,
            "dynamic_thresholding": options.decrisper, "qualityToggle": False, "ucPreset": 3,
            "legacy": False, "legacy_v3_extend": False}
        if options.variety_boost:
            params["skip_cfg_above_sigma"] = 19.0
        if reference is not None:
            params.update(director_reference_images=[precise_pixels(reference)],
                director_reference_descriptions=[_caption(options.reference_type)],
                director_reference_information_extracted=[1.0],
                director_reference_strength_values=[options.reference_strength],
                director_reference_secondary_strength_values=[options.reference_fidelity])
        if on_submit:
            await on_submit()
        response = await self.http.request("POST", "https://image.novelai.net/ai/generate-image", key=key,
            json={"input": request.positive, "model": MODEL, "action": "generate", "parameters": params},
            headers={"Accept": "application/json"})
        try:
            if response.headers.get("content-type", "").split(";")[0] == "application/zip":
                from zipfile import ZipFile
                with ZipFile(BytesIO(response.content)) as archive:
                    members = [item for item in archive.infolist() if not item.is_dir()]
                    if len(members) != 1 or members[0].file_size > 12*1024*1024:
                        raise ValueError()
                    content = archive.read(members[0])
            else:
                images = response.json()["images"]
                if len(images) != 1:
                    raise ValueError()
                content = base64.b64decode(images[0]["image"], validate=True)
            with Image.open(BytesIO(content)) as decoded:
                mime = Image.MIME[decoded.format]
            validate_generated_media_content(mime, content, max_bytes=12 * 1024 * 1024)
        except Exception as exc:
            raise ImageSubmissionError("novelai_result_invalid") from exc
        return ImageResult(content, mime)
