from collections.abc import Iterable

from fastapi import APIRouter

from app.api.v1.routes import agent_runs
from app.api.v1.routes import agents
from app.api.v1.routes import auth
from app.api.v1.routes import bot
from app.api.v1.routes import character_lore
from app.api.v1.routes import community
from app.api.v1.routes import messages
from app.api.v1.routes import runtime_status
from app.api.v1.routes import tree
from app.api.v1.routes import worlds
from app.api.v1.routes import world_character_setup
from app.api.v1.routes import world_activity_runtime
from app.domains.device_home.public import router as device_home_router
from app.domains.identity.api.local_routes import router as local_identity_router
from app.domains.manual_social.api.routes import router as manual_social_router
from app.domains.world_characters.api.routes import router as world_character_router
from app.domains.world_packages.api.routes import router as world_package_router


class HostedRouterConfigurationError(RuntimeError):
    pass


PUBLIC_ROUTERS = (
    local_identity_router,
    device_home_router,
    world_character_router,
    manual_social_router,
    world_package_router,
    auth.public_router,
    agents.router,
    character_lore.router,
    agent_runs.router,
    bot.router,
    community.router,
    messages.router,
    runtime_status.router,
    tree.router,
    worlds.router,
    world_character_setup.router,
    world_activity_runtime.router,
)


def create_public_api_router(
    hosted_routers: Iterable[APIRouter] = (),
) -> APIRouter:
    hosted = tuple(hosted_routers)
    if len({id(router) for router in hosted}) != len(hosted):
        raise HostedRouterConfigurationError("duplicate hosted router")

    api_router = APIRouter()
    for router in (*PUBLIC_ROUTERS, *hosted):
        api_router.include_router(router)
    return api_router


public_api_router = create_public_api_router()
