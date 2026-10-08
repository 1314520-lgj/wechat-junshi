"""离线回放回归：把「消息区截图 → 谁说了什么」整条链路拉到测试里。

## 为什么需要它

项目此前唯一的自动化覆盖是面板布局检查（Playwright）和几个纯函数单测，
而真正决定「军师读到了什么」的那条链路——截图裁剪 → OCR 行 → 归属判定
（谁说的）→ 时间戳 → 气泡多行合并 → 滚动去重——没有任何回归保护。
这块一旦坏了（比如某次调整把 her 判成 me，或把多行拆成多条），
表现是「建议质量变差」，不会抛异常，因此最难发现、代价也最大。

现状是真实样本只有 9 条消息，无法覆盖分支。本模块用合成画布 + 注入
OCR 行的方式补上覆盖：`Reader._ocr` 是整条链路上唯一调用 RapidOCR 的
地方，把它替换掉，其余代码（who_said / prepare_ocr / group_card_rows /
new_lines / has_color_ink）全部走真实路径。因此它验证的是真实逻辑，
只是不依赖模型文件与 GPU，可在 CI 里秒级跑完。

## 合成画布必须「像真的」——三个踩过的坑

这些约束是实测出来的，改动合成器前请先读：

1. **字迹必须是竖笔画，不能是实心色条。** `who_said` 取 OCR 框内的主导色
   作为气泡底色。实心色条会让主导色变成字迹本身，于是对比度算成 0，
   整行被误判为 gray。真实文字是稀疏笔画的，主导色仍是气泡底。
2. **字迹必须与气泡同色相、只是更暗。** 纯黑在绿底上会让
   `has_color_ink` 判定为「彩色内容」（它按色相余弦区分抗锯齿与彩色图，
   纯黑色度为 0），整行会被当成内联图片。真实抗锯齿文字继承底色色相。
3. **行距要接近真实排版（约 1.5 倍字高）。** 合并判据是
   `top - 上一行 bottom < 0.6 * lh`，而 `lh` 由字迹像素高度标定。
   行距太大会被正确地判成两条独立消息。
"""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

# ocr 模块在导入期就 `from rapidocr_onnxruntime import RapidOCR`，而这个包会拖进
# onnxruntime（约 200MB），不适合放进轻量的静态检查 CI job。本模块所有用例都
# 替换掉了识别引擎，只用引擎的**下游**逻辑（who_said / has_color_ink /
# prepare_ocr / new_lines / 缓存），因此只要模块能导入就够用；导不进来就整体跳过，
# 并在原因里写清楚怎么补上，而不是让 CI 变绿得不明不白。
try:
    import ocr as ocr_mod
except Exception as exc:  # pragma: no cover - 取决于本地是否装了 rapidocr
    raise unittest.SkipTest(
        '需要 rapidocr-onnxruntime 才能驱动 OCR 下游逻辑（离线回放不调用真实识别）：'
        f' {type(exc).__name__}: {exc}'
    ) from exc

# 画布与配色：全部按真实微信截图的取值。
WIDTH = 1000
PANE_BG = (245, 245, 245)          # 消息区底盘灰
ME_BG = (149, 236, 105)            # 自己的绿色气泡
HER_BG = (255, 255, 255)           # 对方白色气泡
ME_INK = (30, 50, 20)              # 绿底上的字：同色相、更暗
HER_INK = (60, 60, 60)             # 白底上的字
GLYPH_H = 16                       # 字迹像素高，决定 lh 标定
LINE_PITCH = 24                    # 行距（约 1.5 倍字高）
STROKE_STEP, STROKE_W = 6, 3       # 竖笔画间距与宽度


def canvas(height):
    img = np.zeros((height, WIDTH, 3), dtype=np.uint8)
    img[:, :] = PANE_BG
    return img


def bubble(img, x0, y0, x1, y1, bg):
    img[y0:y1, x0:x1] = bg


def glyphs(img, y0, ink, x0=700, x1=900, height=GLYPH_H):
    """在 y0 处画一行字：稀疏竖笔画，而不是实心色条（见模块文档第 1、2 条）。"""
    for x in range(x0, x1, STROKE_STEP):
        img[y0:y0 + height, x:x + STROKE_W] = ink


