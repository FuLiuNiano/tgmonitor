import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from core import match_keywords, message_link, schedule_is_due
from tg_guardian import proxy_from_env


class CoreTests(unittest.TestCase):
    def test_keyword_match_is_case_insensitive_and_deduplicated_by_config(self):
        self.assertEqual(match_keywords("New BONUS and bonus", ["bonus", "通知"]), ["bonus"])

    def test_schedule_window(self):
        tz = timezone(timedelta(hours=8), name="Asia/Shanghai")
        self.assertTrue(schedule_is_due(datetime(2026, 1, 1, 9, 20, tzinfo=tz), "09:00", 30))
        self.assertFalse(schedule_is_due(datetime(2026, 1, 1, 9, 31, tzinfo=tz), "09:00", 30))
        self.assertFalse(schedule_is_due(datetime(2026, 1, 1, 8, 59, tzinfo=tz), "09:00", 30))

    def test_message_link(self):
        class Entity:
            username = "demo_channel"
            id = 123

        self.assertEqual(message_link(Entity(), 7), "https://t.me/demo_channel/7")

    def test_proxy_config(self):
        with patch.dict("os.environ", {"TG_PROXY": "socks5://user:pass@127.0.0.1:7890"}, clear=False):
            self.assertEqual(proxy_from_env(), {
                "proxy_type": "socks5",
                "addr": "127.0.0.1",
                "port": 7890,
                "rdns": True,
                "username": "user",
                "password": "pass",
            })


if __name__ == "__main__":
    unittest.main()
