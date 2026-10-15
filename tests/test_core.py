import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone

from core import match_keyword_rules, match_keywords, message_link, schedule_is_due
from tg_guardian import proxy_from_env


class CoreTests(unittest.TestCase):
    def test_keyword_rule_requires_all_terms_in_same_message(self):
        self.assertEqual(match_keyword_rules('优惠活动开始了', ['优惠 补货']), [])
        self.assertEqual(match_keyword_rules('今天补货了', ['优惠 补货']), [])
        self.assertEqual(match_keyword_rules('补货了，今天还有优惠', ['优惠 补货']), ['优惠 补货'])

    def test_keyword_rule_lines_are_independent_alternatives(self):
        rules = ['优惠 补货', '限时 折扣', '通知']
        self.assertEqual(match_keyword_rules('限时活动提供折扣', rules), ['限时 折扣'])
        self.assertEqual(match_keyword_rules('优惠活动有折扣', rules), [])
        self.assertEqual(match_keyword_rules('一条通知', rules), ['通知'])

    def test_keyword_rule_whitespace_case_and_duplicate_groups(self):
        rules = ['  VPS\tSALE  ', 'sale VPS', '\u3000', '补货\u3000优惠', '']
        self.assertEqual(match_keyword_rules('sale available for vps，优惠补货', rules), ['VPS SALE', '补货 优惠'])
        self.assertEqual(match_keyword_rules('', rules), [])

    def test_keyword_rules_multiline_input_and_separate_messages(self):
        self.assertEqual(match_keyword_rules('B and A', ['A B\nC D']), ['A B'])
        self.assertEqual(match_keyword_rules('A', ['A B']), [])
        self.assertEqual(match_keyword_rules('B', ['A B']), [])
        self.assertEqual(match_keyword_rules('A B C D', ['A B', 'C D']), ['A B', 'C D'])

    def test_legacy_phrase_matching_for_checkin_is_unchanged(self):
        self.assertEqual(match_keywords('B and A', ['A B']), [])

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
