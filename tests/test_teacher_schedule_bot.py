from datetime import date
import os
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

with patch.dict(os.environ, {"BOT_TOKEN": "123456789:local-test-token"}), patch("dotenv.load_dotenv"):
    import bot

from test_teacher_schedule import OTHER_TEACHER, TEACHER, lesson


class FixedDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 11, 9)


class TeacherScheduleBotTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.message = SimpleNamespace(
            text="", from_user=SimpleNamespace(id=987654321), answer=AsyncMock(),
        )
        self.storage = MemoryStorage()
        self.state = FSMContext(
            storage=self.storage,
            key=StorageKey(bot_id=123456789, chat_id=987654321, user_id=987654321),
        )
        self.details = {"teachers": {"К.А.Егоров": TEACHER, "Е.Н.Егоров": OTHER_TEACHER}, "rooms": {}}
        self.lessons = [lesson(), lesson(3, teacher="Е.Н.Егоров", subject="Чужая пара")]
        self.data = {"groups": {"А-1": {"weeks": {"week_1": {"ПОНЕДЕЛЬНИК": self.lessons}}}}}
        self.addCleanup(patch.stopall)
        patch("schedule_service.date", FixedDate).start()
        patch("schedule_service.load_schedules", return_value=self.data).start()
        patch("schedule_service.load_details", return_value=self.details).start()
        patch("bot.load_schedules", return_value=self.data).start()
        patch("bot.load_details", return_value=self.details).start()
        bot.user_groups.pop(self.message.from_user.id, None)

    async def asyncTearDown(self):
        bot.user_groups.pop(self.message.from_user.id, None)
        await self.storage.close()
        await bot.bot.session.close()

    async def send(self, text):
        self.message.text = text
        self.message.answer.reset_mock()
        await bot.handle_text(self.message, self.state)
        return "\n".join(call.args[0] for call in self.message.answer.await_args_list)

    async def test_command_shows_full_week_without_selected_group(self):
        text = await self.send("Где Егоров К. А.")
        self.assertIn(TEACHER, text)
        self.assertIn("09.11.2026–15.11.2026", text)
        self.assertIn("09:30–10:50", text)
        self.assertIn("Группы: А-1", text)
        self.assertNotIn("Чужая пара", text)
        self.assertIsNone(await self.state.get_state())

    async def test_ambiguous_surname_then_first_name_keeps_weekly_mode(self):
        text = await self.send("Где Егоров")
        self.assertIn("несколько преподавателей", text)
        self.assertTrue((await self.state.get_data())["teacher_schedule"])
        text = await self.send("Кирилл")
        self.assertIn("Расписание на неделю", text)
        self.assertIn(TEACHER, text)
        self.assertNotIn(OTHER_TEACHER, text)
        self.assertEqual(await self.state.get_data(), {})

    async def test_bare_command_then_surname(self):
        self.assertIn("Введи фамилию", await self.send("Где?"))
        self.assertIn("Расписание на неделю", await self.send("Егоров К. А."))

    async def test_retry_after_not_found_keeps_weekly_mode(self):
        self.assertIn("не найден", await self.send("Где Неизвестный"))
        self.assertIn("Расписание на неделю", await self.send("Егоров К. А."))

    async def test_cancel_and_explicit_teacher_search_exit_weekly_mode(self):
        await self.send("Где")
        await self.send("/cancel")
        self.assertEqual(await self.send("Егоров К. А."), f"👨‍🏫 {TEACHER}")
        await self.send("Где")
        self.assertEqual(await self.send("препод Егоров К. А."), f"👨‍🏫 {TEACHER}")

    async def test_weekly_command_overrides_date_mode_and_preserves_group(self):
        bot.user_groups[self.message.from_user.id] = "А-1"
        await self.send("На дату")
        self.assertIn("Расписание на неделю", await self.send("Где Егоров К. А."))
        self.assertEqual(bot.user_groups[self.message.from_user.id], "А-1")
        self.assertIsNone(await self.state.get_state())

    async def test_group_selection_exits_weekly_search(self):
        await self.send("Где Егоров")
        self.assertIn("Группа успешно выбрана", await self.send("А-1"))
        self.assertEqual(await self.state.get_data(), {})
        self.assertEqual(await self.send("Егоров К. А."), f"👨‍🏫 {TEACHER}")

    async def test_long_schedule_is_sent_in_several_messages(self):
        self.lessons[:] = [lesson(subject=f"Предмет {number:03d} " + "а" * 80) for number in range(80)]
        text = await self.send("Где Егоров К. А.")
        self.assertGreater(self.message.answer.await_count, 1)
        self.assertIn("Предмет 079", text)
        for call in self.message.answer.await_args_list:
            self.assertLessEqual(len(call.args[0].encode("utf-16-le")) // 2, 4096)


if __name__ == "__main__":
    unittest.main()
