# 参与开发

感谢你有兴趣参与军师。本文说明本地开发环境、提交前检查和 PR 约定。

> 应用的目标是**看清上下文、说像你的话、把选择权留给你**。所有改动都必须守住
> 一条底线：**军师不发送任何消息**。任何形式的自动发送、绕过用户确认、
> 或让模型指令越过输入保护的改动都不会被合并。

---

## 1. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Windows | 10 / 11 | 依赖 Windows Graphics Capture、DPAPI、`uiautomation` |
| Python | **3.12** | 见下方「为什么必须是 3.12」 |
| Node.js | ≥ 20 | 仅用于面板排版/交互检查，运行时不依赖 |
| Ollama | 可选 | 媒体理解需要，`ollama pull qwen3-vl:2b` |

### 为什么必须是 Python 3.12

`requirements.txt` 里固定了 `rapidocr-onnxruntime==1.4.4`，它声明
`Requires-Python >=3.6,<3.13`。在 3.13 上 pip 会**在依赖解析阶段**就失败：

```
ERROR: Could not find a version that satisfies the requirement
       rapidocr-onnxruntime==1.4.4
```

这条报错很容易被误读成「包被下架了」，实际只是 Python 版本不对。
CI 里有一个「断言 Python 版本」步骤专门把这个隐式前提变成显式检查。
将来要升到 3.13，必须同步替换这组依赖（OCR / OpenCV / onnxruntime），
那不是一次顺手升级，需要单独评估。

---

## 2. 起步

```powershell
git clone https://github.com/1314520-lgj/wechat-junshi.git
cd wechat-junshi

:: 运行时依赖
pip install -r requirements.txt

:: 开发工具链（ruff / pip-audit / pre-commit / Pillow）
pip install -r requirements-dev.txt

:: 启用提交前钩子（只需一次）
pre-commit install

:: 从源码运行
python -X utf8 launcher.py
```

---

## 3. 提交前检查

CI 和本地跑**同一套策略**，避免「本地过、CI 挂」这种最难排查的情况。
提交前请本地跑一遍：

```powershell
pre-commit run --all-files      # 首次可能自动修正文件，再跑一次应全绿
ruff check .                    # 规则集与豁免都在 pyproject.toml
python -m unittest discover -s tests -p "test_*.py"
```

面板相关改动还需要：

```powershell
npm install
npx playwright install chromium
npm run test:layout
npm run test:actions
```

具体规则与豁免理由见下方「工程约定」。

### 关于那两个未启用的钩子

`.pre-commit-config.yaml` 里**刻意没有**启用 `check-case-conflict` 与
`mixed-line-ending`。这两个钩子的可执行文件在部分 Windows 环境会被
Application Control 策略拦截（`[WinError 4551]` / `Permission denied`）。
永远红的钩子会被习惯性 `--no-verify` 绕过，进而连带废掉整套检查，
所以宁可不启用。它们覆盖的能力用更可靠的方式补上：

- 混用换行符 → `.gitattributes` 的 `* text=auto`，入库时统一为 LF
- 大小写冲突 → 人工注意；在大小写敏感的 CI（ubuntu）上可以补跑

在没这条策略的环境（Linux/macOS、其他 Windows）可以把它们加回来。

---

## 4. 工程约定

### Python

- **风格**：代码库刻意采用紧凑单行风格（`if x: return`），因此
  `E501`（行长）/ `E701` / `E702` / `E731` / `E741` 是**有意忽略**的。
  不要为了「符合 PEP8」把它们改回去。
- **中文全角标点**：`RUF001-003` 是**有意忽略**的，源码注释与 UI 文案都是中文。
- **导入顺序**：多处需要先 `sys.path.insert` 再导入，故 `E402` 忽略。
- **修改规则集**：`pyproject.toml` 是静态检查的**单一事实来源**。
  新增豁免必须在 `ignore` 里写清理由（现有条目都是逐条复核过的），
  并在 PR 描述里说明为什么这是误报而不是真问题。
- **安全规则**：已启用 `S`（等价 Bandit）。`S603` / `S606` / `S310` /
  `S110` / `S112` / `S101` 的豁免都附了实测理由。改动这些豁免前请先读注释。
- **`pyproject.toml` 只放 `[tool.*]`**，不要定义 `[project]` /
  `[build-system]`，否则 pip/PyInstaller 会把仓库当成可安装包。

### JavaScript（面板）

