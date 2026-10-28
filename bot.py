import asyncio
import os
from datetime import date, timedelta
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

# Пока сохраняем выбор группы в памяти.
# При перезапуске бота пользователь выберет группу снова.
user_groups: dict[int, str] = {}


def get_groups() -> list[str]:
    """Возвращает список доступных учебных групп."""
    data = load_schedules()
    return list(data.get("groups", {}).keys())


def get_group_keyboard() -> InlineKeyboardMarkup:
    """Создаёт клавиатуру выбора учебной группы."""
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
    """Создаёт основное меню бота."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Расписание")],
            [KeyboardButton(text="Сменить группу")],
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
                    text="◀ Предыдущий день",
                    callback_data=f"day:{previous_day.isoformat()}",
                ),
                InlineKeyboardButton(
                    text="Следующий день ▶",
                    callback_data=f"day:{next_day.isoformat()}",
                ),
            ]
        ]
    )


@dp.message(CommandStart())
async def start(message: Message):
    """Обрабатывает команду /start."""
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
    """Сохраняет выбранную учебную группу."""
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
    """Отправляет расписание на текущий день."""
    group = user_groups.get(message.from_user.id)

    if not group:
        await message.answer(
            "Сначала выбери учебную группу:",
            reply_markup=get_group_keyboard(),
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


@dp.callback_query(F.data.startswith("day:"))
async def change_schedule_day(callback: CallbackQuery):
    """Переключает расписание на выбранную дату."""
    group = user_groups.get(callback.from_user.id)

    if not group:
        await callback.answer(
            "Сначала выбери учебную группу.",
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


@dp.message(F.text == "Сменить группу")
async def change_group(message: Message):
    """Предлагает выбрать другую учебную группу."""
    await message.answer(
        "Выбери новую учебную группу:",
        reply_markup=get_group_keyboard(),
    )


async def main():
    print("Бот запущен. Для остановки нажми Ctrl+C.")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())