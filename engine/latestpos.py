"""Read-only witness for whether the message list shows its latest message.

Real-world constraints that shaped this module (do not relax them):
  * WeChat's chat list is custom-drawn. Its accessibility subtree
    (`MMUIRenderSubWindow`) is a single opaque pane and exposes NO UIA
    ScrollPattern, so a UIA scroll percentage can never be read here.
  * The visible scrollbar is a transient overlay: it is not present in a
    captured frame, so it cannot be located in pixels either.
  * Walking the accessibility tree from the window root escapes WeChat and
    picks up other windows' scroll patterns. A naive "some container is at the
    end" test would then be satisfied by an unrelated window. The walk is
    therefore confined to WeChat's own subtree and cross-window rows are
    rejected rather than trusted.

What this module does provide is bounded geometric evidence: whether the last
visible content sits flush against the bottom of the message list. Even that is
geometry, not proof that no newer message exists, so it only ever *adds* a
witness alongside the existing guards. It never relaxes any of them.

Read-only by construction: no scrolling, clicking, focusing, typing, or sending.
"""
import threading
import time
from collections import deque

# Geometry thresholds, expressed against the list box so they survive DPI and
# window-size changes instead of being hard-coded pixel offsets.
#
# Real-window measurements showed the list box height itself moves by ~100px
# between otherwise identical frames, which makes a single percentage test
# flip its verdict for a gap of ~23px. A knife-edge threshold is unacceptable
# for a decision that gates automatic filling, so a verdict additionally
# requires an independent absolute check, and requires two agreeing consecutive
# measurements.
#
# The absolute check used to be a hard-coded 8px. Real WeChat makes that
# unreachable: the conversation pane leaves a fixed design padding of 18px
# between the last bubble and the composer, measured identically across repeated
# grabs (ratio 1.74%, which already satisfies the 2% test). A threshold that
# real geometry can never satisfy is not a safety guard, it is a permanent
# refusal that silently disables automatic filling.
#
# The replacement asks the question the guard actually exists to answer -- "could
# this blank band be hiding an undisplayed message?" -- and answers it from the
# frame itself: the band must be shorter than the smallest message block on
# screen, so it is geometrically incapable of containing one. That bound
# calibrates to DPI, window size and font scale instead of assuming a pixel
# count, and it is a genuinely separate condition from the ratio test.
_MAX_BOTTOM_GAP_RATIO = 0.02   # last content within 2% of list height...
_MIN_CONTENT_ROWS = 3          # fewer rows than this is not a usable witness
_BLANK_ROW_RUN = 6             # background rows that separate two message blocks
_FAINT_TOLERANCE = 4           # stricter than _BG_TOLERANCE, to catch soft edges
_MIN_BLOCKS_FOR_CALIBRATION = 2  # one block gives nothing to compare against
# With a single block there is no internal spacing to calibrate against, so the
# measured bound cannot be formed. A band this small cannot physically contain a
# message, so it is accepted without calibration; anything larger is refused.
_UNCALIBRATED_MAX_GAP = 2
_CONFIRMATIONS_REQUIRED = 2    # consecutive agreeing measurements
_BG_TOLERANCE = 12             # per-channel deviation that counts as "content"
_PROBE_TIMEOUT = 0.35
_CACHE_TTL = 2.0


def _unverified(reason, **extra):
    result = {
        'available': False,
        'verified': False,
        'reason': reason,
        'source': 'list_bottom_geometry',
        'read_only': True,
    }
    result.update(extra)
    return result


def frame_matches_window(frame_shape, rect):
    """Reject frames whose size disagrees with the window rectangle.

    A capture that came back at a different size than the live window cannot
    be trusted for absolute geometry, so no verdict is produced from it.
    """
    if not frame_shape or not rect:
        return False, '没有可用的画面尺寸'
    height, width = frame_shape[0], frame_shape[1]
    left, top, right, bottom = rect
    win_w, win_h = int(right) - int(left), int(bottom) - int(top)
    if win_w <= 0 or win_h <= 0:
        return False, '窗口尺寸无效'
    if abs(width - win_w) > max(8, int(win_w * 0.02)):
        return False, '画面宽度与窗口不一致，本帧不作为证据'
    if abs(height - win_h) > max(8, int(win_h * 0.02)):
        return False, '画面高度与窗口不一致，本帧不作为证据'
    return True, ''