def box(x0, y0, x1, y1):
    """RapidOCR 的 box 格式：四点多边形（左上/右上/右下/左下）。"""
    return [(float(x0), float(y0)), (float(x1), float(y0)),
            (float(x1), float(y1)), (float(x0), float(y1))]


class RecordingReader(ocr_mod.Reader):
    """把 _ocr 换成「回放预先录好的行」，其余逻辑全部走真实实现。"""

    def __init__(self, rows, app=None):
        super().__init__(app or ocr_mod.DEFAULT)
        self.replay(rows)

    def replay(self, rows):
        """rows: [(box, text, confidence), ...]，坐标是原图坐标。"""
        self._replay = [(list(b), t, c) for b, t, c in rows]
        self.ocr_calls = 0
        self._ocr = self._replay_ocr

    def _replay_ocr(self, chat):
        self.ocr_calls += 1
        rows = self._replay
        return [(list(b), t, c) for b, t, c in rows]


class Attribution(unittest.TestCase):
    """谁说了什么：靠气泡底色区分 me / her。"""

    def test_green_bubble_is_attributed_to_me(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        reader = RecordingReader([(box(620, 112, 920, 128), '我发的消息', 0.98)])
        out = reader.read(img, PANE_BG)
        self.assertEqual(len(out), 1, out)
        who, name, text, _y, _t, kind = out[0]
        self.assertEqual(who, 'me')
        self.assertIsNone(name, 'me 的消息不应带发言人名')
        self.assertEqual(text, '我发的消息')
        self.assertEqual(kind, 'text')

    def test_white_bubble_is_attributed_to_her(self):
        img = canvas(900)
        bubble(img, 60, 100, 400, 140, HER_BG)
        glyphs(img, 112, HER_INK, x0=160, x1=360)
        reader = RecordingReader([(box(80, 112, 380, 128), '对方消息', 0.97)])
        out = reader.read(img, PANE_BG)
        self.assertEqual(len(out), 1, out)
        self.assertEqual(out[0][0], 'her')


class GrayText(unittest.TestCase):
    """灰字三分：居中且像时间 → 时间戳；左侧短文本 → 昵称；都不产出消息行。"""

    def test_centered_timestamp_is_not_a_message(self):
        img = canvas(900)
        reader = RecordingReader([(box(455, 200, 545, 220), '14:23', 0.99)])
        out = reader.read(img, PANE_BG)
        self.assertEqual(out, [], '时间戳不应产生消息行')
        self.assertIn('time', [b[4] for b in reader.last_boxes], reader.last_boxes)

    def test_left_edge_short_text_becomes_speaker_name(self):
        img = canvas(900)
        reader = RecordingReader([(box(20, 300, 90, 320), '张三', 0.99)])
        out = reader.read(img, PANE_BG)
        self.assertEqual(out, [], '昵称行本身不是消息')
        self.assertIn('name', [b[4] for b in reader.last_boxes], reader.last_boxes)


class MultiLineMerge(unittest.TestCase):
    """同一气泡内的多行必须合并成一条消息，而不是拆成多条。"""

    def test_adjacent_lines_in_same_bubble_are_merged(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 170, ME_BG)
        glyphs(img, 112, ME_INK)
        glyphs(img, 112 + LINE_PITCH, ME_INK)
        # 另外一条独立消息，用于把 lh 标定到真实字高
        bubble(img, 600, 240, 940, 280, ME_BG)
        glyphs(img, 250, ME_INK)
        rows = [(box(620, 112, 920, 128), '第一行', 0.98),
                (box(620, 112 + LINE_PITCH, 920, 128 + LINE_PITCH), '第二行', 0.98),
                (box(620, 250, 920, 266), '另一条', 0.98)]
        reader = RecordingReader(rows)
        out = reader.read(img, PANE_BG)
        self.assertEqual(len(out), 2, f'同气泡两行应合并、共 2 条消息，实际 {out}')
        self.assertEqual(out[0][2], '第一行第二行', out)
        self.assertEqual(out[1][2], '另一条', out)

    def test_lines_far_apart_stay_separate(self):
        # 反例：行距远超行高时**不应**合并，否则会把两条独立消息粘成一条。
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        bubble(img, 600, 300, 940, 340, ME_BG)
        glyphs(img, 312, ME_INK)
        rows = [(box(620, 112, 920, 128), '消息甲', 0.98),
                (box(620, 312, 920, 328), '消息乙', 0.98)]
        reader = RecordingReader(rows)
        out = reader.read(img, PANE_BG)
        texts = [o[2] for o in out]
        self.assertIn('消息甲', texts)
        self.assertIn('消息乙', texts)
        self.assertNotIn('消息甲消息乙', texts, '相隔很远的行不应合并')


class ScrollDedup(unittest.TestCase):
    """滚动去重：同一批消息在滚动后重复出现，不应被当成新消息。"""

    def test_identical_second_frame_reports_no_new_lines(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        bubble(img, 600, 200, 940, 240, ME_BG)
        glyphs(img, 212, ME_INK)
        reader = RecordingReader([])
        reader.replay([(box(620, 112, 920, 128), '一', 0.9),
                       (box(620, 212, 920, 228), '二', 0.9)])
        lines1 = reader.read(img, PANE_BG)
        new1 = reader.new_lines(lines1)
        self.assertEqual(len(new1), 2, new1)
        # 像素完全相同的第二帧 → 不该有新消息
        lines2 = reader.read(img, PANE_BG)
        self.assertEqual(reader.new_lines(lines2), [],
                         '同一帧重复读取不应产生新行')

    def test_already_seen_line_is_not_reported_again(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        reader = RecordingReader([(box(620, 112, 920, 128), '历史消息', 0.9)])
        lines = reader.read(img, PANE_BG)
        first = reader.new_lines(lines)
        self.assertEqual(len(first), 1, first)
        # 再喂一次同样的帧 → 已见过，不应报新
        lines2 = reader.read(img, PANE_BG)
        self.assertEqual(reader.new_lines(lines2), [],
                         '已见过的消息不应重复报新')

    def test_shrinking_frame_is_deduped_via_seen_list(self):
        """帧变短（向上滚动/消息区变窄）时 overlap 匹配不上，只能靠 seen 去重。

        这是 `new_lines` 里 `already_seen` 那条分支的唯一到达路径：
        如果 seen 列表被写坏（比如忘记 append），这里会把旧消息当新消息
        重报，下游就会重复分析同一条对话。
        """
        img_ab = canvas(900)
        bubble(img_ab, 600, 100, 940, 140, ME_BG)
        glyphs(img_ab, 112, ME_INK)
        bubble(img_ab, 600, 200, 940, 240, ME_BG)
        glyphs(img_ab, 212, ME_INK)
        img_a = canvas(900)
        bubble(img_a, 600, 100, 940, 140, ME_BG)
        glyphs(img_a, 112, ME_INK)

        reader = RecordingReader([])
        reader.replay([(box(620, 112, 920, 128), '甲', 0.9),
                       (box(620, 212, 920, 228), '乙', 0.9)])
        first = reader.new_lines(reader.read(img_ab, PANE_BG))
        self.assertEqual(len(first), 2, first)
        self.assertIn(('me', None, '甲', None, 'text'), first, 'seen 未记录')

        # 第二帧只剩「甲」，且位置与首帧头部不同 → overlap 匹配不上
        reader.replay([(box(620, 112, 920, 128), '甲', 0.9)])
        second = reader.new_lines(reader.read(img_a, PANE_BG))
        self.assertEqual(second, [], f'已见过的「甲」不应重报，实际 {second}')


class OcrCache(unittest.TestCase):
    """OCR 缓存：键是像素指纹，只缓存词法结果，不缓存身份/归属。

    注意：缓存逻辑写在 `Reader._ocr` 内部。若按其他用例那样替换 `_ocr`，
    缓存根本不会执行、测的就是空气。所以这里改为替换更底层的
    `Reader.ocr`（RapidOCR 实例），让 `_ocr` 的缓存分支真实跑起来。
    """

    class FakeEngine:
        """冒充 RapidOCR 引擎：记调用次数并返回预设行。"""

        def __init__(self, rows):
            self.rows = rows
            self.calls = 0

        def __call__(self, image, use_cls=False):
            self.calls += 1
            return [([list(p) for p in b], t, c) for b, t, c in self.rows], None

    def _reader_with_engine(self, rows):
        reader = ocr_mod.Reader()
        engine = self.FakeEngine(rows)
        reader.ocr = engine
        return reader, engine

    def test_cache_key_is_pixel_fingerprint(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        reader, _engine = self._reader_with_engine([(box(620, 112, 920, 128), '甲', 0.9)])
        self.assertIsNone(reader._ocr_cache, '未读过之前不应有缓存')
        reader.read(img, PANE_BG)
        self.assertIsNotNone(reader._ocr_cache)
        shape, dtype, digest = reader._ocr_cache[0]
        self.assertEqual(shape, img.shape)
        self.assertEqual(dtype, str(img.dtype))
        self.assertEqual(len(digest), 32, 'sha256 digest 应 32 字节')

    def test_identical_pixels_are_served_from_cache(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        rows = [(box(620, 112, 920, 128), '缓存', 0.9)]
        reader, engine = self._reader_with_engine(rows)
        reader.read(img, PANE_BG)
        calls_after_first = engine.calls
        self.assertGreater(calls_after_first, 0)
        # 同像素再读：命中缓存，底层识别不应被再次调用
        reader.read(img, PANE_BG)
        self.assertTrue(reader.ocr_cache_hit, '同像素第二次应命中缓存')
        self.assertEqual(engine.calls, calls_after_first,
                         '命中缓存时不应再调识别引擎')

    def test_changed_pixels_bypass_cache(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        rows = [(box(620, 112, 920, 128), '甲', 0.9)]
        reader, engine = self._reader_with_engine(rows)
        reader.read(img, PANE_BG)
        calls = engine.calls
        img[800:810, 100:110] = (0, 0, 0)  # 改一个像素
        reader.read(img, PANE_BG)
        self.assertFalse(reader.ocr_cache_hit, '像素变了就不该命中缓存')
        self.assertGreater(engine.calls, calls)


class MetricsAndEvidence(unittest.TestCase):
    """每帧必须产出度量与证据，面板与下游都依赖它们。"""

    def test_metrics_present_after_read(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        reader = RecordingReader([(box(620, 112, 920, 128), '度量', 0.9)])
        out = reader.read(img, PANE_BG)
        self.assertEqual(len(out), 1, out)
        for key in ('ocr_ms', 'post_ms', 'width', 'height'):
            self.assertIn(key, reader.last_metrics, reader.last_metrics)
        self.assertEqual(reader.last_metrics['width'], WIDTH)
        self.assertEqual(reader.last_metrics['height'], 900)

    def test_evidence_matches_line_count(self):
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        bubble(img, 600, 200, 940, 240, ME_BG)
        glyphs(img, 212, ME_INK)
        reader = RecordingReader([(box(620, 112, 920, 128), '第一条', 0.9),
                                  (box(620, 212, 920, 228), '第二条', 0.9)])
        out = reader.read(img, PANE_BG)
        self.assertEqual(len(out), 2, out)
        self.assertEqual(len(reader.last_evidence), len(out),
                         '证据条数必须与输出行数对齐')


class EmptyAndDegenerate(unittest.TestCase):
    """退化输入不得抛异常，且给出空结果而不是编造内容。"""

    def test_no_ocr_rows_yields_no_messages(self):
        reader = RecordingReader([])
        out = reader.read(canvas(900), PANE_BG)
        self.assertEqual(out, [])
        self.assertEqual(reader.last_metrics['width'], WIDTH)

    def test_small_canvas_takes_unscaled_path(self):
        img = canvas(400)  # < 900，不缩放
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        reader = RecordingReader([(box(620, 112, 920, 128), '小画布', 0.9)])
        out = reader.read(img, PANE_BG)
        self.assertEqual(len(out), 1, out)
        self.assertEqual(out[0][0], 'me')

    def test_reader_is_reusable_across_sessions(self):
        # 一个会话一个 Reader；切走再切回不该把旧消息当新消息重报。
        img = canvas(900)
        bubble(img, 600, 100, 940, 140, ME_BG)
        glyphs(img, 112, ME_INK)
        reader = RecordingReader([(box(620, 112, 920, 128), '翻页', 0.9)])
        lines = reader.read(img, PANE_BG)
        self.assertEqual(len(reader.new_lines(lines)), 1)
        # 再次读同一帧：seen 已记录，必须为空
        lines2 = reader.read(img, PANE_BG)
        self.assertEqual(reader.new_lines(lines2), [])


if __name__ == '__main__':
    unittest.main()
