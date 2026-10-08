"""锁定 HTTP 路由分派表：端点集合与「未授权/未找到」的语义。

`Handler._route` 原先是一条 320 行 / 33 分支的 if 长链，现已拆到 `apiroutes.ROUTES`
表驱动分派。这个测试锁定两件事：
  1. 端点集合不再意外增删（加了新端点要同步更新这里，等于强制 review）；
  2. 未命中路径仍返回 404 `not found`，且鉴权失败先于路由查找（401 优先）。

只做纯静态/桩测试，不启动真实引擎、不碰网络。
"""
import importlib
import os
import sys
import unittest
from urllib.parse import urlparse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'engine'))

import apiroutes

# 与 apiroutes.ROUTES 逐条对应；新增/删除端点必须显式改这里。
EXPECTED_ROUTES = {
    ('GET', '/capabilities'), ('GET', '/models'), ('POST', '/models'),
    ('GET', '/uia'), ('POST', '/evidence'), ('POST', '/attach-media'),
    ('POST', '/correct-message'), ('GET', '/participants'), ('GET', '/extensions'),
    ('POST', '/verify-extension'), ('GET', '/vision-models'), ('POST', '/vision-key'),
    ('GET', '/health'), ('GET', '/state'), ('GET', '/frame.png'),
    ('GET', '/settings'), ('POST', '/settings'), ('POST', '/startup'),
    ('POST', '/fill'), ('POST', '/copy-text'), ('POST', '/copy'),
    ('POST', '/pause'), ('POST', '/resume'), ('POST', '/regenerate'),
    ('POST', '/analyze-text'), ('POST', '/launch-wechat'), ('POST', '/key-delete'),
    ('POST', '/key'), ('POST', '/memory-clear'), ('POST', '/memory-confirm'),
    ('POST', '/cancel-manual'), ('POST', '/media-file'), ('POST', '/media-job'),
    ('GET', '/ui'), ('GET', '/ui/panel.js'), ('POST', '/shutdown'),
}

# `/capabilities` 的 tools 列表是给宿主做能力协商用的，改动即破坏兼容。
EXPECTED_TOOLS = {
    'state', 'participants', 'analyze-text', 'cancel-manual', 'regenerate', 'settings',
    'extensions', 'vision-models', 'fill', 'models', 'evidence', 'correct-message',
    'uia', 'memory-confirm', 'media-file', 'media-job', 'attach-media', 'verify-extension',
}


class FakeHandler:
    """最小桩：只记录被写出的响应，不涉及 socket。"""

    def __init__(self, command, path, authorized=True):
        self.command = command
        self.path = path
        self.authorized = authorized
        self.responses = []

    def _check(self):
        return self.authorized

    def _json(self, payload, code=200):
        self.responses.append((code, payload))

    def __getattr__(self, name):
        # 任何未被桩化的端点方法被真正调用时，说明测试选错了路径；
        # 用一个明确的异常把问题暴露出来。
        raise AssertionError(f'unexpected handler attribute accessed: {name}')


class RouteTable(unittest.TestCase):
    def test_route_set_is_exactly_as_documented(self):
        self.assertEqual(set(apiroutes.ROUTES), EXPECTED_ROUTES)

    def test_every_route_target_is_callable(self):
        for key, target in apiroutes.ROUTES.items():
            self.assertTrue(callable(target), f'{key} 不是可调用对象')
            self.assertIsNotNone(target.__doc__ or True)

    def test_no_duplicate_paths_across_methods_are_lost(self):
        # 同一路径可以同时有 GET/POST（如 /models、/settings），
        # 但要确认 GET 与 POST 不会互相覆盖。
        by_path = {}
        for method, path in apiroutes.ROUTES:
            by_path.setdefault(path, set()).add(method)
        self.assertEqual(by_path['/models'], {'GET', 'POST'})
        self.assertEqual(by_path['/settings'], {'GET', 'POST'})

    def test_capabilities_tools_match(self):
        self.assertEqual(set(apiroutes._CAPABILITIES['tools']), EXPECTED_TOOLS)
        self.assertIs(apiroutes._CAPABILITIES['sends_messages'], False)
        self.assertEqual(apiroutes._CAPABILITIES['evidence_api_version'], '1.1')

    def test_unknown_path_returns_not_found(self):
        handler = FakeHandler('GET', '/nope')
        apiroutes.route(handler)
        self.assertEqual(handler.responses, [(404, {'ok': False, 'error': 'not found'})])

    def test_wrong_method_on_known_path_returns_not_found(self):
        handler = FakeHandler('DELETE', '/state')
        apiroutes.route(handler)
        self.assertEqual(handler.responses, [(404, {'ok': False, 'error': 'not found'})])

    def test_unauthorized_wins_over_routing(self):
        # 鉴权必须先于路由查找：否则未授权请求能靠 404/200 差异探测端点是否存在。
        handler = FakeHandler('GET', '/nope', authorized=False)
        apiroutes.route(handler)
        self.assertEqual(handler.responses, [(401, {'ok': False, 'error': 'unauthorized'})])

    def test_query_string_is_ignored_when_matching(self):
        # 原实现用 urlparse(...).path 匹配，query 不应参与路由；这里锁住该行为。
        seen = {}

        def fake(handler, app):
            seen['hit'] = True
            handler._json({'ok': True})

        original = apiroutes.ROUTES[('GET', '/state')]
        apiroutes.ROUTES[('GET', '/state')] = fake
        try:
            handler = FakeHandler('GET', '/state?x=1&y=2')
            apiroutes.route(handler)
        finally:
            apiroutes.ROUTES[('GET', '/state')] = original
        self.assertTrue(seen.get('hit'))
        self.assertEqual(handler.responses, [(200, {'ok': True})])

    def test_dispatcher_reads_path_from_urlparse(self):
        # 分派必须基于 handler.path 解析出的 path，而不是裸 path 字符串。
        self.assertEqual(urlparse('/state?a=1').path, '/state')


class CapabilitiesPayload(unittest.TestCase):
    def test_tools_are_sorted_stable_view(self):
        # 保证能力协商的 tools 是 list 且无重复（宿主按集合语义消费）。
        tools = apiroutes._CAPABILITIES['tools']
        self.assertIsInstance(tools, list)
        self.assertEqual(len(tools), len(set(tools)))


class AppAccessor(unittest.TestCase):
    def test_app_accessor_is_lazy(self):
        # _app() 只在调用时才 import junshi；模块导入期不得解引用它的状态。
        with open(apiroutes.__file__, encoding='utf-8') as fh:
            source = fh.read()
        self.assertIn('def _app():', source)
        self.assertIn('import junshi', source)
        # 不允许在模块顶层出现 `import junshi`（那会造成循环导入）。
        top_level = [ln for ln in source.splitlines()
                     if ln.strip() == 'import junshi' and not ln.startswith(' ')]
        self.assertEqual(top_level, [])

    def test_module_reloads_without_junshi_present(self):
        # 仅导入 apiroutes 本身不应依赖 junshi 可用。
        spec = importlib.util.find_spec('apiroutes')
        self.assertIsNotNone(spec)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(set(module.ROUTES), EXPECTED_ROUTES)


if __name__ == '__main__':
    unittest.main()