def _content_blocks(content):
    """Row spans of message blocks, split on runs of blank rows.

    Returns a list of (start_row, end_row) inclusive. A message bubble is far
    taller than the gap between bubbles, so splitting on a run of background
    rows separates blocks without depending on colour or bubble geometry.
    """
    mask = content.any(axis=1)
    blocks = []
    start = None
    blank = 0
    for index, filled in enumerate(mask):
        if filled:
            if start is None:
                start = index
            blank = 0
            continue
        if start is None:
            continue
        blank += 1
        if blank >= _BLANK_ROW_RUN:
            blocks.append((start, index - blank))
            start = None
            blank = 0
    if start is not None:
        blocks.append((start, len(mask) - 1))
    return blocks


def evaluate_geometry(gray, list_box, background=30):
    """Decide from a grayscale list crop whether the last row is the newest.

    `list_box` is (x0, y0, x1, y1) in the crop's own coordinates. Returns a
    witness dict; never raises.
    """
    try:
        import numpy as np
    except Exception:
        return _unverified('缺少图像计算库，无法核对最新位置')
    if gray is None or getattr(gray, 'ndim', 0) != 2:
        return _unverified('没有可用的消息区画面')
    x0, y0, x1, y1 = (int(v) for v in list_box)
    h, w = gray.shape[:2]
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(w, x1), min(h, y1)
    if x1 - x0 < 40 or y1 - y0 < 40:
        return _unverified('消息区太小，无法核对最新位置')
    crop = gray[y0:y1, x0:x1]
    # `crop` is (rows, cols) grayscale: there is no channel axis to reduce, so
    # compare per pixel and reduce only the column axis when summarising rows.
    deviation = np.abs(crop.astype(int) - int(background))
    content = deviation > _BG_TOLERANCE
    rows = np.where(content.any(axis=1))[0]
    if rows.size < _MIN_CONTENT_ROWS:
        return _unverified('消息区内容过少，无法核对最新位置')
    first_row, last_row = int(rows[0]), int(rows[-1])
    list_height = y1 - y0
    gap = (y1 - y0) - 1 - last_row
    ratio = gap / float(list_height)

    # Independent absolute check: the blank band under the last bubble must be
    # pure background, and too short to hold a message. Both are measured from
    # this frame, so the verdict adapts to DPI and window size.
    blocks = _content_blocks(content)
    heights = [b - a + 1 for a, b in blocks]
    smallest_block = min(heights) if heights else 0
    band = crop[last_row + 1:, :]
    band_has_faint_content = bool(
        band.size and (np.abs(band.astype(int) - int(background)) > _FAINT_TOLERANCE).any())
    # gap == 0 means the last row is flush against the list bottom, which is the
    # strongest "already at the bottom" evidence there is; only a gap that is
    # actually taller than the smallest message could be concealing one.
    calibrated = len(blocks) >= _MIN_BLOCKS_FOR_CALIBRATION and smallest_block > 0
    gap_small_enough = gap < smallest_block if calibrated else gap <= _UNCALIBRATED_MAX_GAP
    gap_can_hide_message = not gap_small_enough or band_has_faint_content

    common = {
        'list_box': [x0, y0, x1, y1],
        'content_first_row': y0 + first_row,
        'content_last_row': y0 + last_row,
        'bottom_gap_pixels': int(gap),
        'bottom_gap_ratio': round(ratio, 4),
        'message_blocks': len(blocks),
        'smallest_block_pixels': int(smallest_block),
        'bottom_band_has_faint_content': band_has_faint_content,
        'gap_threshold_source': ('smallest_message_block_in_this_frame' if calibrated
                                 else 'uncalibrated_strict_max'),
    }
    if ratio <= _MAX_BOTTOM_GAP_RATIO and not gap_can_hide_message:
        return {
            'available': True,
            'verified': True,
            'reason': '最后一条可见内容紧贴消息列表底边，且空白不足以容纳一条未显示的消息',
            'source': 'list_bottom_geometry',
            'read_only': True,
            'evidence_kind': 'geometry_only',
            'caveat': '这是几何证据，不等于证明没有更新消息；其它保护仍然全部生效',
            **common,
        }
    return _unverified(
        '最后一条内容与列表底边之间的空白可能容纳未显示的新消息，请手动填入',
        evidence_kind='geometry_only', **common)


