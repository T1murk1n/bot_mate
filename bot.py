import asyncio
import os
from datetime import date, timedelta
from pathlib import Path

import re
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
    START_DATE,
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

# Выбранная группа хранится в памяти.
# При перезапуске бота её потребуется ввести заново.
user_groups: dict[int, str] = {}


def get_groups() -> list[str]:
    """Возвращает список доступных учебных групп."""
    data = load_schedules()
    return list(data.get("groups", {}).keys())


def find_group(user_input: str) -> str | None:
    """Находит группу без учёта регистра и крайних пробелов."""
    normalized_input = user_input.strip().casefold()

    for group in get_groups():
        if group.casefold() == normalized_input:
            return group

    return None


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт основное меню бота."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Расписание")],
            [KeyboardButton(text="Звонки")],
        ],
        resize_keyboard=True,
    )


def get_schedule_keyboard(
    selected_date: date,
) -> InlineKeyboardMarkup:
    """Создаёт кнопки переключения дней расписания."""
    previous_day = selected_date - timedelta(days=1)
    next_day = selected_date + timedelta(days=1)

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="◀️ Предыдущий день",
                    callback_data=f"day:{previous_day.isoformat()}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Следующий день ▶️",
                    callback_data=f"day:{next_day.isoformat()}",
                )
            ],
        ]
    )


@dp.message(CommandStart())
async def start(message: Message):
    """Просит пользователя указать учебную группу."""
    user_id = message.from_user.id
    current_group = user_groups.get(user_id)

    if current_group:
        await message.answer(
            f"Текущая группа: {current_group}\n\n"
            "Введи название другой группы, чтобы изменить её, "
            "или нажми «Расписание», чтобы продолжить.",
            reply_markup=get_main_keyboard(),
        )
        return

    await message.answer(
        "Привет! 👋\n\n"
        "Введи название своей учебной группы.\n"
        "Например: ПРИ-О-23/1"
    )


@dp.message(F.text.regexp(r"(?i)^препод\s+(.+?)\s*$"))
async def find_teacher(message: Message):
    """Находит полное ФИО преподавателя по фамилии."""
    from schedule_service import load_details

    match = re.match(
        r"(?i)^препод\s+(.+?)\s*$",
        message.text.strip(),
    )

    if not match:
        return

    surname = match.group(1).strip()

    details = load_details()
    teachers = details.get("teachers", {})

    # Ищем фамилию без учёта регистра.
    for key, full_name in teachers.items():
        if key.strip().casefold() == surname.casefold():
            await message.answer(
                f"👨‍🏫 {full_name}"
            )
            return

    await message.answer(
        f"❌ Преподаватель «{surname}» не найден.\n\n"
        "Проверь фамилию и попробуй ещё раз."
    )


@dp.message(F.text.regexp(r"(?i)^расписание$"))
async def send_schedule(message: Message):
    """Отправляет расписание на текущий день."""
    group = user_groups.get(message.from_user.id)

    if not group:
        await message.answer(
            "Сначала введи название своей учебной группы."
        )
        return

    selected_date = date.today()

    if selected_date < START_DATE:
        await message.answer(
            "Расписание пока недоступно: "
            "учебная неделя ещё не началась."
        )
        return

    try:
        text = format_schedule(group, selected_date)

        await message.answer(
            text,
            reply_markup=get_schedule_keyboard(selected_date),
        )

    except ValueError as error:
        await message.answer(str(error))


@dp.message(F.text.regexp(r"(?i)^звонки$"))
async def send_bell_schedule(message: Message):
    """Отправляет расписание звонков."""
    await message.answer(
        "🔔 Расписание звонков\n\n"
        "1️⃣  08:00–09:20\n"
        "2️⃣  09:30–10:50\n"
        "3️⃣  11:00–12:20\n"
        "4️⃣  12:45–14:05\n"
        "5️⃣  14:15–15:35\n"
        "6️⃣  15:45–17:05\n"
        "7️⃣  17:15–18:35\n"
        "8️⃣  18:40–20:00",
        reply_markup=get_main_keyboard(),
    )


@dp.callback_query(F.data.startswith("day:"))
async def change_schedule_day(callback: CallbackQuery):
    """Переключает расписание на выбранную дату."""
    group = user_groups.get(callback.from_user.id)

    if not group:
        await callback.answer(
            "Сначала введи название своей учебной группы.",
            show_alert=True,
        )
        return

    try:
        selected_date = date.fromisoformat(
            callback.data.split(":", 1)[1]
        )
    except (ValueError, TypeError, AttributeError):
        await callback.answer(
            "Некорректная дата.",
            show_alert=True,
        )
        return

    if selected_date < START_DATE:
        await callback.answer(
            "Расписание на эту дату не предусмотрено.",
            show_alert=True,
        )
        return

    try:
        text = format_schedule(group, selected_date)

        await callback.message.edit_text(
            text,
            reply_markup=get_schedule_keyboard(selected_date),
        )

        await callback.answer()

    except ValueError as error:
        await callback.answer(
            str(error),
            show_alert=True,
        )


@dp.message(F.text)
async def handle_text(message: Message):
    """
    Обрабатывает ввод названия группы.
    Если пользователь вводит другую существующую группу,
    его выбор обновляется.
    """
    user_input = message.text.strip()

    group = find_group(user_input)

    if group is None:
        available_groups = "\n".join(
            f"• {name}" for name in get_groups()
        )

        await message.answer(
            "❌ Такая группа не найдена.\n\n"
            "Проверь название и попробуй ещё раз.\n\n"
            "Доступные группы:\n"
            f"{available_groups}"
        )
        return

    user_groups[message.from_user.id] = group

    await message.answer(
        f"✅ Группа успешно выбрана: {group}\n\n"
        "Теперь нажми «Расписание», чтобы посмотреть занятия.\n"
        "Чтобы сменить группу, просто введи её новое название.",
        reply_markup=get_main_keyboard(),
    )


async def main():
    print("Бот запущен. Для остановки нажми Ctrl+C.")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())