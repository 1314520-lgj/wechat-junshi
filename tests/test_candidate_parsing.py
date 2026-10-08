"""候选解析必须能吃下模型「按行返回多个 JSON 数组」的真实格式。

背景：`_parse_candidates` 曾对整串不是合法 JSON、但以 `[` 开头的内容直接判定失败，
导致 selftest 里 `'["a"]\\n["b"]\\n["c"]'` 这类用例抛错（逐行兜底逻辑不可达）；
同一处还有一行 `startswith('[')` 的死分支，使 `'["a"], ["b"], ["c"]'` 也无法解析。
本用例覆盖这两条路径，防止再次退化。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / 'engine').is_dir():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / 'engine'))

from draft import _parse_candidates
from deepseek import LlmError


class CandidateParsing(unittest.TestCase):
    def test_single_json_array(self):
        self.assertEqual(_parse_candidates('["a","b","c"]'), ['a', 'b', 'c'])

    def test_fenced_json_array(self):
        self.assertEqual(_parse_candidates('```json\n["x", "y", "z"]\n```'), ['x', 'y', 'z'])

    def test_numbered_lines(self):
        self.assertEqual(_parse_candidates('1. 你好\n2. 在吗\n3. 咋了'), ['你好', '在吗', '咋了'])

    def test_lone_candidate(self):
        self.assertEqual(_parse_candidates('["只有一条"]'), ['只有一条'])

    def test_separate_arrays_one_per_line(self):
        """整串不是合法 JSON，但每行各是一个数组：必须走逐行兜底。"""
        self.assertEqual(
            _parse_candidates('["好，明天下午"]\n["好嘞，明天聊"]\n["行，今晚弄"]'),
            ['好，明天下午', '好嘞，明天聊', '行，今晚弄'])

    def test_several_arrays_on_one_line(self):
        """一行内并排多个数组：正则兜底必须生效，不能被跳过。"""
        self.assertEqual(_parse_candidates('["a"], ["b"], ["c"]'), ['a', 'b', 'c'])

    def test_trailing_punctuation_is_cleaned(self):
        self.assertEqual(
            _parse_candidates('["知道了。","真的吗？","好～"]'),
            ['知道了', '真的吗？', '好～'])

    def test_broken_object_payload_is_rejected(self):
        """损坏的对象负载必须判失败，绝不能把 JSON 原文当成候选回复。"""
        with self.assertRaises(LlmError):
            _parse_candidates('{"candidates": ["a", "b"}')

    def test_capped_at_three(self):
        self.assertEqual(_parse_candidates('["1","2","3","4","5"]'), ['1', '2', '3'])


if __name__ == '__main__':
    unittest.main()
