import asyncio
import logging
import os
from datetime import date, timedelta
from pathlib import Path

import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from dotenv import load_dotenv

from input_service import (
    extract_teacher_query,
    find_group as match_group,
    find_teachers,
    looks_like_group,
    normalize_text,
    parse_schedule_date,
    teacher_suggestions,
)
from schedule_service import (
    load_schedules,
    load_details,
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


class TeacherSearch(StatesGroup):
    surname = State()


class ScheduleDate(StatesGroup):
    day = State()


# Выбранная группа хранится в памяти.
# При перезапуске бота её потребуется ввести заново.
user_groups: dict[int, str] = {}


def get_groups() -> list[str]:
    """Возвращает список доступных учебных групп."""
    data = load_schedules()
    return list(data.get("groups", {}).keys())


def find_group(user_input: str) -> str | None:
    return match_group(user_input, get_groups())


def get_main_keyboard() -> ReplyKeyboardMarkup:
    """Создаёт основное меню бота."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Расписание"), KeyboardButton(text="На дату")],
            [KeyboardButton(text="Звонки")],
            [KeyboardButton(text="Преподаватель по фамилии")],
        ],
        resize_keyboard=True,
    )


def get_schedule_keyboard(
    selected_date: date,
) -> InlineKeyboardMarkup:
    """Создаёт кнопки переключения дней расписания."""
    buttons = []
    if selected_date > START_DATE:
        previous_day = selected_date - timedelta(days=1)
        buttons.append([InlineKeyboardButton(
            text="◀️ Предыдущий день", callback_data=f"day:{previous_day.isoformat()}",
        )])
    if selected_date < date.max:
        next_day = selected_date + timedelta(days=1)
        buttons.append([InlineKeyboardButton(
            text="Следующий день ▶️", callback_data=f"day:{next_day.isoformat()}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    """Просит пользователя указать учебную группу."""
    await state.clear()
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
        "Например: ПРИ-О-23/1.\n\n"
        "Можно также написать фамилию преподавателя, например: Андреев.\n"
        "Для расписания на другой день отправь дату: 05.11.2026.\n"
        "Список групп: /groups",
        reply_markup=get_main_keyboard(),
    )


async def request_teacher_surname(message: Message, state: FSMContext):
    """Включает поиск преподавателя по следующему сообщению."""
    await state.clear()
    await state.set_state(TeacherSearch.surname)
    await message.answer(
        "Введи фамилию преподавателя.\n"
        "Например: Андреев или Андреева.\n\n"
        "Фамилию можно писать и без нажатия кнопки.\n"
        "Для выхода выбери другую кнопку или отправь /cancel.",
        reply_markup=get_main_keyboard(),
    )


async def find_teacher(message: Message, state: FSMContext, query: str):
    """Ищет преподавателя и уточняет имя при совпадении фамилий."""
    teachers = load_details().get("teachers", {})
    matches = find_teachers(query, teachers)
    context = await state.get_data()
    if not matches and context.get("teacher_candidates"):
        matches = [
            name for name in context["teacher_candidates"]
            if name in teachers.values()
            and find_teachers(f"{name.split()[0]} {query}", {name: name})
        ]
    if len(matches) == 1:
        await state.clear()
        await message.answer(f"👨‍🏫 {matches[0]}", reply_markup=get_main_keyboard())
        return
    await state.set_state(TeacherSearch.surname)
    if matches:
        await state.update_data(teacher_candidates=matches)
        names = "\n".join(f"• {name}" for name in matches)
        await message.answer(
            f"Нашлось несколько преподавателей:\n{names}\n\n"
            "Уточни имя или введи фамилию вместе с именем.",
            reply_markup=get_main_keyboard(),
        )
        return
    suggestions = teacher_suggestions(query, teachers)
    hint = f"Возможно, ты имел в виду: {', '.join(suggestions)}.\n" if suggestions else ""
    await message.answer(
        f"❌ Преподаватель «{query[:100]}» не найден в справочнике.\n\n"
        f"{hint}Проверь фамилию и попробуй ещё раз.\n"
        "Можно также ввести группу или отправить /cancel.",
        reply_markup=get_main_keyboard(),
    )


async def request_schedule_date(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(ScheduleDate.day)
    group = user_groups.get(message.from_user.id)
    example = max(date.today(), START_DATE).strftime("%d.%m.%Y")
    if group:
        text = f"Группа: {group}.\nВведи дату: ДД.ММ.ГГГГ или ДД.ММ."
    else:
        text = "Введи дату расписания. Если группа ещё не выбрана, я попрошу её следующим сообщением."
    await message.answer(
        f"{text}\nНапример: {example}.\n"
        "Без года используется текущий год. Можно также написать «завтра».\n"
        "Для выхода отправь /cancel или выбери другую кнопку.",
        reply_markup=get_main_keyboard(),
    )


async def send_schedule(message: Message, state: FSMContext, selected_date: date | None = None):
    """Отправляет расписание на сегодня или на указанную дату."""
    explicit_date = selected_date is not None
    selected_date = selected_date or date.today()
    await state.clear()
    if selected_date < START_DATE:
        if explicit_date:
            await state.set_state(ScheduleDate.day)
        await message.answer(
            f"Расписание доступно с {START_DATE.strftime('%d.%m.%Y')}.\n"
            "Введи дату не раньше начала расписания.",
            reply_markup=get_main_keyboard(),
        )
        return
    group = user_groups.get(message.from_user.id)

    if not group:
        if explicit_date:
            await state.set_state(ScheduleDate.day)
            await state.update_data(schedule_date=selected_date.isoformat())
            await message.answer(
                f"Чтобы показать расписание на {selected_date.strftime('%d.%m.%Y')}, "
                "введи название своей учебной группы.\nСписок групп: /groups",
                reply_markup=get_main_keyboard(),
            )
            return
        await message.answer(
            "Сначала введи название своей учебной группы."
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


async def send_bell_schedule(message: Message, state: FSMContext):
    """Отправляет расписание звонков."""
    await state.clear()
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
async def change_schedule_day(callback: CallbackQuery, state: FSMContext):
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

        if not isinstance(callback.message, Message):
            await callback.answer("Открой расписание заново.", show_alert=True)
            return
        await state.clear()
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
    except TelegramBadRequest as error:
        if "message is not modified" in error.message.lower():
            await callback.answer()
        elif "message to edit not found" in error.message.lower() or "message can't be edited" in error.message.lower():
            await callback.answer("Открой расписание заново.", show_alert=True)
        else:
            raise


async def send_help(message: Message):
    await message.answer(
        "Выбери кнопку меню или напиши:\n"
        "• фамилию преподавателя: Андреев;\n"
        "• фамилию с командой: препод Андреев;\n"
        "• свою группу: ПРИ-О-23/1.\n\n"
        "На другой день: 05.11.2026, 05.11 или «расписание на 05.11».\n"
        "Можно также написать «завтра» или нажать «На дату».\n\n"
        "Список групп: /groups\n"
        "Выход из поиска: /cancel",
        reply_markup=get_main_keyboard(),
    )


async def select_group(message: Message, state: FSMContext, group: str):
    current_state = await state.get_state()
    context = await state.get_data()
    await state.clear()
    user_groups[message.from_user.id] = group
    if current_state == ScheduleDate.day.state:
        if context.get("schedule_date"):
            await send_schedule(message, state, date.fromisoformat(context["schedule_date"]))
        else:
            await request_schedule_date(message, state)
        return
    await message.answer(
        f"✅ Группа успешно выбрана: {group}\n\n"
        "Нажми «Расписание» для просмотра на сегодня или отправь нужную дату.\n"
        "Чтобы сменить группу, просто введи её новое название.",
        reply_markup=get_main_keyboard(),
    )


@dp.message(F.text)
async def handle_text(message: Message, state: FSMContext):
    """Разбирает команды, группы и фамилии независимо от режима поиска."""
    user_input = message.text.strip()
    command = normalize_text(user_input).strip(" .!?:;")
    if command == "/start":
        await start(message, state)
        return
    if command in {"/help", "помощь", "меню", "/menu", "привет", "здравствуйте"}:
        await state.clear()
        await send_help(message)
        return
    if command in {"/cancel", "отмена", "назад"}:
        await state.clear()
        await message.answer("Ввод завершён. Выбери действие.", reply_markup=get_main_keyboard())
        return
    if command in {"расписание", "расписание сегодня", "расписание на сегодня", "/schedule", "пары"}:
        await send_schedule(message, state)
        return
    if command in {"звонки", "звонок", "расписание звонков", "/bells"}:
        await send_bell_schedule(message, state)
        return
    if command in {"на дату", "расписание на дату", "выбрать дату", "/date"}:
        await request_schedule_date(message, state)
        return
    if command in {"/groups", "группы", "список групп", "выбрать группу", "сменить группу", "группа"}:
        if await state.get_state() != ScheduleDate.day.state:
            await state.clear()
        groups = "\n".join(f"• {group}" for group in get_groups())
        await message.answer(
            f"Доступные группы:\n{groups}\n\nВведи название своей группы.",
            reply_markup=get_main_keyboard(),
        )
        return
    try:
        selected_date = parse_schedule_date(user_input)
    except ValueError as error:
        await state.clear()
        await state.set_state(ScheduleDate.day)
        await message.answer(str(error), reply_markup=get_main_keyboard())
        return
    if selected_date is not None:
        await send_schedule(message, state, selected_date)
        return
    teacher_query = extract_teacher_query(user_input)
    if teacher_query is not None:
        await state.clear()
        if teacher_query:
            await find_teacher(message, state, teacher_query)
        else:
            await request_teacher_surname(message, state)
        return
    if command.startswith("/"):
        await message.answer("Неизвестная команда. Справка: /help", reply_markup=get_main_keyboard())
        return

    group_query = re.sub(r"^(?:моя\s+)?группа(?:\s*[:\-]\s*|\s+)", "", normalize_text(user_input))
    group = find_group(group_query)
    if group:
        await select_group(message, state, group)
        return
    if looks_like_group(group_query):
        if await state.get_state() != ScheduleDate.day.state:
            await state.clear()
        await message.answer(
            "❌ Такая группа не найдена. Проверь название.\n"
            "Например: ПРИ-О-23/1. Список доступных групп: /groups",
            reply_markup=get_main_keyboard(),
        )
        return

    teachers = load_details().get("teachers", {})
    current_state = await state.get_state()
    if (current_state == TeacherSearch.surname.state
            or find_teachers(user_input, teachers)
            or (current_state != ScheduleDate.day.state and re.fullmatch(r"[А-Яа-яЁё-]{2,}", user_input))):
        await find_teacher(message, state, user_input)
        return
    if current_state == ScheduleDate.day.state:
        await message.answer("Введи дату в формате ДД.ММ.ГГГГ или ДД.ММ, например 05.11.2026.")
        return
    await send_help(message)


@dp.message()
async def handle_non_text(message: Message, state: FSMContext):
    if await state.get_state() == TeacherSearch.surname.state:
        await message.answer("Введи фамилию преподавателя текстом.")
    elif await state.get_state() == ScheduleDate.day.state:
        await message.answer("Введи дату текстом, например 05.11.2026.")
    else:
        await send_help(message)


async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.info("Бот запущен.")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
