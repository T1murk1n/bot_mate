
import asyncio
import os
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv

from schedule_service import (
    load_schedules,
    format_schedule,
)


BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "Не найден BOT_TOKEN. Проверь файл .env."
    )

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Пока сохраняем выбор в памяти.
# При перезапуске бота пользователь выберет группу снова.
user_groups: dict[int, str] = {}


def get_groups() -> list[str]:
    data = load_schedules()
    return list(data.get("groups", {}).keys())


def get_group_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(
                text=group,
                callback_data=f"group:{group}",
            )
        ]
        for group in get_groups()
    ]

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


def get_main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Расписание")],
            [KeyboardButton(text="Сменить группу")],
        ],
        resize_keyboard=True,
    )


@dp.message(CommandStart())
async def start(message: Message):
    user_id = message.from_user.id

    if user_id in user_groups:
        await message.answer(
            f"Твоя группа: {user_groups[user_id]}\n"
            "Нажми «Расписание», чтобы посмотреть занятия.",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        "Привет! 👋\nВыбери свою учебную группу:",
        reply_markup=get_group_keyboard(),
    )


@dp.callback_query(F.data.startswith("group:"))
async def select_group(callback: CallbackQuery):
    group = callback.data.split(":", 1)[1]

    if group not in get_groups():
        await callback.answer(
            "Такая группа не найдена.",
            show_alert=True,
        )
        return

    user_groups[callback.from_user.id] = group

    await callback.answer("Группа выбрана!")

    await callback.message.answer(
        f"Группа {group} выбрана ✅\n"
        "Теперь нажми «Расписание».",
        reply_markup=get_main_keyboard(),
    )


@dp.message(F.text == "Расписание")
async def send_schedule(message: Message):
    group = user_groups.get(message.from_user.id)

    if not group:
        await message.answer(
            "Сначала выбери учебную группу:",
            reply_markup=get_group_keyboard(),
        )
        return

    try:
        text = format_schedule(group)
        await message.answer(text)
    except ValueError as error:
        await message.answer(str(error))


@dp.message(F.text == "Сменить группу")
async def change_group(message: Message):
    await message.answer(
        "Выбери новую учебную группу:",
        reply_markup=get_group_keyboard(),
    )


async def main():
    print("Бот запущен. Для остановки нажми Ctrl+C.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())