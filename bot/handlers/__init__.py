"""Handlers package — aggregates all sub-routers into a single router."""
from aiogram import Router

from .admin import router as admin_router
from .candidate import router as candidate_router
from .common import router as common_router
from .controller_db import router as controller_db_router
from .invitations import router as invitations_router

router = Router(name="root")

# Registration order matters: more specific routers first
router.include_router(admin_router)
router.include_router(controller_db_router)
router.include_router(invitations_router)
router.include_router(candidate_router)
router.include_router(common_router)
