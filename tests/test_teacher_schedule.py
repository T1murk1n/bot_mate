from datetime import date, timedelta
import unittest
from unittest.mock import patch

from input_service import find_teachers
from schedule_service import (
    DAY_NAMES,
    START_DATE,
    format_teacher_schedule,
    get_schedule_teachers,
    get_teacher_schedule,
    split_schedule_text,
)


TEACHER = "Егоров Кирилл Александрович"
OTHER_TEACHER = "Егоров Егор Николаевич"


def lesson(number=2, teacher="К.А.Егоров", room="101", subject="Математика"):
    return {
        "lesson_number": number, "teacher": teacher, "room": room,
        "subject": subject, "type": "лек",
    }


class TeacherScheduleTests(unittest.TestCase):
    def setUp(self):
        self.details = {
            "teachers": {"К.А.Егоров": TEACHER, "Е.Н.Егоров": OTHER_TEACHER},
            "rooms": {"101": "Первый корпус"},
        }
        self.data = {"groups": {
            "А-1": {"weeks": {
                "week_1": {"ПОНЕДЕЛЬНИК": [
                    lesson(4, room=""), lesson(),
                    lesson(3, teacher="Е.Н.Егоров", subject="Чужая пара"),
                ]},
                "week_2": {"ВТОРНИК": [lesson(5, subject="Вторая неделя")]},
            }},
            "Б-1": {"weeks": {"week_1": {"ПОНЕДЕЛЬНИК": [
                lesson(teacher=TEACHER),
                lesson(room="102", subject="Другая аудитория"),
                lesson(6, teacher="И.Р.Васильева"),
            ]}}},
            "В-1": {"weeks": {}},
        }}
        self.addCleanup(patch.stopall)
        patch("schedule_service.load_schedules", return_value=self.data).start()
        patch("schedule_service.load_details", return_value=self.details).start()

    def test_all_groups_sorted_and_shared_classes_merged(self):
        week, monday, schedule = get_teacher_schedule(TEACHER, date(2026, 10, 30))
        self.assertEqual((week, monday), (1, START_DATE))
        self.assertEqual(list(schedule), DAY_NAMES)
        lessons = schedule["ПОНЕДЕЛЬНИК"]
        self.assertEqual([item["lesson_number"] for item in lessons], [2, 2, 4])
        shared = next(item for item in lessons if item["subject"] == "Математика" and item["room"] == "101")
        self.assertEqual(shared["groups"], ["А-1", "Б-1"])
        self.assertFalse(schedule["ВОСКРЕСЕНЬЕ"])
        self.assertNotIn("groups", self.data["groups"]["А-1"]["weeks"]["week_1"]["ПОНЕДЕЛЬНИК"][0])

    def test_week_parity_and_full_week_on_sunday(self):
        week, monday, schedule = get_teacher_schedule(TEACHER, date(2026, 11, 8))
        self.assertEqual((week, monday), (2, date(2026, 11, 2)))
        self.assertFalse(schedule["ПОНЕДЕЛЬНИК"])
        self.assertEqual(schedule["ВТОРНИК"][0]["subject"], "Вторая неделя")

    def test_same_surname_does_not_mix_initials(self):
        _, _, schedule = get_teacher_schedule(OTHER_TEACHER, START_DATE)
        self.assertEqual(len(schedule["ПОНЕДЕЛЬНИК"]), 1)
        self.assertEqual(schedule["ПОНЕДЕЛЬНИК"][0]["subject"], "Чужая пара")
        self.assertEqual(len(find_teachers("Егоров", get_schedule_teachers())), 2)

    def test_teacher_missing_from_directory_is_searchable_by_surname(self):
        teachers = get_schedule_teachers()
        self.assertEqual(find_teachers("Васильева", teachers), ["Васильева И. Р."])
        _, _, schedule = get_teacher_schedule("Васильева И. Р.", START_DATE)
        self.assertEqual(schedule["ПОНЕДЕЛЬНИК"][0]["lesson_number"], 6)

    def test_conflicting_initials_do_not_expand_to_wrong_full_name(self):
        self.details["teachers"]["Васильева"] = "Васильева Анна Петровна"
        teachers = get_schedule_teachers()
        self.assertEqual(teachers["И.Р.Васильева"], "Васильева И. Р.")
        _, _, schedule = get_teacher_schedule("Васильева Анна Петровна", START_DATE)
        self.assertFalse(any(schedule.values()))

    def test_formatted_week_includes_dates_times_rooms_groups_and_free_days(self):
        text = format_teacher_schedule(TEACHER, date(2026, 10, 30))
        for expected in [
            TEACHER, "26.10.2026–01.11.2026", "Учебная неделя: 1",
            "ПОНЕДЕЛЬНИК, 26.10", "ВОСКРЕСЕНЬЕ, 01.11",
            "2 пара · 09:30–10:50", "4 пара · 12:45–14:05",
            "Математика (Лекция)", "Аудитория: 101 (Первый корпус)",
            "Аудитория: не указана", "Группы: А-1, Б-1", "Занятий в расписании нет.",
        ]:
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
        self.assertNotIn("Чужая пара", text)
        self.assertNotIn("Вторая неделя", text)
        self.assertEqual(text.count("2 пара"), 2)

    def test_no_lessons_and_date_before_start(self):
        text = format_teacher_schedule("Несуществующий преподаватель", START_DATE)
        self.assertIn("На эту неделю занятий в расписании нет.", text)
        with self.assertRaises(ValueError):
            get_teacher_schedule(TEACHER, START_DATE - timedelta(days=1))

    def test_large_schedule_is_split_without_losing_lessons(self):
        lessons = self.data["groups"]["А-1"]["weeks"]["week_1"]["ПОНЕДЕЛЬНИК"]
        lessons[:] = [lesson(subject=f"Предмет {number:03d} " + "а" * 80) for number in range(80)]
        text = format_teacher_schedule(TEACHER, START_DATE)
        chunks = split_schedule_text(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk.encode("utf-16-le")) // 2 <= 4096 for chunk in chunks))
        self.assertEqual("".join(text.split()), "".join("".join(chunks).split()))
        for number in range(80):
            self.assertIn(f"Предмет {number:03d}", "\n".join(chunks))


class RealTeacherScheduleTests(unittest.TestCase):
    def test_all_known_teachers_both_weeks_format_for_telegram(self):
        teachers = get_schedule_teachers()
        for teacher in set(teachers.values()):
            for offset in (0, 7):
                with self.subTest(teacher=teacher, offset=offset):
                    text = format_teacher_schedule(teacher, START_DATE + timedelta(days=offset))
                    chunks = split_schedule_text(text)
                    self.assertTrue(chunks)
                    self.assertIn(teacher, chunks[0])
                    self.assertTrue(all(len(chunk.encode("utf-16-le")) // 2 <= 4096 for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
