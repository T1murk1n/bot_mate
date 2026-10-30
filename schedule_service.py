
import json
from datetime import date, timedelta
from pathlib import Path
import re

BASE_DIR = Path(__file__).parent

SCHEDULE_FILE = BASE_DIR / "schedules_all.json"
DETAILS_FILE = BASE_DIR / "schedule_details.json"

# Понедельник первой учебной недели
START_DATE = date(2026, 10, 26)

DAY_NAMES = [
    "ПОНЕДЕЛЬНИК",
    "ВТОРНИК",
    "СРЕДА",
    "ЧЕТВЕРГ",
    "ПЯТНИЦА",
    "СУББОТА",
    "ВОСКРЕСЕНЬЕ",
]

DAY_NAMES_SHORT = [
    "пн", "вт", "ср", "чт", "пт", "сб", "вс"
]

# Время начала и окончания каждой пары
LESSON_TIMES = {
    1: ("08:00", "09:20"),
    2: ("09:30", "10:50"),
    3: ("11:00", "12:20"),
    4: ("12:45", "14:05"),
    5: ("14:15", "15:35"),
    6: ("15:45", "17:05"),
    7: ("17:15", "18:35"),
    8: ("18:40", "20:00"),
}


def load_schedules() -> dict:
    """Загружает основное расписание."""
    with SCHEDULE_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def load_details() -> dict:
    """Загружает справочники преподавателей и аудиторий."""
    if not DETAILS_FILE.exists():
        return {"teachers": {}, "rooms": {}}

    with DETAILS_FILE.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_current_week(today: date | None = None) -> int:
    """Определяет номер чередующейся учебной недели."""
    today = today or date.today()
    days_passed = (today - START_DATE).days

    if days_passed < 0:
        raise ValueError(
            "Дата раньше начала учебного расписания."
        )

    weeks_passed = days_passed // 7
    return weeks_passed % 2 + 1


def get_schedule(
    group: str,
    today: date | None = None,
) -> tuple[int, str, list[dict]]:
    """Возвращает номер недели, день и занятия."""
    today = today or date.today()
    data = load_schedules()

    groups = data.get("groups", {})

    if group not in groups:
        raise ValueError(f"Группа {group} не найдена.")

    week_number = get_current_week(today)
    day_name = DAY_NAMES[today.weekday()]

    group_data = groups[group]
    week_key = f"week_{week_number}"

    lessons = (
        group_data
        .get("weeks", {})
        .get(week_key, {})
        .get(day_name, [])
    )

    return week_number, day_name, lessons





def get_teacher_name(teacher: str, teachers: dict) -> str:
    """Находит фамилию в записи с инициалами и подставляет ФИО."""
    if not teacher:
        return ""

    # Извлекаем последнее слово, состоящее из букв и дефиса.
    # Примеры:
    # А.С.Шабалин -> Шабалин
    # А. С. Шабалин -> Шабалин
    # Шабалин -> Шабалин
    match = re.search(
        r"([А-ЯЁ][а-яё-]*)\s*$",
        teacher.strip(),
        flags=re.IGNORECASE,
    )

    if not match:
        return teacher

    surname = match.group(1)

    # Сопоставляем ключи справочника без учёта регистра.
    for key, full_name in teachers.items():
        if key.strip().casefold() == surname.casefold():
            return full_name

    # Если соответствие не найдено, сохраняем исходное значение.
    return teacher



def get_room_address(room: str, rooms: dict) -> str:
    """Возвращает адрес корпуса для аудитории."""
    if not room:
        return ""

    address = rooms.get(str(room).strip())
    if address:
        return f"{room} ({address})"

    # Если аудитория отсутствует в справочнике,
    # показываем исходный номер без выдуманного адреса.
    return str(room)


def get_lesson_type(lesson_type: str) -> str:
    """Преобразует короткое обозначение типа занятия."""
    normalized = (lesson_type or "").strip().lower()

    if "лек" in normalized:
        return "Лекция"

    if "лаб" in normalized:
        return "Лабораторное занятие"

    if "практ" in normalized:
        return "Практическое занятие"

    return lesson_type.strip() if lesson_type else ""


def get_date_title(selected_date: date) -> str:
    """Формирует заголовок даты, как в примере."""
    today = date.today()

    if selected_date == today:
        day_label = "сегодня"
    elif selected_date == today + timedelta(days=1):
        day_label = "завтра"
    elif selected_date == today - timedelta(days=1):
        day_label = "вчера"
    else:
        day_label = selected_date.strftime("%d.%m")

    weekday = DAY_NAMES_SHORT[selected_date.weekday()]
    return (
        f"на {day_label} "
        f"({weekday}, {selected_date.strftime('%d.%m')})"
    )


def format_schedule(
    group: str,
    today: date | None = None,
) -> str:
    """Формирует расписание для Telegram."""
    selected_date = today or date.today()

    week_number, day_name, lessons = get_schedule(
        group,
        selected_date,
    )

    details = load_details()
    teachers = details.get("teachers", {})
    rooms = details.get("rooms", {})

    title = get_date_title(selected_date)

    lines = [
        f"📄 Расписание для {group} {title}",
        "",
    ]

    if not lessons:
        lines.append("🎉 На этот день занятий нет!")
        return "\n".join(lines)

    sorted_lessons = sorted(
        lessons,
        key=lambda item: item["lesson_number"],
    )

    # Оставляем только реально заполненные пары.
    # Пары до первого занятия и после последнего
    # вообще не рассматриваем.
    lessons_by_number = {
        int(lesson["lesson_number"]): lesson
        for lesson in sorted_lessons
    }

    first_lesson = min(lessons_by_number)
    last_lesson = max(lessons_by_number)

    for number in range(first_lesson, last_lesson + 1):
        if number in lessons_by_number:
            lesson = lessons_by_number[number]

            subject = lesson.get("subject", "Без названия")
            teacher = get_teacher_name(
                lesson.get("teacher", ""),
                teachers,
            )
            room = get_room_address(
                lesson.get("room", ""),
                rooms,
            )
            lesson_type = get_lesson_type(
                lesson.get("type", "")
            )

            start_time, end_time = LESSON_TIMES[number]

            lines.append(f"{number}️⃣ {subject}")

            if teacher:
                lines.append(f"👨‍🏫 {teacher}")

            # Аудитория, адрес корпуса и тип занятия.
            place_details = []

            if room:
                place_details.append(room)

            if lesson_type:
                place_details.append(
                    f"({lesson_type})"
                )

            if place_details:
                lines.append(f"🏫 {' '.join(place_details)}")

            lines.append(
                f"🕒 {start_time}-{end_time}"
            )

        else:
            # Окно показываем только между первой
            # и последней фактическими парами.
            lines.append(f"{number}️⃣ (окно)")

        # Отступ между парами, как на скриншоте.
        if number < last_lesson:
            lines.append("")

    return "\n".join(lines)
