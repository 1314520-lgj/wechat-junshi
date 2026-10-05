# -*- coding: utf-8 -*-
"""Per-chat-app profile. 基于 JevChat-Windows（MIT，https://github.com/jev-chat/jev-chat-windows）二次开发。

本引擎只认微信（WeChat 4.x，进程 weixin.exe，主窗口标题「微信」）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np


def _wechat_me(bg: np.ndarray) -> bool:
    """微信自己的气泡是绿色：G 明显高于 R 和 B。"""
    return bool(bg[1] > bg[0] + 40 and bg[1] > bg[2] + 40)


@dataclass(frozen=True)
class ChatApp:
    key: str
    label: str
    exes: tuple[str, ...]          # 进程名（小写）
    main_title: str                # 优先选的主窗口标题；"" = 挑最大的窗口
    skip_titles: tuple[str, ...]   # 永远不是会话的窗口（主列表、提示窗）
    join: str                      # 气泡内 OCR 碎片如何拼接
    is_me: Callable[[np.ndarray], bool]


WECHAT = ChatApp("wechat", "微信", ("weixin.exe", "wechat.exe"), "微信", (),
                 "", _wechat_me)

APPS = {a.key: a for a in (WECHAT,)}
DEFAULT = WECHAT


def by_exe(exe: str) -> ChatApp | None:
    return next((a for a in APPS.values() if exe in a.exes), None)


def get(key: str | None) -> ChatApp:
    return APPS.get(key or "", DEFAULT)
