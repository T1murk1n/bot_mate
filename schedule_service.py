
import json
from datetime import date
from pathlib import Path


SCHEDULE_FILE = Path(__file__).parent / "schedules.json"

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


def load_schedules() -> dict:
    """Загружает расписание из JSON."""
    with SCHEDULE_FILE.open("r", encoding="utf-8") as file:
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
    """Возвращает номер недели, день и список занятий."""
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


def format_schedule(
    group: str,
    today: date | None = None,
) -> str:
    """Формирует компактное и читаемое расписание для Telegram."""
    week_number, day_name, lessons = get_schedule(
        group, today
    )

    selected_date = today or date.today()

    lines = [
        f"📅 {day_name}, {selected_date.strftime('%d.%m.%Y')}",
        f"👥 {group} · Учебная неделя {week_number}",
        "",
    ]

    if not lessons:
        lines.append("🎉 На этот день занятий нет!")
        return "\n".join(lines)

    sorted_lessons = sorted(
        lessons,
        key=lambda item: item["lesson_number"],
    )

    for index, lesson in enumerate(sorted_lessons):
        number = lesson["lesson_number"]
        subject = lesson["subject"]
        lesson_type = lesson.get("type")
        room = lesson.get("room")
        teacher = lesson.get("teacher")

        # Название предмета
        lines.append(f"{number}️⃣ {subject}")

        # Тип занятия и аудитория
        details = []

        if lesson_type:
            type_emoji = (
                "📖" if "лек" in lesson_type.lower()
                else "🧪" if "лаб" in lesson_type.lower()
                else "📝"
            )
            details.append(f"{type_emoji} {lesson_type}")


        if room:
            details.append(f"🚪 Ауд. {room}")

        if details:
            lines.append(" · ".join(details))

        # Преподаватель
        if teacher:
            lines.append(f"👤 {teacher}")

        # Разделитель между парами
        if index < len(sorted_lessons) - 1:
            lines.append("")

    return "\n".join(lines)