# ---- WeChat subtree confinement -------------------------------------------------

def find_render_subtree(root, max_depth=12):
    """Locate WeChat's own render pane, refusing to leave its subtree.

    Everything the caller passes upward comes from below this node only, so an
    unrelated window's scroll pattern can never be mistaken for WeChat's.
    """
    stack = deque([(root, 0)])
    while stack:
        item, depth = stack.popleft()
        if item is None:
            continue
        try:
            name = item.Name or ''
        except Exception:
            name = ''
        if name == 'MMUIRenderSubWindow':
            return item
        if depth < max_depth:
            try:
                stack.extend((child, depth + 1) for child in item.GetChildren()[:40])
            except Exception:
                continue
    return None


def scroll_rows_within(node, limit=250, budget=1.0):
    """Collect scroll-pattern rows strictly beneath `node`."""
    rows = []
    if node is None:
        return rows
    stack = deque([(node, 0)])
    started = time.monotonic()
    visited = 0
    while stack and visited < limit and time.monotonic() - started < budget:
        item, depth = stack.popleft()
        if item is None:
            continue
        visited += 1
        row = {'type': item.ControlTypeName, 'depth': depth}
        try:
            pattern = item.GetScrollPattern()
            if pattern is not None:
                row['vertical_scroll_percent'] = pattern.VerticalScrollPercent
                try:
                    row['vertical_view_size'] = pattern.VerticalViewSize
                except Exception:
                    row['vertical_view_size'] = None
        except Exception:
            pass
        rows.append(row)
        if depth < 16:
            try:
                stack.extend((child, depth + 1) for child in item.GetChildren()[:60])
            except Exception:
                continue
    return rows


def evaluate_scroll_rows(rows):
    """Rule kept for completeness; WeChat yields no rows in practice."""
    candidates = [r for r in (rows or [])
                  if isinstance(r, dict) and r.get('vertical_scroll_percent') is not None]
    if not candidates:
        return _unverified('微信未暴露可读的滚动位置，改用列表底部几何核对')
    percents = []
    for row in candidates:
        try:
            percents.append(float(row['vertical_scroll_percent']))
        except (TypeError, ValueError):
            continue
    if not percents or min(percents) < 99.5:
        return _unverified('消息列表不在末尾，可能还有未显示的新消息，请手动填入',
                           vertical_scroll_percent=percents)
    return {
        'available': True, 'verified': True,
        'reason': '消息列表滚动位置处于末尾，可见范围即最新范围',
        'source': 'list_bottom_geometry', 'read_only': True,
        'evidence_kind': 'scroll_pattern',
        'vertical_scroll_percent': percents,
    }


# ---- cached live probe -----------------------------------------------------------

_cache = {}
_confirm = {}
_inflight = {}
_lock = threading.Lock()


def cached(hwnd):
    with _lock:
        entry = _cache.get(int(hwnd))
    if not entry:
        return None
    stamp, value = entry
    age = time.monotonic() - stamp
    if age >= _CACHE_TTL:
        return None
    result = dict(value)
    result['witness_age_seconds'] = round(age, 3)
    return result


