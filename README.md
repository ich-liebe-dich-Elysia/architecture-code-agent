# Architecture-to-Project Code Agent

一个无需大模型 API Key 的简化代码生成工具。它通过规则解析架构说明和 PlantUML 视图，整理为 JSON 规格，再使用预设模板生成可运行的 Node.js + Express 项目骨架。

工作流程：**读取架构 → 整理规格 → 输出生成计划 → 写入工程文件 → 验证结果**。

## 功能

- 从特定格式的架构 Markdown 中提取项目名称、技术栈、组件、API、数据表名称及需求追踪项。
- 提取 PlantUML 子集中的角色、用例、类名、组件、关系、交互和状态名称。
- 输出 `architecture_spec.json`、`generation_plan.json` 和验证报告。
- 生成 Express API、依赖文件、README、Dockerfile 和 Node HTTP 测试。
- 检查文件完整性、依赖声明、固定路由及规格副本；可选调用生成项目的 `npm test`。

仓库仅保存 Agent 源码、依赖配置和本 README。本地输入文档、学习笔记、测试文件、验收记录、生成产物及 `node_modules` 不纳入版本控制。生成测试文件仍是工具本身保留的功能。

## 环境要求

- Python 3.11 或以上；Windows 示例使用 `py -3`，其他环境可替换为 `python3`。
- Node.js 18 或以上及 npm，用于运行生成的服务。本项目已在 Node.js 22 上运行验证。

Agent 只使用 Python 标准库，无须 `pip install`，也无需配置模型 API Key。

## 快速体验：使用内置示例规格

克隆仓库后，在仓库根目录的 PowerShell 中逐条执行：

```powershell
# 使用内置示例，不依赖未随仓库上传的架构文档
py -3 -m agent.cli sample-spec --output output/architecture_spec.json
py -3 -m agent.cli plan
py -3 -m agent.cli generate
py -3 -m agent.cli validate

# 安装依赖并启动生成的服务
Set-Location '.\output\space-fractions'
npm.cmd install
npm.cmd test
npm.cmd start
```

此流程中的 JSON 来自内置示例，没有执行外部架构文档解析。Linux/macOS 中将 `npm.cmd` 替换为 `npm`。

服务默认监听 `http://localhost:3000`：

| 接口 | 当前行为 |
| --- | --- |
| `GET /health` | 返回 `{"status":"ok"}` |
| `GET /play` | 返回固定游戏 ID 和一道分数题 |
| `POST /play/1/answer` | 接收 `{"answer":"1/2"}` 并判断答案 |
| `GET /scores/1` | 返回占位得分 0 |

程序提供 JSON API，没有网页首页，访问 `/` 返回 404。`npm start` 持续占用终端，按 `Ctrl+C` 停止服务。

在另一个 PowerShell 窗口可调用：

```powershell
Invoke-RestMethod 'http://localhost:3000/health'
Invoke-RestMethod 'http://localhost:3000/play' | ConvertTo-Json -Depth 6
Invoke-RestMethod -Method Post -Uri 'http://localhost:3000/play/1/answer' -ContentType 'application/json' -Body '{"answer":"1/2"}'
```

## 使用自己的架构文档

把架构说明和 UML Markdown 放在本地 `input/` 目录，或通过参数传入其他位置。在仓库根目录执行：

```powershell
py -3 -m agent.cli run --documentation input/Architecture_Documentation.md --views input/Architecture_View.md
```

两份文档不随本仓库分发。解析器要求与原作业输入相同的格式，例如：

````markdown
The Space Fractions system is a web-based learning tool.
Chosen architectural style: Microservices
* Language/runtime: Node.js 18
* Web framework: Express.js 4
* GameComponent: responsible for game logic

```yml
paths:
  /play:
    get:
      summary: Play the game
```
````

UML 使用 `actor EndUser`、`class Game`、`artifact GameComponent`、`User->>Game: play()` 等当前解析器支持的语法。它不支持任意格式的架构文档或完整 PlantUML 语法。

省略输入参数时，程序沿用原作业布局，查找仓库同级的 `RotationTask(1)` 目录；独立克隆后请使用上面的显式参数或内置示例。

## 输出与验证

```text
output/
├─ architecture_spec.json
├─ generation_plan.json
├─ generation_report.md
└─ space-fractions/
   ├─ package.json
   ├─ src/
   ├─ tests/
   ├─ README.md
   └─ Dockerfile
```

安装生成项目的 npm 依赖后，在仓库根目录执行：

```powershell
py -3 -m agent.cli validate --run-npm-tests
```

该命令把真实 Node 测试结果写入 `output/generation_report.md`。默认 `validate` 只运行静态检查；报告通过不代表全部架构需求均已实现。

可单独运行的命令为 `check`、`sample-spec`、`analyze`、`plan`、`generate`、`validate` 和 `run`。`check` 仅检查 CLI 入口，不检测完整运行环境。详细参数见：

```powershell
py -3 -m agent.cli --help
```

再次生成会覆盖模板对应的输出文件，需要保留的手工修改请另行保存。

## 源码结构

```text
agent/
├─ __init__.py
├─ cli.py                   # 命令行入口
├─ specification.py         # 规格数据结构、校验与 JSON 序列化
├─ documentation_parser.py  # 架构 Markdown 规则解析
├─ uml_parser.py            # PlantUML 子集解析
├─ planner.py               # 固定工程文件清单
├─ generator.py             # Express 模板及文件写入
├─ validator.py             # 静态检查与可选 Node 测试
└─ workflow.py              # 工作流编排
```

## 当前边界

这是针对固定输入格式和固定技术栈的 MVP。主要业务代码来自预设模板，修改规格中的接口路径不会自动改变生成的路由。架构中的微服务、PostgreSQL、Redis、认证等信息目前用于记录，尚未落实为完整运行组件。

游戏会话、累计计分、多题进度和完善的参数校验尚未实现。生成的两个 HTTP 测试只覆盖 `/health` 和 `/play`。当前工作流不调用大模型，也没有根据测试失败自动修复代码的循环。
