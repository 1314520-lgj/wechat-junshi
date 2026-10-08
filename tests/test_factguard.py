"""事实绑定护栏必须「有据放行、无据拦截」——两个方向都要锁死。

背景：`factguard.py` 是起草回复前的词法护栏。它做两件事：
(1) 从对话里抽出日期/时间/地点/事件（dates/places/events/times），
(2) 检查待发回复有没有把「原文没有的信息」编出来（编造承诺、编造没看手机、
    编造正在吃饭/位置、编造剩余数量、编造对方情绪）。

第二件事以前完全没有测试，风险是双向的：
  - 该拦没拦 → 助手替用户编造经历，这是产品定位（「洞察不猜」）的直接违背；
  - 不该拦却拦 → 护栏变砖墙，把正常回复全挡掉，用户只能拿到兜底话术。
所以下面的用例里，**「放行」和「拦截」同等重要**，每类都成对出现。

这些函数是纯词法逻辑（无 Windows / 无 GPU / 无网络 / 无模型调用）。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'engine').is_dir():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / 'engine'))

from factguard import (_assertive_units, _entry_action, cancelled,
                       conversational_detail_issue, dates, evidence_units, events,
                       facts_bound, personal_assertion_issue, places,
                       remaining_quantity_issue)


def her(text, **extra):
    return {'from': 'her', 'text': text, 'kind': 'text', **extra}


def me(text, **extra):
    return {'from': 'me', 'text': text, 'kind': 'text', **extra}


def no_times(_text):
    """facts_bound 要求一个 times() 回调；本文件不关心时间，恒返回空集。"""
    return set()


class Dates(unittest.TestCase):
    def test_relative_days_are_recognised(self):
        self.assertEqual(dates('今晚见'), {'今天'})
        self.assertEqual(dates('明晚见'), {'明天'})
        self.assertEqual(dates('昨天说的'), {'昨天'})
        self.assertEqual(dates('后天'), {'后天'})

    def test_time_words_normalise_to_canonical_day(self):
        """今晚/今早 都折算成今天；明晚/明早 都折算成明天，避免同日多种写法。"""
        self.assertEqual(dates('今早'), {'今天'})
        self.assertEqual(dates('明早'), {'明天'})
        self.assertEqual(dates('昨日'), {'昨天'})

    def test_weekday_normalises_xingqi_to_zhou(self):
        self.assertEqual(dates('星期三'), {'周三'})
        self.assertEqual(dates('周天'), {'周日'})

    def test_month_day_and_slash_forms_normalise(self):
        self.assertEqual(dates('7月8号'), {'7/8'})
        self.assertEqual(dates('07月08日'), {'7/8'})
        self.assertEqual(dates('12/25'), {'12/25'})

    def test_multiple_dates_are_all_returned(self):
        self.assertEqual(dates('明天和周三'), {'明天', '周三'})

    def test_no_date_yields_empty_set(self):
        self.assertEqual(dates('在吗'), set())


class Places(unittest.TestCase):
    def test_named_venue_suffixes(self):
        self.assertIn('会议室', places('会议室见'))
        self.assertIn('图书馆', places('去图书馆'))

    def test_definite_references_to_a_shared_place(self):
        """『楼下那家店』『老地方』是双方已知地点，是事实而非建议。"""
        self.assertIn('老地方', places('老地方见'))
        self.assertTrue(any('那家' in p for p in places('楼下那家店')))

    def test_generic_suggestion_is_not_a_place(self):
        """『找个地方』没有指定地点，不能当成已确定地点。"""
        self.assertEqual(places('我们找个地方吃饭吧'), set())

    def test_date_and_clock_are_stripped_before_place_extraction(self):
        """时间词要被剥掉，否则会被当成地点名词的一部分。"""
        self.assertNotIn('明天', places('明天会议室见'))


class Events(unittest.TestCase):
    def test_common_events(self):
        self.assertEqual(events('明天开会'), {'开会'})
        self.assertEqual(events('聚餐和培训'), {'聚餐', '培训'})

    def test_no_event(self):
        self.assertEqual(events('在吗'), set())


class Cancelled(unittest.TestCase):
    def test_plain_cancellation(self):
        self.assertTrue(cancelled('取消了'))

    def test_negated_cancellation_is_not_a_cancellation(self):
        self.assertFalse(cancelled('没有取消'))
        self.assertFalse(cancelled('还没取消'))
        self.assertFalse(cancelled('尚未取消'))

    def test_negative_marker_after_word_does_not_suppress(self):
        """『取消不是我的意思』里，否定词在『取消』之后，不构成「没取消」。"""
        self.assertTrue(cancelled('取消不是我说的'))


class EvidenceUnits(unittest.TestCase):
    def test_sentence_split_keeps_first_flag(self):
        units = list(evidence_units('明天开会。取消了'))
        self.assertEqual(units[0][0], '明天开会')
        self.assertIs(units[0][2], True)

    def test_cancellation_tail_applies_to_its_sentence(self):
        """裸的『取消了』尾巴只作用于本句，不能扩散到另一句的安排。"""
        units = list(evidence_units('明天开会，取消了。后天聚餐'))
        cancelled_flags = {u: c for u, c, _ in units}
        self.assertTrue(cancelled_flags['明天开会'])
        self.assertIs(cancelled_flags['后天聚餐'], False)

    def test_time_bearing_cancellation_stays_local(self):
        """带时间词的那条不是「裸取消尾巴」，不该把整句拖成取消态。"""
        units = {u: c for u, c, _ in evidence_units('明天开会，明天取消了。后天聚餐')}
        self.assertIs(units['后天聚餐'], False)


class AssertiveUnits(unittest.TestCase):
    def test_questions_and_conditionals_are_dropped(self):
        self.assertEqual(_assertive_units('我在吃饭？真的吗，我在家'),
                         ['我在家'])

    def test_hedged_clauses_are_dropped(self):
        self.assertEqual(_assertive_units('可能在家，也许在公司，我确定在家'), ['我确定在家'])

    def test_plain_assertions_survive(self):
        self.assertEqual(_assertive_units('我到家了，刚洗完澡'), ['我到家了', '刚洗完澡'])


class EntryAction(unittest.TestCase):
    def test_verbs_map_to_canonical_actions(self):
        cases = {'安装过': 'install', '下载': 'download', '关注': 'follow', '试用过': 'try',
                 '打开过': 'open', '点进去': 'open', '了解过': 'know'}
        for verb, expected in cases.items():
            with self.subTest(verb=verb):
                self.assertEqual(_entry_action({'action': verb}), expected)

    def test_unknown_verb_yields_none(self):
        self.assertIsNone(_entry_action({'action': '发疯'}))


class RemainingQuantity(unittest.TestCase):
    def test_invented_count_is_blocked(self):
        self.assertIsNotNone(remaining_quantity_issue('还差三处就好', [her('在吗')]))

    def test_count_supported_by_own_text_passes(self):
        self.assertIsNone(
            remaining_quantity_issue('还差三处就好', [her('在吗'), me('还差三处')]))

    def test_count_supported_by_other_text_passes(self):
        self.assertIsNone(
            remaining_quantity_issue('还差三处就好', [her('还差三处')]))

    def test_question_about_count_is_not_a_claim(self):
        """『还差三处吗』是在问，不是在断言，无据也要放行。"""
        self.assertIsNone(remaining_quantity_issue('还差三处吗？', [her('在吗')]))

    def test_hedged_count_is_not_a_claim(self):
        self.assertIsNone(remaining_quantity_issue('可能还差三处', [her('在吗')]))

    def test_chinese_numeral_is_compared_numerically(self):
        """『还差3处』与『还差三处』是同一个数量，不能因写法不同而误拦。"""
        self.assertIsNone(remaining_quantity_issue('还差三处', [me('还差3处')]))

    def test_negated_evidence_does_not_support(self):
        self.assertIsNotNone(remaining_quantity_issue('还差三处', [me('已经不差三处了')]))


class PersonalAssertion(unittest.TestCase):
    def setUp(self):
        self.ctx = [her('你怎么又忘了?'), me('抱歉')]

    def test_invented_activity_is_blocked(self):
        issue = personal_assertion_issue('我在吃饭呢', self.ctx)
        self.assertIsNotNone(issue)

    def test_invented_absolute_promise_is_blocked(self):
        issue = personal_assertion_issue('我保证下次一定提前告诉你', self.ctx)
        self.assertIsNotNone(issue)

    def test_promise_supported_by_own_text_passes(self):
        ctx = self.ctx + [me('我保证下次一定提前告诉你')]
        self.assertIsNone(personal_assertion_issue('我保证下次一定提前告诉你', ctx))

    def test_own_activity_supported_by_own_text_passes(self):
        ctx = self.ctx + [me('我在吃饭')]
        self.assertIsNone(personal_assertion_issue('我在吃饭', ctx))

    def test_incoming_text_never_authorises_own_claim(self):
        """对方说『你在家吧』不能成为我自称在家的依据。"""
        ctx = [her('你在家吧'), me('嗯')]
        self.assertIsNotNone(personal_assertion_issue('我在家', ctx))

    def test_invented_feeling_claim_is_blocked(self):
        """不能断言『我知道你生气』——除非本人有可靠情绪表述。"""
        self.assertIsNotNone(personal_assertion_issue('我知道你现在很生气', self.ctx))

    def test_feeling_claim_backed_by_her_report_passes(self):
        ctx = [her('我很生气'), me('抱歉')]
        self.assertIsNone(personal_assertion_issue('我知道你很生气', ctx))

    def test_ordinary_care_is_allowed(self):
        """寻常的关心不该被当成编造事实拦下。"""
        self.assertIsNone(personal_assertion_issue('别太累了，早点休息', self.ctx))

    def test_conditional_clause_does_not_create_a_promise(self):
        ctx = self.ctx + [me('我保证下次一定提前告诉你')]
        self.assertIsNone(personal_assertion_issue('要是我不提前告诉你，你就骂我', ctx))

    def test_low_confidence_message_does_not_authorise_claim(self):
        """OCR 置信度偏低且未经人工确认的句子，不能作为事实依据。"""
        ctx = [her('我生气了', vision_uncertain=True), me('嗯')]
        self.assertIsNotNone(personal_assertion_issue('我知道你很生气', ctx))

    def test_user_confirmed_low_confidence_message_does_authorise(self):
        ctx = [her('我生气了', vision_uncertain=True, text_confirmation='user_confirmed'),
               me('嗯')]
        self.assertIsNone(personal_assertion_issue('我知道你很生气', ctx))


class ConversationalDetail(unittest.TestCase):
    def setUp(self):
        self.ctx = [her('你怎么又忘了?'), me('抱歉')]

    def test_invented_phone_excuse_is_blocked(self):
        self.assertIsNotNone(conversational_detail_issue('我没看手机', self.ctx))

    def test_invented_reply_intent_is_blocked(self):
        self.assertIsNotNone(conversational_detail_issue('我不是故意不回的', self.ctx))

    def test_invented_past_habit_is_blocked(self):
        self.assertIsNotNone(conversational_detail_issue('我以前一直都记得的', self.ctx))

    def test_phone_excuse_backed_by_own_text_passes(self):
        ctx = self.ctx + [me('我没看手机')]
        self.assertIsNone(conversational_detail_issue('我没看手机', ctx))

    def test_reply_intent_backed_by_own_text_passes(self):
        ctx = self.ctx + [me('我不是故意不回的')]
        self.assertIsNone(conversational_detail_issue('我不是故意不回的', ctx))

    def test_question_form_of_excuse_is_not_a_claim(self):
        self.assertIsNone(conversational_detail_issue('我没看手机吗？', self.ctx))

    def test_invented_period_is_blocked(self):
        """原文没说『下班后』，却把一件具体事安排在那个时段——必须拦。

        注意不能拿『下班后好好休息』当反例：那句命中了 rest_suggestion 豁免
        （纯关心，没断言任何事发生的时段），见下一条用例。
        """
        self.assertIsNotNone(conversational_detail_issue('下班后回你', self.ctx))
        self.assertIsNotNone(conversational_detail_issue('下班后我把方案发你', self.ctx))

    def test_period_backed_by_conversation_passes(self):
        ctx = [her('你下班后记得回我'), me('好')]
        self.assertIsNone(conversational_detail_issue('下班后回你', ctx))

    def test_rest_suggestion_is_exempt_from_period_rule(self):
        """『下班后好好休息』是关心建议，不是对事件时段的断言，豁免时段规则。"""
        self.assertIsNone(conversational_detail_issue('你下班后先休息吧', self.ctx))
        self.assertIsNone(conversational_detail_issue('下班后好好休息', self.ctx))

    def test_plain_reply_has_no_issue(self):
        self.assertIsNone(conversational_detail_issue('我记住了，这次一定', self.ctx))

    def test_personal_issue_takes_precedence(self):
        """conversational_detail_issue 必须先跑个人断言护栏。"""
        self.assertIsNotNone(conversational_detail_issue('我在吃饭', self.ctx))


class FactsBound(unittest.TestCase):
    def test_reply_without_facts_is_bound(self):
        self.assertTrue(facts_bound('好的我知道了', [her('在吗')], no_times))

    def test_invented_date_is_not_bound(self):
        self.assertFalse(facts_bound('那我们明天见', [her('在吗'), me('嗯')], no_times))

    def test_date_supported_by_her_text_is_bound(self):
        self.assertTrue(facts_bound('那我们明天见', [her('明天见'), me('嗯')], no_times))

    def test_tentative_question_is_not_bound(self):
        """拿不准的试探句不能宣布事实已对齐。"""
        self.assertFalse(facts_bound('是明天见吗？', [her('在吗'), me('嗯')], no_times))

    def test_denied_and_affirmed_clauses_cannot_lend_each_other_status(self):
        """同句里既有断言又有否定时，不能互相背书，一律保守拦截。"""
        self.assertFalse(
            facts_bound('不去图书馆，明天见会议室', [her('明天会议室见'), me('嗯')], no_times))

    def test_mixed_cancelled_and_asserted_clauses_are_blocked(self):
        self.assertFalse(
            facts_bound('明天开会取消了，后天聚餐', [her('明天开会'), me('嗯')], no_times))

    def test_personal_issue_blocks_facts_bound(self):
        self.assertFalse(facts_bound('我在吃饭，明天见', [her('明天见')], no_times))

    def test_place_supported_by_conversation_is_bound(self):
        self.assertTrue(facts_bound('老地方见', [her('老地方见'), me('好')], no_times))


if __name__ == '__main__':
    unittest.main()
