from fastapi import APIRouter

from cat.routes.admins.crud import router as crud_router
from cat.routes.admins.plugins import router as plugins_router

router = APIRouter(prefix="/admins")


router.include_router(crud_router)
router.include_router(plugins_router)