- `lib/panel.js` 是**独立完整**的 UI：CSS 以模板字符串注入，DOM 由
  `document.body.innerHTML` 渲染，没有构建步骤、没有外部资源。
- 引擎**每个请求都从磁盘重读** `lib/panel.js`，不缓存；浏览器刷新即可看到改动。
- 排版改动请同时验证 **浅色 / 深色** 与 **广播宽屏 / 窄窗** 至少两组尺寸。

### 依赖

- `requirements.txt`：运行时依赖。OCR 与 Windows 捕获行为敏感，**保持固定版本**。
- `requirements-dev.txt`：静态检查与离线测试工具链，固定版本
  （漏洞库与判定逻辑的变化应该是可预期的动作，而不是某天早上 CI 突然变红）。
- 新增依赖请在 PR 里说明用途，并确认 `pip-audit` 无已知漏洞。

### 安全红线

以下内容**不得**提交到公开仓库：

- `private-data-backup`、`dev-data`、`test-data` 目录
- Harness 会话日志
- 任何 `*.dpapi`、`*.sqlite3` 数据文件
- 实例令牌（`DSH_JUNSHI_TOKEN`）—— 不要写进文档、日志或插件上下文

---

## 5. 测试

| 命令 | 覆盖范围 |
| --- | --- |
| `python -m unittest discover -s tests -p "test_*.py"` | 引擎纯逻辑：解析、归属、事实核验、路由表、OCR 回放 |
| `npm run test:layout` | 面板排版：窗口尺寸、连续缩放、草稿保留、长设置滚动 |
| `npm run test:actions` | 面板交互：抽屉、建议失效、复制/填入失败、证据范围 |

`tests/` 下的用例使用**虚构会话、合成画布与模拟服务**，不发起网络请求，
不需要微信、真实截图或本地模型。`tests/test_ocr_replay.py` 会替换掉 OCR
引擎、只跑下游归属/合并/去重逻辑。

CI 会检查**没有用例被跳过**：若因 Python 版本漂移导致 OCR 依赖装不上，
测试模块会整体 skip，套件虽然绿但覆盖悄悄消失。所以不要用
`@unittest.skip` 图省事。

新增逻辑请配套用例。纯函数（解析、判定、排序）优先——它们最能锁住回归，
且不需要任何本机资源。

---

## 6. 提交与 PR

### Commit message

用 Conventional Commits 前缀，正文用中文，说明**为什么**而不只是**改了什么**：

```
fix: 修正 _parse_candidates 对空候选的越界访问

原实现假设模型一定返回至少一个候选，实际在超时降级路径上会拿到空列表，
导致 IndexError 冒泡到分析主流程、整次分析失败。改为提前返回空结果，
由调用方按「无候选」处理。
```

常用前缀：`feat` / `fix` / `perf` / `refactor` / `test` / `docs` / `chore` / `ci`。

### PR 前自查

- [ ] `pre-commit run --all-files` 全绿
- [ ] `ruff check .` 通过
- [ ] Python 单元测试全绿且**无跳过**
- [ ] 涉及面板改动时，两组尺寸 × 浅深色主题均验证过
- [ ] 没有引入新的静默 `except` 分支（要么记录、要么注释说明为何可忽略）
- [ ] 没有触碰「不发送消息」这条底线

### 不要做的事

- 不要用 `--no-verify` 绕过钩子。钩子报错说明有真实问题，或是配置本身要改，
  两种情况都应该解决而不是跳过。
- 不要盲目接受自动格式化产生的全库改动。如果某个钩子改了几十个文件，
  先确认每处都是纯空白/纯格式变化，再决定是否接受——混在功能改动里会淹没真正的 diff。

---

## 7. 发布与升级

桌面安装包内置 Python 3.12 运行时与全部依赖，不随仓库分发；仓库是完整应用源码（开发包）。

在已有安装上升级：

1. 在军师设置中退出程序
2. 备份安装目录（默认 `%LOCALAPPDATA%\Programs\Junshi`）
3. 覆盖对应源码
4. 启动 `launcher.py`

用户数据在**独立目录**（`%LOCALAPPDATA%\Junshi\`），部署源码不会触碰它。

---

## 8. 许可证

提交即表示你同意以 [MIT](LICENSE) 许可发布你的贡献。
第三方组件的许可证保留在 `licenses/` 与各 `dist-info/licenses` 目录。
