"""Jev 判断的「模型输出 → 结构化答案」解析必须容错、且不能放宽枚举口径。

背景：`questions.py` 承担两件容易悄悄退化的事——
(1) 从模型回复里抠 JSON。模型经常在 JSON 前写一句带花括号的中文（「我{觉得}…」），
    第一个平衡块解析失败时必须继续往后找，而不是直接判定「没给判断」降级；
(2) 把模型给的枚举值/分数收敛到白名单与合法区间。任何键名漂移、越界分数、
    自造枚举都必须被拒，否则会喂给起草阶段一份看似有据、实则编造的判断。

这些函数是纯逻辑（无 Windows / 无 GPU / 无网络），此前完全没有直接测试。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'engine').is_dir():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / 'engine'))

from questions import (_CHOICES, CHOICE_LABELS, JUDGE_QUESTIONS, _ev, _extract_json,
                       _pick, build_judge_prompt, build_rank_prompt, build_state,
                       finite_number, guidance_text, line_of, parse_judgment, parse_rank)


def full_judgment(**overrides):
    """一份形状完整的模型输出；overrides 覆盖顶层字段。"""
    data = {
        "literal_question": {"value": False, "evidence": "他说『你肯定又忘了』"},
        "true_intent": {"choice": "confirm_you_care", "evidence": "上次那家店"},
        "danger_level": {"score": 5.4, "evidence": "语气变冷"},
        "should_reply_now": {"value": True, "evidence": "时间已给出"},
        "best_action": {"choice": "check_history", "evidence": "要求复述"},
        "she_needs": {"choice": "care", "evidence": "试探你是否记得"},
        "tension_resolved": {"value": False},
        "psychology": {"value": "有点着急，想尽快定下来", "evidence": "连问两次"},
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


class ExtractJson(unittest.TestCase):
    """从自由文本里抠第一个可解析的平衡 JSON 对象。"""

    def test_plain_object(self):
        self.assertEqual(_extract_json('{"a":1}'), '{"a":1}')

    def test_fenced_block_is_unwrapped(self):
        self.assertEqual(_extract_json('```json\n{"b":2}\n```'), '{"b":2}')

    def test_bare_fence_is_unwrapped(self):
        self.assertEqual(_extract_json('```\n{"c":3}\n```'), '{"c":3}')

    def test_leading_brace_in_prose_is_skipped(self):
        """文档明确承诺：前面带花括号的说明句不能让整次判断降级。"""
        self.assertEqual(_extract_json('我觉得{这样}不对。{"a":1}'), '{"a":1}')

    def test_first_invalid_block_falls_through_to_next(self):
        self.assertEqual(_extract_json('{bad} {"ok":1}'), '{"ok":1}')

    def test_braces_inside_strings_are_not_counted(self):
        self.assertEqual(_extract_json('{"a":"}"}'), '{"a":"}"}')

    def test_escaped_quote_inside_string_is_not_a_terminator(self):
        self.assertEqual(_extract_json(r'{"a":"x\"y"}'), r'{"a":"x\"y"}')

    def test_unclosed_object_returns_none(self):
        self.assertIsNone(_extract_json('{"a":1'))

    def test_no_object_returns_none(self):
        self.assertIsNone(_extract_json('模型什么都没说'))

    def test_empty_string_returns_none(self):
        self.assertIsNone(_extract_json(''))


class FiniteNumber(unittest.TestCase):
    def test_bool_is_not_a_number(self):
        """True 是 int 的子类，但绝不能当成 1 分或 1.0 概率。"""
        self.assertFalse(finite_number(True))
        self.assertFalse(finite_number(False))

    def test_ints_and_floats_pass(self):
        self.assertTrue(finite_number(0))
        self.assertTrue(finite_number(9))
        self.assertTrue(finite_number(1.5))

    def test_nan_and_inf_are_rejected(self):
        self.assertFalse(finite_number(float('nan')))
        self.assertFalse(finite_number(float('inf')))
        self.assertFalse(finite_number(float('-inf')))

    def test_non_numbers_are_rejected(self):
        for value in ('1', None, [], {}, [1]):
            with self.subTest(value=value):
                self.assertFalse(finite_number(value))


class Pick(unittest.TestCase):
    ALLOWED = ('vent_anger', 'casual_chat', 'close_topic')

    def test_explicit_choice_wins(self):
        self.assertEqual(_pick({'choice': 'vent_anger'}, self.ALLOWED), 'vent_anger')

    def test_answer_key_is_accepted_like_choice(self):
        self.assertEqual(_pick({'answer': 'casual_chat'}, self.ALLOWED), 'casual_chat')

    def test_out_of_whitelist_choice_is_rejected(self):
        self.assertIsNone(_pick({'choice': '发疯'}, self.ALLOWED))

    def test_probabilities_pick_the_mode(self):
        self.assertEqual(
            _pick({'vent_anger': 0.2, 'casual_chat': 0.8, 'close_topic': 0.0}, self.ALLOWED),
            'casual_chat')

    def test_out_of_range_probabilities_ignored(self):
        """概率必须落在 [0,1]；越界值不参与比大小。"""
        self.assertEqual(_pick({'vent_anger': 2.0, 'casual_chat': 0.3}, self.ALLOWED), 'casual_chat')

    def test_all_zero_probabilities_resolve_by_order_not_by_none(self):
        """全 0 概率不是「无选项」：_pick 只负责挑一个合法选项，0.0 > -1.0 使首个胜出。
        真正把「全 0 分布」清掉的逻辑在 parse_rank 里（见 ParseRank 对应用例）。"""
        self.assertEqual(_pick({'vent_anger': 0.0, 'casual_chat': 0.0}, self.ALLOWED),
                         'vent_anger')

    def test_non_dict_yields_none(self):
        self.assertIsNone(_pick('casual_chat', self.ALLOWED))


class Evidence(unittest.TestCase):
    def test_dict_value_and_evidence(self):
        self.assertEqual(_ev({'value': True, 'evidence': '他说“你忘了”'}), (True, '他说“你忘了”'))

    def test_reason_is_accepted_as_evidence(self):
        self.assertEqual(_ev({'value': 3, 'reason': '语气冷'}), (3, '语气冷'))

    def test_bare_value_has_no_evidence(self):
        self.assertEqual(_ev(3), (3, ''))

    def test_evidence_is_trimmed_to_80_chars(self):
        _, evidence = _ev({'value': 1, 'evidence': '甲' * 200})
        self.assertEqual(len(evidence), 80)

    def test_score_key_is_recognised(self):
        self.assertEqual(_ev({'score': 7, 'evidence': 'x'}), (7, 'x'))

    def test_choice_key_is_recognised(self):
        self.assertEqual(_ev({'choice': 'care', 'evidence': 'x'}), ('care', 'x'))


class ParseJudgment(unittest.TestCase):
    def test_full_payload_maps_every_question(self):
        out = parse_judgment(full_judgment())
        self.assertEqual(sorted(out),
                         ['best_action', 'danger_level', 'literal_question', 'psychology',
                          'she_needs', 'should_reply_now', 'tension_resolved', 'true_intent'])

    def test_noul_answers_become_float_flags(self):
        out = parse_judgment(full_judgment())
        self.assertEqual(out['literal_question'], {'type': 'noul', 'noul': 0.0,
                                                   'evidence': '他说『你肯定又忘了』'})
        self.assertEqual(out['should_reply_now']['noul'], 1.0)
        self.assertEqual(out['tension_resolved']['noul'], 0.0)

    def test_choice_answers_are_whitelisted(self):
        out = parse_judgment(full_judgment())
        self.assertEqual(out['true_intent'], {'type': 'choice', 'choice': 'confirm_you_care',
                                              'evidence': '上次那家店'})
        self.assertEqual(out['best_action']['choice'], 'check_history')
        self.assertEqual(out['she_needs']['choice'], 'care')

    def test_danger_level_is_rounded_and_clamped(self):
        self.assertEqual(parse_judgment(full_judgment())['danger_level']['score'], 5)
        self.assertEqual(parse_judgment('{"danger_level":{"score":42}}')['danger_level']['score'], 9)
        self.assertEqual(parse_judgment('{"danger_level":{"score":-3}}')['danger_level']['score'], 0)

    def test_invented_choice_is_dropped_entirely(self):
        """自造枚举不能进结果——宁可缺一项，也不能喂起草阶段一个假判断。"""
        out = parse_judgment('{"true_intent":{"choice":"发疯"},"best_action":{"choice":"apologize"}}')
        self.assertNotIn('true_intent', out)
        self.assertEqual(out['best_action']['choice'], 'apologize')

    def test_bare_bool_still_parses_for_legacy_shape(self):
        out = parse_judgment('{"literal_question":true,"tension_resolved":false}')
        self.assertEqual(out['literal_question']['noul'], 1.0)
        self.assertEqual(out['tension_resolved']['noul'], 0.0)

    def test_bare_choice_string_is_accepted(self):
        out = parse_judgment('{"true_intent":"casual_chat"}')
        self.assertEqual(out['true_intent']['choice'], 'casual_chat')

    def test_choice_given_as_probability_dict_is_resolved(self):
        out = parse_judgment('{"she_needs":{"apology":0.1,"care":0.9}}')
        self.assertEqual(out['she_needs']['choice'], 'care')

    def test_psychology_is_trimmed_to_40_chars(self):
        out = parse_judgment(json.dumps({'psychology': '急' * 100}, ensure_ascii=False))
        self.assertEqual(len(out['psychology']['text']), 40)

    def test_psychology_accepts_bare_string(self):
        self.assertEqual(parse_judgment('{"psychology":"轻松开心"}')['psychology']['text'], '轻松开心')

    def test_blank_psychology_is_dropped(self):
        self.assertNotIn('psychology', parse_judgment('{"psychology":"   "}'))

    def test_danger_level_bool_is_not_a_score(self):
        """models 偶尔把 score 写成 true；bool 必须是数值的例外，不能变 1 分。"""
        self.assertNotIn('danger_level', parse_judgment('{"danger_level":true}'))

    def test_unparseable_content_yields_empty_dict(self):
        self.assertEqual(parse_judgment('完全没有 JSON'), {})
        self.assertEqual(parse_judgment(''), {})

    def test_empty_object_yields_empty_dict(self):
        self.assertEqual(parse_judgment('{}'), {})


class ParseRank(unittest.TestCase):
    def test_explicit_best_reply_and_probabilities(self):
        out = parse_rank('{"best_reply":"reply_b","probabilities":'
                         '{"reply_a":0.1,"reply_b":0.7,"reply_c":0.2},"reason":"具体"}',
                         ['甲', '乙', '丙'])
        best = out['best_reply']
        self.assertEqual(best['choice'], 'reply_b')
        self.assertEqual(best['reason'], '具体')
        self.assertAlmostEqual(sum(best['probabilities'].values()), 1.0, places=3)
        self.assertEqual(max(best['probabilities'], key=best['probabilities'].get), 'reply_b')

    def test_partial_probabilities_are_synthesised_and_normalised(self):
        """只给了 best_reply、没给全概率时，要合成分布，避免界面显示 0% 却推荐它。"""
        out = parse_rank('{"best_reply":"reply_b"}', ['甲', '乙', '丙'])['best_reply']
        probs = out['probabilities']
        self.assertEqual(set(probs), {'reply_a', 'reply_b', 'reply_c'})
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=3)
        self.assertEqual(max(probs, key=probs.get), 'reply_b')

    def test_all_zero_probabilities_are_not_trusted(self):
        out = parse_rank('{"best_reply":"reply_a","probabilities":'
                         '{"reply_a":0,"reply_b":0}}', ['甲', '乙'])['best_reply']
        self.assertEqual(out['choice'], 'reply_a')
        self.assertGreater(out['probabilities']['reply_a'], 0)

    def test_best_reply_missing_falls_back_to_modal_probability(self):
        out = parse_rank('{"probabilities":{"reply_a":0.2,"reply_b":0.8}}', ['甲', '乙'])
        self.assertEqual(out['best_reply']['choice'], 'reply_b')

    def test_unknown_best_reply_with_no_probabilities_is_rejected(self):
        self.assertEqual(parse_rank('{"best_reply":"reply_z"}', ['甲', '乙', '丙']), {})

    def test_only_two_candidates_uses_two_keys(self):
        out = parse_rank('{"best_reply":"reply_b","reason":"x"}', ['甲', '乙'])['best_reply']
        self.assertEqual(set(out['probabilities']), {'reply_a', 'reply_b'})
        self.assertAlmostEqual(sum(out['probabilities'].values()), 1.0, places=3)

    def test_unparseable_content_yields_empty_dict(self):
        self.assertEqual(parse_rank('没有 JSON', ['甲', '乙']), {})


class GuidanceText(unittest.TestCase):
    def test_empty_answers_yield_empty_string(self):
        self.assertEqual(guidance_text({}), '')
        self.assertEqual(guidance_text(None), '')

    def test_choices_are_rendered_with_chinese_labels(self):
        out = parse_judgment(full_judgment())
        text = guidance_text(out)
        self.assertIn('判断参考', text)
        self.assertIn('希望确认你在意', text)
        self.assertIn('（confirm_you_care）', text)
        self.assertIn('先核对聊天记录', text)

    def test_psychology_is_included_when_present(self):
        text = guidance_text(parse_judgment(full_judgment()))
        self.assertIn('心理状态', text)

    def test_tension_and_literal_summary_line(self):
        text = guidance_text(parse_judgment(full_judgment()))
        self.assertIn('紧张度：5/9', text)
        self.assertIn('字面意思：否（有潜台词）', text)

    def test_evidence_is_appended_when_available(self):
        text = guidance_text(parse_judgment(full_judgment()))
        self.assertIn('依据：', text)

    def test_blank_answers_produce_no_dangling_header(self):
        """全空时不能只留一个「判断参考」光杆标题。"""
        self.assertEqual(guidance_text({'psychology': {}}), '')


class LineOf(unittest.TestCase):
    def test_tuple_form(self):
        self.assertEqual(line_of(('her', '在吗')), 'her: 在吗')

    def test_tuple_form_with_name_and_time(self):
        self.assertEqual(line_of(('her', '在吗', '小明', '10:30')), '小明 10:30: 在吗')

    def test_dict_form_with_group_identity(self):
        line = line_of({'from': 'her', 'text': '在吗', 'name': '小明', 'speaker_id': 'p1',
                        'identity_confidence': 'user_confirmed', 'identity_scope': 'observation'})
        self.assertIn('昵称[小明]', line)
        self.assertIn('身份[user_confirmed]', line)
        self.assertTrue(line.endswith('在吗'))

    def test_legacy_confirmed_without_observation_scope_is_downgraded(self):
        """历史数据里 confirmed 但没标 observation 的，必须降级待确认，不能冒充已确认。"""
        line = line_of({'from': 'her', 'text': '在吗', 'name': '小明', 'identity_confidence':
                        'user_confirmed', 'identity_scope': 'display'})
        self.assertIn('legacy_needs_confirmation', line)

    def test_system_kind_is_labelled_not_attributed(self):
        line = line_of({'from': 'her', 'text': 'xxx 撤回了一条消息', 'kind': 'system'})
        self.assertIn('微信系统记录（非人物发言）', line)

    def test_vision_uncertainty_is_surfaced(self):
        line = line_of({'from': 'her', 'text': '看图', 'kind': 'image',
                        'media_description': '一张桌子', 'vision_uncertain': True})
        self.assertIn('视觉识别存在不确定项', line)

    def test_unfinished_media_understanding_is_surfaced(self):
        line = line_of({'from': 'her', 'text': '视频', 'kind': 'video',
                        'media_description': '画面', 'media_understanding_complete': False})
        self.assertIn('媒体理解未完成', line)

    def test_original_message_without_text_is_empty_body(self):
        self.assertEqual(line_of({'from': 'me', 'text': None}), 'me: ')


class BuildState(unittest.TestCase):
    def test_tuples_are_normalised_to_dicts(self):
        state = build_state([('her', '在吗'), ('me', '在')], '朋友')
        self.assertEqual(state['chat']['messages'],
                         [{'from': 'her', 'text': '在吗'}, {'from': 'me', 'text': '在'}])

    def test_unknown_speaker_is_skipped_not_fatal(self):
        """analyze-text 可能传 system/未知来源；跳过即可，不能整次分析崩溃。"""
        state = build_state([('system', 'x'), ('her', '在吗'), ('me', '在')], '朋友')
        self.assertEqual([m['from'] for m in state['chat']['messages']], ['her', 'me'])

    def test_keep_trims_from_the_front(self):
        rows = [('her', str(i)) for i in range(20)]
        state = build_state(rows, '朋友', keep=3)
        self.assertEqual([m['text'] for m in state['chat']['messages']], ['17', '18', '19'])

    def test_latest_from_ignores_system_and_time_rows(self):
        rows = [{'from': 'her', 'text': '在吗'},
                {'from': 'her', 'text': '10:00', 'kind': 'time'}]
        self.assertEqual(build_state(rows, '朋友')['chat']['latest_from'], 'her')

    def test_latest_from_is_none_when_only_system_rows(self):
        rows = [{'from': 'her', 'text': 'x', 'kind': 'system'}]
        self.assertEqual(build_state(rows, '朋友')['chat']['latest_from'], 'none')

    def test_group_detected_from_name_field(self):
        self.assertTrue(build_state([('her', '在吗', '小明')], '同事')['chat']['is_group'])
        self.assertFalse(build_state([('her', '在吗')], '同事')['chat']['is_group'])

    def test_falsy_optional_fields_are_not_copied(self):
        """空字符串时间/种类不该污染状态，避免下游判成「有时间的媒体」。"""
        state = build_state([{'from': 'her', 'text': '在吗', 'time': '', 'kind': ''}], '朋友')
        self.assertEqual(state['chat']['messages'][0], {'from': 'her', 'text': '在吗'})

    def test_explicit_false_flags_are_preserved(self):
        """vision_uncertain=False / complete=False 是有意义的显式信息，必须保留。"""
        state = build_state([{'from': 'her', 'text': 'x', 'kind': 'image',
                              'media_understanding_complete': False}], '朋友')
        self.assertIs(state['chat']['messages'][0]['media_understanding_complete'], False)

    def test_reply_to_is_attached_when_given(self):
        self.assertEqual(build_state([('her', '在吗')], '朋友', reply_to='m1')['chat']['reply_to'], 'm1')
        self.assertNotIn('reply_to', build_state([('her', '在吗')], '朋友')['chat'])


class PromptWiring(unittest.TestCase):
    """提示词必须把全部题目和候选都送出去——少送一题就是静默降级。"""

    def setUp(self):
        self.state = build_state([('her', '你怎么又忘了?'), ('me', '抱歉')], '恋人')

    def test_judge_prompt_lists_every_question(self):
        prompt = build_judge_prompt(self.state)
        for name in JUDGE_QUESTIONS:
            self.assertIn(f'### {name}', prompt['user'])

    def test_judge_prompt_embeds_transcript(self):
        prompt = build_judge_prompt(self.state)
        self.assertIn('你怎么又忘了?', prompt['user'])
        self.assertIn('<<<对话开始>>>', prompt['user'])

    def test_judge_prompt_demands_json_only(self):
        prompt = build_judge_prompt(self.state)
        self.assertIn('不要输出 JSON 之外的任何文字', prompt['system'])

    def test_rank_prompt_names_only_the_given_candidates(self):
        prompt = build_rank_prompt(self.state, ['回复甲', '回复乙'])
        self.assertIn('reply_a: 回复甲', prompt['user'])
        self.assertIn('reply_b: 回复乙', prompt['user'])
        self.assertNotIn('reply_c', prompt['user'])

    def test_rank_prompt_with_three_candidates(self):
        prompt = build_rank_prompt(self.state, ['甲', '乙', '丙'])
        for key in ('reply_a', 'reply_b', 'reply_c'):
            self.assertIn(key, prompt['user'])


class ChoiceContract(unittest.TestCase):
    """_CHOICES / CHOICE_LABELS 必须与题目集一致——两边漂移就是枚举口径分叉。"""

    def test_choices_derive_from_question_criteria(self):
        for name, choices in _CHOICES.items():
            with self.subTest(name=name):
                self.assertEqual(choices, list(JUDGE_QUESTIONS[name]['criteria']))

    def test_every_choice_has_a_label(self):
        for name, choices in _CHOICES.items():
            for choice in choices:
                with self.subTest(name=name, choice=choice):
                    self.assertIn(choice, CHOICE_LABELS[name])

    def test_labels_have_no_extra_keys(self):
        for name, labels in CHOICE_LABELS.items():
            with self.subTest(name=name):
                self.assertEqual(sorted(labels), sorted(_CHOICES[name]))


if __name__ == '__main__':
    unittest.main()
