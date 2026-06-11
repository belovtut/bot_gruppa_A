"""Run the Telegram bot: ``python -m bot`` from the repository root."""
import asyncio

from bot.app import main

if __name__ == "__main__":
    asyncio.run(main())
