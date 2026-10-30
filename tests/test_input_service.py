import unittest

from input_service import (
    extract_teacher_query,
    find_group,
    find_teachers,
    normalize_text,
    teacher_suggestions,
)
from schedule_service import get_teacher_name, load_details, load_schedules


class InputMatchingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.teachers = load_details()["teachers"]
        cls.groups = list(load_schedules()["groups"])

    def test_all_full_names_and_directory_keys_are_searchable(self):
        for key, full_name in self.teachers.items():
            for query in [key, full_name, key.lower(), f"  {key.upper()}  "]:
                with self.subTest(query=query):
                    self.assertIn(full_name, find_teachers(query, self.teachers))

    def test_common_surname_case_forms(self):
        examples = {
            "Андреева": "Андреев Александр Сергеевич",
            "Андрееву": "Андреев Александр Сергеевич",
            "Андреевым": "Андреев Александр Сергеевич",
            "Андрееве": "Андреев Александр Сергеевич",
            "Шабалиным": "Шабалин Александр Станиславович",
            "Блюменштейном": "Блюменштейн Алексей Александрович",
            "Агаджановой": "Агаджанова Эмилия Рафаэловна",
            "Агаджанову": "Агаджанова Эмилия Рафаэловна",
            "Смолехи": "Смолеха Виталий Петрович",
            "Шевченко": "Шевченко Татьяна Валентиновна",
            "Чекал": "Чекал Елена Георгиевна",
        }
        for query, expected in examples.items():
            with self.subTest(query=query):
                self.assertEqual(find_teachers(query, self.teachers), [expected])

    def test_yo_punctuation_and_initials(self):
        for query in ["Хрусталёв", "ХРУСТАЛЕВ!", "Хрусталёва"]:
            with self.subTest(query=query):
                self.assertEqual(find_teachers(query, self.teachers), ["Хрусталев Сергей Александрович"])
        self.assertEqual(find_teachers("А.С.Шабалин", self.teachers), ["Шабалин Александр Станиславович"])
        self.assertEqual(find_teachers("Шабалин А. С.", self.teachers), ["Шабалин Александр Станиславович"])

    def test_same_surname_requires_clarification(self):
        self.assertEqual(len(find_teachers("Егоров", self.teachers)), 2)
        self.assertEqual(find_teachers("Егоров Кирилл", self.teachers), ["Егоров Кирилл Александрович"])
        self.assertEqual(find_teachers("Е.Н.Егоров", self.teachers), ["Егоров Егор Николаевич"])

    def test_case_form_does_not_pick_the_wrong_person(self):
        self.assertEqual(len(find_teachers("Богданова", self.teachers)), 2)
        self.assertEqual(find_teachers("Богданова Алевтина", self.teachers), ["Богданова Алевтина Владиславовна"])
        self.assertEqual(find_teachers("Богданова Андрей", self.teachers), ["Богданов Андрей Юрьевич"])

    def test_typo_is_only_a_suggestion(self):
        self.assertEqual(find_teachers("Андрев", self.teachers), [])
        self.assertIn("Андреев", teacher_suggestions("Андрев", self.teachers))
        for query in ["", "неизвестнаяфамилия", "ПРИ-О-23/1", "Андреев1", "привет как твои дела"]:
            with self.subTest(query=query):
                self.assertEqual(find_teachers(query, self.teachers), [])

    def test_command_word_forms(self):
        for prefix in ["препод", "препода", "преподу", "преподом", "преподаватель", "преподавателя", "преподавателю", "преподавателем", "/teacher", "ФИО", "фамилия"]:
            with self.subTest(prefix=prefix):
                self.assertEqual(extract_teacher_query(f"  {prefix}   Андреева "), "андреева")
        self.assertEqual(extract_teacher_query("препод:Андреев"), "андреев")
        self.assertEqual(extract_teacher_query("Преподаватель по фамилии"), "")
        self.assertEqual(extract_teacher_query("препод"), "")
        self.assertIsNone(extract_teacher_query("Андреев"))
        self.assertIsNone(extract_teacher_query("Преподобный"))

    def test_group_normalization(self):
        for group in self.groups:
            with self.subTest(group=group):
                self.assertEqual(find_group(group.lower().replace("-", " — "), self.groups), group)
        for query in ["при – O – 23 / 1", "ПРИ О 23 1", "прио231"]:
            with self.subTest(query=query):
                self.assertEqual(find_group(query, self.groups), "ПРИ-О-23/1")
        self.assertIsNone(find_group("Андреев", self.groups))
        self.assertIsNone(find_group("ПРИ-О-99/1", self.groups))

    def test_ambiguous_group_is_not_chosen(self):
        self.assertIsNone(find_group("аб12", ["АБ-1/2", "АБ-12"]))

    def test_schedule_expansion_respects_initials(self):
        self.assertEqual(get_teacher_name("К.А.Егоров", self.teachers), "Егоров Кирилл Александрович")
        self.assertEqual(get_teacher_name("Е.Н.Егоров", self.teachers), "Егоров Егор Николаевич")
        self.assertEqual(get_teacher_name("Егоров", self.teachers), "Егоров")
        self.assertEqual(get_teacher_name("Д.А.Богданова", self.teachers), "Д.А.Богданова")
        self.assertEqual(get_teacher_name("Неизвестный", self.teachers), "Неизвестный")

    def test_text_normalization(self):
        self.assertEqual(normalize_text("  ПрЕПоД\n Хрусталёв  "), "препод хрусталев")


if __name__ == "__main__":
    unittest.main()
