from app.domains.operations.contracts import PollinationsFreeImageModel, PollinationsImageRouteMode

POLLINATIONS_FREE_IMAGE_MODEL_KEY = "pollinations_free_image_model"


DEFAULT_POLLINATIONS_FREE_IMAGE_MODEL: PollinationsFreeImageModel = "flux"


POLLINATIONS_FREE_IMAGE_MODEL_LABELS: dict[PollinationsFreeImageModel, str] = {
    "flux": "Pollinations · Flux Schnell",
    "zimage": "Pollinations · Z-Image Turbo",
    "sana": "Pollinations · Sana Sprint 1.6B",
    "replicate-zimage-turbo-lora": "Replicate · Z-Image Turbo LoRA",
}


POLLINATIONS_IMAGE_ROUTE_MODE_KEY = "pollinations_image_route_mode"


DEFAULT_POLLINATIONS_IMAGE_ROUTE_MODE: PollinationsImageRouteMode = "direct"


POLLINATIONS_IMAGE_ROUTE_MODE_LABELS: dict[PollinationsImageRouteMode, str] = {
    "lambda": "Lambda relay",
    "direct": "Direct",
}


POLLINATIONS_PROFILE_IMAGE_MODEL_KEY = "pollinations_profile_image_model"


DEFAULT_POLLINATIONS_PROFILE_IMAGE_MODEL: PollinationsFreeImageModel = "zimage"


POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE_KEY = "pollinations_profile_image_route_mode"


DEFAULT_POLLINATIONS_PROFILE_IMAGE_ROUTE_MODE: PollinationsImageRouteMode = "lambda"

INFO_BANNER_KEY = "agent_activity_info"


MAINTENANCE_BANNER_KEY = "agent_activity_maintenance"
