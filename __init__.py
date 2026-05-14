from aiogram import Router

from games.bank import router as bank_router
from games.gold import router as gold_router
from games.mines import router as mines_router
from games.tower import router as tower_router

router = Router()
router.include_router(bank_router)
router.include_router(gold_router)
router.include_router(mines_router)
router.include_router(tower_router)