def probe(hwnd, frame=None, rect=None, list_box=None, background=30, timeout=_PROBE_TIMEOUT):
    """Produce a witness. Read-only.

    Geometry from a supplied frame is preferred. A UIA scroll witness is only
    ever read from WeChat's own subtree, never from the window root.
    """
    key = int(hwnd)
    if frame is not None:
        if list_box is None:
            return _unverified('未提供消息列表区域，无法核对最新位置')
        ok, why = frame_matches_window(getattr(frame, 'shape', None), rect)
        if not ok:
            return _unverified(why)
        try:
            import cv2
            x0, y0, x1, y1 = (int(v) for v in list_box)
            if x1 - x0 < 40 or y1 - y0 < 40:
                return _unverified('消息列表区域太小，无法核对最新位置')
            patch = frame[y0:y1, x0:x1]
            if patch.ndim != 3 or patch.shape[0] < 40 or patch.shape[1] < 40:
                return _unverified('消息列表画面不完整，无法核对最新位置')
            gray = cv2.cvtColor(patch, cv2.COLOR_RGB2GRAY)
        except Exception:
            return _unverified('消息区画面无法转换，无法核对最新位置')
        if getattr(gray, 'ndim', 0) != 2:
            return _unverified('消息区画面无法转换，无法核对最新位置')
        result = evaluate_geometry(gray, (0, 0, gray.shape[1], gray.shape[0]),
                                   background=background)
        # A single measurement is not enough: the list box can shift by ~100px
        # between frames. Require consecutive agreeing measurements before
        # allowing a fill. Any disagreement resets the run.
        if result.get('verified'):
            previous = _confirm.get(key)
            agree = (previous is not None
                     and previous.get('bottom_gap_pixels') == result.get('bottom_gap_pixels')
                     and previous.get('list_box') == result.get('list_box'))
            if not agree:
                _confirm[key] = {'bottom_gap_pixels': result.get('bottom_gap_pixels'),
                                 'list_box': result.get('list_box')}
                result = dict(result)
                result.update(verified=False, available=False,
                              reason='需要再次核对消息列表位置，稍后重试',
                              confirmations=1)
            else:
                _confirm[key] = dict(_confirm.get(key) or {}, confirmations=2)
                result = dict(result)
                result['confirmations'] = 2
        else:
            _confirm.pop(key, None)
        if len(_confirm) > 32:
            # 窗口句柄反复重建时确认表缓慢增长：只保留最近 32 个条目。
            for stale in list(_confirm)[:-32]:
                _confirm.pop(stale, None)
        with _lock:
            _cache[key] = (time.monotonic(), result)
        return result

    # 无帧路径：先查缓存，已有探测在跑就复用同一个结果，
    # 绝不让每次调用都新建一个带 COM 初始化的 UIA 线程（会堆积到每秒上百个）。
    with _lock:
        entry = _cache.get(key)
    if entry:
        stamp, value = entry
        if time.monotonic() - stamp < _CACHE_TTL:
            result = dict(value)
            result['witness_age_seconds'] = round(time.monotonic() - stamp, 3)
            return result
    with _lock:
        state = _inflight.get(key)
        if state is None:
            state = {'event': threading.Event(), 'result': None}
            _inflight[key] = state
            started_by_me = True
        else:
            started_by_me = False
    if started_by_me:
        def worker():
            try:
                import uiautomation as auto
                with auto.UIAutomationInitializerInThread():
                    root = auto.ControlFromHandle(key)
                    node = find_render_subtree(root)
                    rows = scroll_rows_within(node)
                    result = evaluate_scroll_rows(rows)
                    result['subtree_found'] = node is not None
                    result['rows_visited'] = len(rows)
            except Exception as exc:
                result = _unverified('无法读取窗口结构：%s' % type(exc).__name__)
            state['result'] = result
            with _lock:
                _cache[key] = (time.monotonic(), result)
                if _inflight.get(key) is state:
                    _inflight.pop(key, None)
            state['event'].set()
        try:
            threading.Thread(target=worker, daemon=True).start()
        except Exception as exc:
            # 线程起不来时清掉 in-flight 状态，否则该 key 从此每次调用都空等超时。
            with _lock:
                if _inflight.get(key) is state:
                    _inflight.pop(key, None)
            state['event'].set()
            raise
    state['event'].wait(timeout=timeout)
    result = state['result']
    if result is None:
        return _unverified('滚动位置读取超时，无法核对是否位于最新位置')
    return dict(result)
