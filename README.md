# 自动化测试 Agent

根据设备知识和技能描述生成 JSON 测试意图，经校验转换为 YAML/DSL 计划。人工审核通过后，YamlRunner 调用本地技能执行设备测试；失败时，诊断 Agent 根据证据选择只读检查工具。WebSocket 回传执行和诊断事件，LLM 生成 Markdown 报告。

## 启动

Python 3.11+。运行依赖见 `requirements-runtime.txt`；`requirements.txt` 引用同一份运行依赖。

首次启动先复制示例配置：Windows PowerShell 执行 `Copy-Item config.example.yaml config.yaml`；Linux/macOS 执行 `cp config.example.yaml config.yaml`。然后填写本机模型服务配置。`config.yaml` 仅保存在本机，不提交。

此上传快照包含通用技能与虚拟设备技能。真实设备适配器、原始设备知识、历史计划、报告和本地数据库未包含在内。代码来源说明见 [docs/PROVENANCE.md](docs/PROVENANCE.md)。

Windows PowerShell：

```powershell
py -3.11 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements-runtime.txt
.\.venv-win\Scripts\python.exe main.py
```

Linux/macOS：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-runtime.txt
.venv/bin/python main.py
```

配置 `config.yaml` 中的 OpenAI-compatible 模型服务和技能组，然后访问 <http://localhost:8080>。HTTP 和 WebSocket 端口均可在配置中修改；前端自动读取 WebSocket 端口。

开发时也可用启动参数指定端口和独立任务数据库，例如 `python main.py --http-port 8082 --ws-port 8083 --database .local/diagnostic-preview.sqlite3`，以便同时保留原服务。

```yaml
llm:
  base_url: "http://localhost:8000/v1"
  model: "your-model"
  api_key: "EMPTY"
workflow:
  database_path: "data/workflow.sqlite3"
```

模型端只需支持 Chat Completions；意图 Schema 被注入 prompt，Pydantic 在本地执行严格校验，不要求模型服务支持原生 JSON Schema 或 function calling。

## 使用流程

1. 上传 `.md` 知识文档，或加载已有计划/`.zip` 计划包。知识文档中的“技能组：名称”可切换 `skills/<名称>`。
2. 生成计划：LLM JSON 意图通过 Pydantic 字段、类型、范围和嵌套结构校验，再由 IntentConverter 校验技能白名单并转为 DSL；失败最多修正一次。
3. 在计划编辑器修改步骤、填写运行参数，点击“通过审核”或“驳回”。审核保存计划版本、SHA-256 摘要、时间、备注和决定。
4. 审核通过后点击“开始测试”。修改步骤或运行参数会使原审核失效，必须审核新版本。
5. 查看实时日志和模块进度。测试失败后自动进入只读诊断，展示检查过程、证据和待人工验证的结论，然后生成报告。报告生成失败时可单独重试，设备动作和已完成的诊断不会重跑。
6. 刷新页面或重启服务后，从“任务记录”找回任务。加载计划库中的计划会创建新的待审核任务。

## LangGraph 生命周期

```text
prepare -> review (interrupt)
              | approved
              v
        execution_gate (interrupt) -> execute -- no failures --> report -> END
                                       |
                                    failures
                                       v
                               diagnostic_prepare
                                       v
                               diagnostic_decide <--- diagnostic_tool
                                       |                    ^
                                       +--- call_tool -------+
                                       |
                                   conclude/limit
                                       v
                               diagnostic_finish -> report -> END

review -- rejected --> END
```

图状态和审核历史由 `SqliteSaver` 保存，任务索引及当前任务指针保存在同一个 SQLite 数据库。路径相对于项目根目录；`data/` 不进入版本控制。

- 审核与开始执行是两个独立的持久化等待点。
- 所有计划入口，包括编辑、保存、导入和加载，都会校验 DSL 和技能名称。
- `task_id` 和 `revision` 防止旧页面审核/启动错误版本；执行期间拒绝重复启动、切换任务和重置。
- 报告节点失败保留执行结果，重启后仍可单独重试报告。
- 诊断中断保留每轮检查点，点击“继续诊断”只恢复诊断节点，不重新执行设备测试。
- 恢复粒度为生命周期阶段，尚未实现 YamlRunner 内部步骤/循环的断点续跑。
- 执行中异常退出会标为 `execution_uncertain`；不会自动重放硬件节点。应先检查设备状态，再创建并审核新任务。
- 当前服务串行运行一个设备任务；任务记录不等于多用户鉴权或设备资源隔离。

## 失败诊断 Agent

`FailureDiagnostician` 使用独立 Chat 实例，按“观察证据 -> 模型决策 -> 白名单工具 -> 新证据”的循环诊断。决策使用 Pydantic 校验的 JSON 协议，工具由 LangChain `StructuredTool` 定义输入 Schema 并校验参数，循环和证据由 LangGraph 持久化。

这里不依赖模型端原生 function calling；OpenAI-compatible Chat Completions 服务也可以使用。普通设备 skill 注册表不会自动成为诊断工具列表。

| 工具 | 数据来源与边界 |
|---|---|
| `read_failure_details` | 按 failure_id 读取已保存的失败步骤、模块、技能及错误 |
| `read_execution_log` | 读取本次测试捕获的 message/error/output 尾部，不读取任意文件 |
| `check_tcp_port` | 只连接已审核计划的 `ip/device_ip/target_ip/host` 字面 IP 变量，且端口必须在配置白名单中；不发送应用数据 |
| `list_serial_ports` | 只枚举本机串口，不打开串口、不发送指令 |

```yaml
diagnostics:
  enabled: true
  max_rounds: 4
  max_tool_calls: 3
  max_seconds: 90
  llm_timeout: 20
  tool_timeout: 2
  allowed_ports: [22, 80, 443]
