"""Synthetic card completion scope; no personal chat or provider requests."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'engine').is_dir():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / 'engine'))
import content
import replycheck


class CardCompletionScope(unittest.TestCase):
    def cards(self, first='red_packet', current='red_packet', confirmation='我领了红包'):
        return [
            {'from': 'her', 'kind': first, 'text': '旧卡片'},
            {'from': 'me', 'kind': 'text', 'text': confirmation},
            {'from': 'her', 'kind': current, 'text': '新卡片'},
        ]

    def test_prior_card_completion_does_not_prove_current_card(self):
        for first, current, confirmation in (
            ('red_packet', 'red_packet', '我领了红包'),
            ('transfer', 'transfer', '钱收到了'),
            ('red_packet', 'transfer', '我收了，谢啦'),
            ('transfer', 'red_packet', '我领到了'),
            ('official_account', 'official_account', '我看完这篇了'),
            ('app_card', 'mini_program', '我打开这个了'),
        ):
            with self.subTest(first=first, current=current, confirmation=confirmation):
                self.assertFalse(replycheck.grounded(confirmation, self.cards(first, current, confirmation)))

    def test_confirmation_before_only_visible_card_is_not_current_completion(self):
        for kind, text in (('red_packet', '我领了红包'), ('transfer', '钱收到了'), ('official_account', '我看完这篇了')):
            with self.subTest(kind=kind):
                rows = [{'from': 'me', 'text': text}, {'from': 'her', 'kind': kind, 'text': '当前卡片'}]
                self.assertFalse(replycheck.grounded(text, rows))

    def test_identical_visible_amounts_do_not_link_two_payments(self):
        rows = [{'from': 'her', 'kind': 'transfer', 'text': '￥88\n微信转账'},
                {'from': 'me', 'text': '钱收到了'},
                {'from': 'her', 'kind': 'transfer', 'text': '￥88\n微信转账'}]
        self.assertFalse(replycheck.grounded('钱收到了', rows))

    def test_current_reliable_self_confirmation_remains_available(self):
        for kind, text in (('red_packet', '我领了红包'), ('transfer', '钱收到了'), ('official_account', '我看完这篇了')):
            with self.subTest(kind=kind):
                rows = self.cards(kind, kind, text) + [{'from': 'me', 'text': text}]
                self.assertTrue(replycheck.grounded(text, rows))

    def test_other_card_family_does_not_erase_current_confirmation(self):
        rows = [{'from': 'her', 'kind': 'transfer', 'text': '当前转账'},
                {'from': 'me', 'text': '钱收到了'},
                {'from': 'her', 'kind': 'official_account', 'text': '一篇文章'}]
        self.assertTrue(replycheck.grounded('钱收到了', rows))

    def test_quoted_uncertain_and_conditional_words_are_not_completion_evidence(self):
        for row in (
            {'from': 'me', 'kind': 'quoted', 'text': '我领了红包'},
            {'from': 'me', 'text': '我领了红包', 'vision_uncertain': True},
            {'from': 'me', 'text': '我领了红包', 'uncertainties': ['文字识别置信度偏低']},
            {'from': 'me', 'text': '如果我领了红包，再跟你说'},
            {'from': 'me', 'text': '他说“我领了红包”'},
        ):
            with self.subTest(row=row):
                rows = [{'from': 'her', 'kind': 'red_packet', 'text': '当前红包'}, row]
                self.assertFalse(replycheck.grounded('我领了红包', rows))

    def test_human_confirmed_current_text_can_resolve_ocr_uncertainty(self):
        rows = [{'from': 'her', 'kind': 'red_packet', 'text': '当前红包'},
                {'from': 'me', 'text': '我领了红包', 'vision_uncertain': True, 'text_confirmation': 'user_confirmed'}]
        self.assertTrue(replycheck.grounded('我领了红包', rows))

    def test_future_self_words_do_not_supply_completed_action_evidence(self):
        for kind, source, reply in (
            ('transfer', '等钱收到了再说', '钱收到了'),
            ('official_account', '我看完这篇后再聊', '我看完这篇'),
            ('app_card', '我稍后打开这个看看', '我打开这个'),
        ):
            with self.subTest(source=source):
                rows = [{'from': 'her', 'kind': kind, 'text': '当前卡片'}, {'from': 'me', 'text': source}]
                self.assertFalse(replycheck.grounded(reply, rows))

    def test_card_visible_status_is_not_self_completion(self):
        for kind in ('red_packet', 'transfer'):
            with self.subTest(kind=kind):
                rows = [{'from': 'her', 'kind': kind, 'text': '￥88\n已收款\n微信转账'}]
                self.assertFalse(replycheck.grounded('钱收到了', rows))

    def test_conditions_and_future_actions_do_not_claim_completion(self):
        rows = [{'from': 'her', 'kind': 'transfer', 'text': '当前转账'},
                {'from': 'her', 'kind': 'official_account', 'text': '一篇文章'}]
        for text in ('如果钱收到了就好了', '如果我领了红包就好了',
                     '等我看完这篇再聊', '等钱到账了再说', '我看完这篇后再聊',
                     '我稍后打开这个看看', '我准备下载这个应用'):
            with self.subTest(text=text):
                self.assertTrue(replycheck.grounded(text, rows))

    def test_conditional_completion_does_not_authorize_a_reply_commitment(self):
        rows = [{'from': 'her', 'kind': 'transfer', 'text': '当前转账'},
                {'from': 'her', 'kind': 'official_account', 'text': '一篇文章'}]
        for text in ('如果钱收到了，我再告诉你', '如果我领了红包，再跟你说',
                     '等我看完这篇再跟你说'):
            with self.subTest(text=text):
                self.assertTrue(content.card_reply_guard(text, '', rows))
                self.assertFalse(replycheck.grounded(text, rows))

    def test_future_or_question_tail_does_not_excuse_prior_assertion(self):
        rows = [{'from': 'her', 'kind': 'transfer', 'text': '当前转账'},
                {'from': 'her', 'kind': 'official_account', 'text': '一篇文章'}]
        for text in ('钱收到了，我稍后再说', '我已经看完这篇，等会再聊',
                     '我看完这篇了，再跟你聊', '我领了红包，可以吗？',
                     '我已经看完这篇，你要等我吗？'):
            with self.subTest(text=text):
                self.assertFalse(replycheck.grounded(text, rows))

    def test_incidental_future_syllables_do_not_excuse_completed_claims(self):
        rows = [{'from': 'her', 'kind': 'transfer', 'text': '当前转账'},
                {'from': 'her', 'kind': 'red_packet', 'text': '当前红包'},
                {'from': 'her', 'kind': 'official_account', 'text': '一篇文章'}]
        for text in ('这笔重要的钱收到了', '我终于把重要的钱收到了',
                     '主要是我领了红包', '要知道我已经领了红包',
                     '我开会时领了红包', '我将就着看完这篇了',
                     '我稍后已经看完这篇了', '这笔钱等级很高我已经领了红包',
                     '开会时钱到账了', '我开会前已经打开这个了',
                     '刚开完会钱收到了', '这笔钱等级很高我领到红包了'):
            with self.subTest(text=text):
                self.assertFalse(replycheck.grounded(text, rows))

    def test_near_verb_future_modifiers_remain_noncompleted(self):
        rows = [{'from': 'her', 'kind': 'app_card', 'text': '当前入口'}]
        for text in ('我会打开这个', '我要打开这个', '我将打开这个',
                     '我稍后打开这个看看', '我准备下载这个应用'):
            with self.subTest(text=text):
                self.assertTrue(content.card_reply_guard(text, '', rows))

    def test_plan_as_method_does_not_bypass_completed_fact_check(self):
        rows = [{'from': 'her', 'kind': 'red_packet', 'text': '当前红包'}]
        for text in ('我按计划领了红包', '我按照计划领了红包', '我按计划收到了钱'):
            with self.subTest(text=text):
                self.assertFalse(content.card_reply_guard(text, '', rows))
                self.assertFalse(replycheck.grounded(text, rows))

    def test_reliable_current_completion_can_describe_a_method(self):
        for source in ('我按计划领了红包', '我按照计划领了红包'):
            with self.subTest(source=source):
                rows = [{'from': 'her', 'kind': 'red_packet', 'text': '当前红包'},
                        {'from': 'me', 'text': source}]
                self.assertTrue(replycheck.grounded(source, rows))
                self.assertTrue(replycheck.grounded('领了红包', rows))

    def test_future_receipt_plan_does_not_supply_completed_receipt(self):
        for source in ('我计划领取了红包', '我打算领取了红包', '我准备领取了红包'):
            with self.subTest(source=source):
                rows = [{'from': 'her', 'kind': 'red_packet', 'text': '当前红包'},
                        {'from': 'me', 'text': source}]
                self.assertFalse(replycheck.grounded('我领取了红包', rows))

    def test_review_keeps_good_reply_without_another_call(self):
        rows = self.cards(confirmation='我领了红包')
        answers = {'replies': ['我领了红包', '谢谢你'], 'best_index': 0}
        with patch.object(replycheck, 'chat', return_value=json.dumps(answers)) as model:
            result = replycheck.review(rows, ['我领了红包', '谢谢你'], 'synthetic', 'model', 10)
        self.assertEqual(list(result), ['谢谢你'])
        self.assertEqual(model.call_count, 1)


if __name__ == '__main__':
    unittest.main()
