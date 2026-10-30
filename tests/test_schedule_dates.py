from datetime import date
import unittest

from input_service import parse_schedule_date


class ScheduleDateTests(unittest.TestCase):
    today = date(2026, 10, 30)

    def test_numeric_date_formats(self):
        for value in ["05.11.2026", "5.11.2026", "05.11.26", "05.11", "05.11.", "5/11/2026", "5-11-2026", "2026-11-05", "  05.11.2026.  "]:
            with self.subTest(value=value):
                self.assertEqual(parse_schedule_date(value, self.today), date(2026, 11, 5))

    def test_schedule_command_prefixes(self):
        for value in ["расписание на 05.11", "РАСПИСАНИЕ 05.11.2026", "на 05.11", "на дату 05.11", "дата:05.11", "/date 05.11", "/schedule 05.11", "пары на 05.11"]:
            with self.subTest(value=value):
                self.assertEqual(parse_schedule_date(value, self.today), date(2026, 11, 5))

    def test_missing_year_uses_current_year(self):
        self.assertEqual(parse_schedule_date("01.01", self.today), date(2026, 1, 1))
        self.assertEqual(parse_schedule_date("05.11", date(2027, 1, 1)), date(2027, 11, 5))

    def test_relative_dates(self):
        for value, expected in [
            ("сегодня", date(2026, 10, 30)), ("завтра", date(2026, 10, 31)),
            ("послезавтра", date(2026, 11, 1)), ("вчера", date(2026, 10, 29)),
            ("расписание на завтра", date(2026, 10, 31)),
        ]:
            with self.subTest(value=value):
                self.assertEqual(parse_schedule_date(value, self.today), expected)
        self.assertEqual(parse_schedule_date("завтра", date(2026, 12, 31)), date(2027, 1, 1))

    def test_leap_year(self):
        self.assertEqual(parse_schedule_date("29.02.2028", self.today), date(2028, 2, 29))
        with self.assertRaises(ValueError):
            parse_schedule_date("29.02.2026", self.today)

    def test_invalid_dates_get_a_date_error(self):
        for value in ["31.02.2026", "32.10.2026", "05.13", "00.11", "2026-02-30", "05.11.2", "2026-11", "расписание на пятницу"]:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_schedule_date(value, self.today)

    def test_group_teacher_and_menu_input_remains_unclaimed(self):
        for value in ["ПРИ-О-23/1", "группа:ПМ-О-26/1", "при – O – 23 / 1", "Андреев", "препод Андреев", "На дату", "Звонки", "/groups", "", "привет"]:
            with self.subTest(value=value):
                self.assertIsNone(parse_schedule_date(value, self.today))

    def test_boundary_dates(self):
        self.assertEqual(parse_schedule_date("9999-12-31", self.today), date.max)
        self.assertEqual(parse_schedule_date("0001-01-01", self.today), date.min)
        with self.assertRaises(ValueError):
            parse_schedule_date("завтра", date.max)


if __name__ == "__main__":
    unittest.main()
