"""Connect the original Character URL prefix to the actual route owners."""
from fastapi import APIRouter
from app.domains.routines import router as routine_routes
from app.domains.relationships import router as relationship_routes

router = APIRouter(prefix="/characters", tags=["world-activity-runtime"])
router.include_router(routine_routes.router)
router.include_router(relationship_routes.router)
