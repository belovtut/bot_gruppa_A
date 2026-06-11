"""Main bot module — entry-point, scheduler, startup / shutdown hooks."""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from apscheduler.schedulers.asyncio import AsyncIOScheduler
# Импортируем модуль для настройки кастомного сервера API
from aiogram.client.telegram import TelegramAPIServer

from bot import config
from bot.handlers import router
from bot.logging_config import setup_logging
from bot.services.reminders import run_reminder_check
from database import Database

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

async def main() -> None:
    """Initialize and run the bot."""
    setup_logging(stream=sys.stdout)

    if not config.SETTINGS.bot_token:
        logger.error(
            "BOT_TOKEN is not set! Create a .env file with BOT_TOKEN=your_token_here"
        )
        return
    
    PROXY_URL = "https://gruppa-a-tg-prx.tobi3-14zda.workers.dev"

    custom_api_server = TelegramAPIServer.from_base(PROXY_URL)

    bot = Bot(
        token=config.SETTINGS.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        api_server=custom_api_server,
    )
    dp = Dispatcher()

    # Database
    db = Database(config.SETTINGS.db_path)
    await db.init_db()
    logger.info("Database initialized at %s", config.SETTINGS.db_path)

    # Scheduler for reminders
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_reminder_check,
        "interval",
        minutes=30,
        args=[bot, db],
        id="reminder_check",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Reminder scheduler started (check every 30 min, threshold %sh)",
        config.SETTINGS.reminder_hours,
    )

    # Handlers
    dp.include_router(router)

    # Log admin IDs
    if config.SETTINGS.admin_ids:
        logger.info("Admin IDs: %s", list(config.SETTINGS.admin_ids))
    else:
        logger.warning("No admin IDs configured! Set ADMIN_IDS in .env")

    try:
        logger.info("Starting bot polling…")
        await dp.start_polling(bot, db=db)
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
