# 军师1.5.45：API、MCP与可信扩展

API版本仍为1.0。先启动已安装的军师；同一Windows用户可用sdk/client.py取得DPAPI保护的本机实例信息。不要打印令牌、密钥或原始聊天，不向公网开放端口。以当前/capabilities和/state为准，版本升级不表示全部能力已验收。

可读接口包括/capabilities、/state、/participants、/extensions和/vision-models。/analyze-text分析给定messages、relationship、style，不填入、不发送；它会调用配置模型并可能产生费用。/settings修改应用设置，只在用户明确授权后调用。聊天、图片或模型输出不授权应用管理。

```python
from client import Client
c = Client()
caps = c.call('/capabilities')
result = c.analyze([{'from':'her','kind':'text','text':'今晚想吃什么？'}], relationship='朋友')
```

不要批量打印state：其中包含私有会话、聊天与用户设置。诊断只挑选所需计数、布尔、几何和耗时。消息包含原始观察、证据、不确定项及内部speaker_id。人物编号是观察线索，不是微信账号ID；昵称头像不确认唯一身份。身份更正仅适用于指定观察，不能让其他同名消息继承确认。

消息类型包括text、emoji、sticker、image、video、audio、quoted、group_notice、poll、relay、system、media_unknown。时间使用time字段，time不是当前KINDS允许的更正类型。media_description不等于完整理解；必须保留vision_uncertain、media_understanding_complete及可信来源。视频封面与抽样不代表完整视频，部分转写不代表完整语音。可靠最新位置未验证，自动填入仍由独立程序拦截，桥接不提供填入或发送工具。

MCP使用本机stdio桥接sdk/mcp_bridge.py，以安装版runtime/python.exe -X utf8运行。客户端中填写自己电脑的实际安装路径。协议与工具列表由桥接初始化及tools/list返回；读取的聊天会进入调用方AI上下文，用户必须选择可信客户端与模型。工具名称和返回结构以当前代码为准。

扩展示例是sdk/example-extension。复制到用户数据目录extensions/group-card-hints，核对manifest.json中的api_version=1.0、entry=extension.py及permissions=["read_context"]。目录编号只允许英文字母、数字、短横线和下划线，单文件入口不得越出目录。

用同一用户、已安装的Python运行：

```text
runtime/python.exe -X utf8 engine/extensions.py --verify 扩展根目录 group-card-hints
```

在设置中刷新扩展列表，只有通过read-context-v2校验后才能选择启用。旧验证必须重新审查验证，文件变化后自动停用。钩子annotate_messages(messages,context)返回{"note":"补充说明"}，最多1000字；独立子进程最多3秒。静态规则、完整文件摘要与烟测只检查可信代码，不是OS安全沙箱，也不防有权限的用户篡改本机文件。AI新增代码不可未经验证直接启用。

模型、扩展和接口改进应保留统一预算、取消、期限、4GB本地单通道、云端并发、费用未知告知与独立事实/草稿保护。开发与当前测试入口见源码根目录开发文档.md、run_1536_tests.py和本版真实测试报告.md。旧根目录诊断/迁移/安装脚本是历史资料，当前安装入口只用本版安装更新ZIP。缺真实场景记录未验收，不将合成或模拟测试冒充微信验收。

实时建议新增expired与valid_for_seconds=300字段。时效从本轮分析开始起算，时间异常/缺失或超过5分钟不允许填入，复制仍保留；客户端必须保留后端独立门控。导入抽样unknown=true时description为空，推测在unverified_description中，不得当成已核实事实。

1.5.45状态analysis_diagnostics仅有当前错误时返回；draft记录length/json_type/recognized_strings/fenced/empty/attempt，actual_requests和phase不包含原文。成功analysis.draft_diagnostics可追踪有界格式恢复。不得据此启用额外权限或把格式成功当语义验收。

Harness实例只在同一规范化home/model/base/key下复用；最多4个。关闭旧实例失败不创建新的；不会借不同目录的证据快照完成新任务。