```

- 决策、非法输出修正和工具请求均消耗预算；重复检查被拦截。达到轮数或时间限制后收束为证据不足的结论。
- `llm_timeout` 限制单轮等待时间，`tool_timeout` 限制 TCP 连接等待。已发出的请求会协作式取消；不保证立即终止底层系统调用。
- 结论中的每条可能原因必须引用已有证据编号；这些编号的存在性会校验，因果推断仍需人工验证。
- 模型不可用、检查异常或用户停止诊断时，保留证据并生成低置信度结论，再继续报告流程。`enabled: false` 可关闭自动诊断。
- 诊断结果不改写原始测试状态，不执行上下电、重启、参数修改、shell 或自动重跑。
- 发送给诊断模型的证据会限制长度并对常见敏感字段、IPv4 地址及连接 URL 脱敏；知识文档和完整运行变量不会整体注入诊断上下文。
- `GET /api/state` 和任务详情包含 `diagnosis`，其中有结论、证据、检查轨迹和预算统计；报告中附加可追溯的诊断证据章节。
- `diagnosis_updated` WebSocket 事件实时更新诊断面板；服务重启后，任务可能进入 `diagnostic_failed`，可继续已保存的只读诊断。原有时间预算不会因重启重置。

## 核心代码

| 文件 | 职责 |
|---|---|
| `engine/intent_schema.py` | Pydantic 意图模型、DSL 校验、数值和嵌套边界 |
| `engine/planner.py` | LLM 调用、JSON 解析及限次修正 |
| `engine/intent_converter.py` | 意图到 DSL 转换、技能白名单 |
| `engine/workflow.py` | LangGraph、SQLite checkpoints、审核历史和恢复策略 |
| `engine/diagnostician.py` | 诊断决策、预算、证据引用校验及报告附录 |
| `engine/diagnostic_tools.py` | LangChain StructuredTool 只读工具白名单及输出脱敏 |
| `engine/agent_service.py` | API 门面、任务选择、后台运行互斥 |
| `engine/yaml_runner.py` | 条件、循环、变量、计时及本地技能执行 |
| `engine/skill_registry.py` | 动态加载 `skill.py`，读取 `skill.md` 能力描述 |
| `shared/skill_base.py` | BaseSkill 和 SkillMetadata |
| `server/http_server.py` | REST API 和静态文件 |
| `server/ws_server.py` | 执行事件及任务状态广播 |
| `web/js/review.js` | 审核、任务记录及页面恢复 |
| `web/js/diagnosis.js` | 诊断轨迹、证据展开、停止及中断恢复 |

技能目录为 `skills/common` 和 `skills/<station>`，后加载的同名技能覆盖先加载的。`skill.py` 导出 `skill_class`，继承 `shared.skill_base.BaseSkill`；`skill.md` 提供能力描述。本上传快照只包含 `common` 和 `virtual_device`；设备操作均为模拟技能。

## 任务 API

| 接口 | 用途 |
|---|---|
| `GET /api/state` | 当前任务的计划、版本、审核、结果、报告和状态 |
| `GET /api/tasks` | 持久化任务记录 |
| `GET /api/tasks/<task_id>` | 指定任务详情 |
| `POST /api/load-task` | 选择任务，body: `{task_id}` |
| `POST /api/generate-plan` | 后台生成新的待审核任务，body: `{instruction?}` |
| `POST /api/update-plan` | 更新草稿，body: `{task_id, revision, plan}` |
| `POST /api/review-plan` | 审核，body: `{task_id, revision, approved, comment?}` |
| `POST /api/start-test` | 执行已审核版本，body: `{task_id, revision, variables?}` |
| `POST /api/retry-report` | 仅重试失败的报告，body: `{task_id}` |
| `POST /api/resume-diagnosis` | 继续中断的只读诊断，body: `{task_id}` |
| `POST /api/generate-report` | 读取已经生成的报告，兼容旧接口 |

原计划库、知识上传、导入导出及暂停/继续/停止 API 保留。校验失败返回 400，状态或版本冲突返回 409。启动时提交的 variables 必须与已审核计划一致。

## 验证

```powershell
.\.venv-win\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv-win\Scripts\python.exe -m pytest
```

浏览器测试优先使用本机 Chrome；其他环境先运行 `python -m playwright install chromium`。只运行后端测试可用 `python -m pytest -m "not browser"`。

测试使用独立临时 SQLite、模拟技能和模拟 LLM，不触碰真实串口。覆盖结构校验、持久化审核、版本失效、崩溃恢复、报告重试、并发启动保护、HTTP API，以及桌面/移动端完整操作流程。诊断测试还覆盖危险工具/参数拦截、虚假证据、重复检查、预算耗尽、模型超时隔离、只读串口枚举和本机 TCP 连接、中断恢复及结果不被改写。浏览器截图保存在 `.local/`。

本地模型服务和真实设备需另行联调；本仓库尚无登录鉴权、技能沙箱或硬件操作恰好一次保证。
