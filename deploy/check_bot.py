"""Validate configuration and Telegram connectivity without exposing secrets."""

import asyncio
from datetime import timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot import TOKEN
from schedule_service import START_DATE, format_schedule, load_schedules


async def main():
    groups = load_schedules().get("groups", {})
    if not groups:
        raise SystemExit("No schedule groups found.")
    for group in groups:
        for day in range(14):
            text = format_schedule(group, START_DATE + timedelta(days=day))
            if not text or len(text) > 4096:
                raise SystemExit("Invalid Telegram schedule message.")

    async with Bot(token=TOKEN) as bot:
        try:
            identity = await bot.get_me()
            webhook = await bot.get_webhook_info()
        except TelegramAPIError as error:
            raise SystemExit(f"Telegram check failed: {type(error).__name__}") from None
        except Exception as error:
            raise SystemExit(f"Connection check failed: {type(error).__name__}") from None
        if webhook.url:
            raise SystemExit("An existing Telegram webhook is configured; polling was not started.")
        print(f"Telegram identity verified: @{identity.username} (id={identity.id})")
        print(f"Schedule verified: {len(groups)} groups, {len(groups) * 14} cases")


if __name__ == "__main__":
    asyncio.run(main())
