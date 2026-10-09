# Architecture Code Agent · 星际分数探索

本项目包含两个可运行的程序：**接入 DeepSeek 的图形界面 Coding Agent**，以及**由该 Agent 实际调用 DeepSeek 生成并修复的中文分数小游戏**。

## 直接打开

在当前电脑上，双击根目录的 **`ArchitectureAgent.exe`**，然后点击 **“打开游戏”**。浏览器会打开已经生成的“星际分数探索”，不需要重新生成，也不需要消耗 API 额度。

也可以双击 `Start-Agent.cmd`。单独运行游戏时，双击 `output/space-fractions-llm/Start-Game.cmd`。

请保留整个项目文件夹，不要只把 EXE 单独拷走：生成的游戏存放在 EXE 旁边的 `output/` 子目录中。关闭 Agent 会停止它启动的游戏服务；独立启动游戏时，关闭对应的命令行窗口即可停止。

从 GitHub 克隆或下载项目后，先安装 Node.js 22 或更高版本，再双击 `output/space-fractions-llm/Start-Game.cmd`。脚本会首次安装游戏依赖，服务器就绪后打开浏览器。依赖安装完成后，也可以双击根目录的 `ArchitectureAgent.exe`，点击“打开游戏”。

### 换一台电脑时

- 需要 Windows 64 位、浏览器、Node.js 22 或更高版本（安装时包含 npm）。EXE 已包含 Python，无需另装 Python。
- 本机已经安装游戏依赖。如果拷贝时未携带游戏目录的 `node_modules`，先双击该目录的 `Start-Game.cmd`，它会安装依赖；首次安装需要联网。
- 只玩已生成的游戏不需要 DeepSeek Key，也不需要联网。重新生成需要有效的 DeepSeek Key、可用 API 额度以及访问 API/npm 的网络。
- 源码运行 Agent 需要 Python 3.11 或更高版本，Windows Python 需支持 Tkinter。

## 小游戏怎么玩

输入昵称，点击“开始探索”。每局随机抽取 5 题，答对一题加 10 分；提交后会显示正确答案及计算解析，再进入下一题。支持暂停/继续、刷新后恢复、结束成绩、排行榜、帮助以及键盘操作。

“教师端”可读取和修改题库，本地演示口令为 **`space-fractions-admin`**。这不是 DeepSeek Key。部署到非本机环境前必须使用环境变量 `ADMIN_TOKEN` 更改此演示口令。

游戏数据保存在 `output/space-fractions-llm/data/store.json`，首次使用时自动创建，保存题库、对局和排行榜。浏览器通过本地存储记住最近的对局；请使用同一个浏览器和访问地址恢复进度。服务端默认仅监听本机，不能当作互联网生产服务直接开放。

## 让 Agent 再生成一个项目

1. 打开 `ArchitectureAgent.exe`，选择自己的架构说明 Markdown 和 UML 视图 Markdown。本机默认读取 `input/Architecture_Documentation.md` 与 `input/Architecture_View.md`；原始任务文档留在本机，不随 GitHub 仓库分发。从 GitHub 下载后请在界面选择这两份输入文件，或自行放入上述路径。体验已生成的游戏不需要输入文档。
2. 选择自己的密钥文本文件，或在隐藏输入框中填入 DeepSeek API Key。本机默认识别项目上一级已有的 `key.txt`，也支持环境变量 `DEEPSEEK_API_KEY`。优先级为输入框、环境变量、文件。
3. 点击生成。Agent 会真实调用 DeepSeek：分析文档 → 制定计划 → 分组生成前后端和测试 → 安装依赖 → 执行测试与独立验收 → 将失败信息交给模型修复。
4. 等待“生成成功”，再点击“打开游戏”。生成通常需要数分钟，并消耗 API 额度。取消会在当前模型请求返回后生效。

模型默认 `deepseek-flash`；界面可修改模型名。API 仅允许官方 `https://api.deepseek.com` 或其 `/v1` 地址，避免密钥误发到其他站点。Key 不写入源码、生成项目、日志或 EXE；游戏本身不使用 Key。交付给老师时**不要附上你的 `key.txt`**。

每次生成都创建新目录，不覆盖已有结果。首次目录为 `output/space-fractions-llm`，以后带时间戳；`output/latest-project.json` 记录最近一次通过验收的项目。接口错误、缺少依赖或修复失败会在界面显示，不会把失败项目标记为成功。

该 Agent 面向本作业的架构文档和分数游戏需求，不是能生成任意软件的通用开发平台。模型生成代码会在本机执行测试；虽然限制了写入路径和依赖，并移除了测试子进程中的常见 API 密钥环境变量，但这**不是操作系统沙箱**，不要用它执行不可信任务或处理含密钥的输入文档。

## 项目结构

```text
AgentProject/
├─ ArchitectureAgent.exe          # 已打包的 Windows 图形界面 Agent
├─ Start-Agent.cmd                # 双击入口，优先使用 EXE
├─ desktop_entry.py               # 桌面程序源码入口
├─ agent/
│  ├─ desktop.py                  # 中文界面、异步生成、日志和游戏启动
│  ├─ deepseek_client.py          # 真实 API 请求、JSON 响应、重试和密钥保护
│  ├─ generation_prompts.py       # 架构上下文、生成约束和修复提示
│  ├─ llm_workflow.py             # 生成、安装、验证和自动修复流程
│  ├─ acceptance.py               # 独立功能验收，不由模型修改
│  └─ game_launcher.py            # 启动和停止本地游戏服务
├─ input/                        # 本地输入目录，不随 GitHub 仓库分发
├─ output/
│  ├─ latest-project.json
│  └─ space-fractions-llm/        # 本次真实 DeepSeek 生成的完整项目
│     ├─ public/                 # 网页、样式和交互代码
│     ├─ src/                    # 题库和 Express 后端
│     ├─ tests/game.test.js      # 模型生成的自动测试
│     ├─ Start-Game.cmd          # 独立双击启动
│     ├─ launch_game.cjs         # Agent 提供的启动辅助程序
│     ├─ package.json
│     ├─ package-lock.json
│     ├─ Dockerfile
│     └─ README.md
├─ tests/                        # Agent 测试、独立验收测试、浏览器回归测试
├─ build-exe.cmd                 # 重新打包 EXE
├─ build_executable.py
├─ requirements.txt              # Agent 运行仅使用 Python 标准库
└─ requirements-build.txt        # 可选打包依赖
```

游戏业务代码、网页、样式、测试及游戏 README 来自实际 DeepSeek 调用；启动脚本、依赖锁文件和独立验收由 Agent 工具流程补齐。保留的 `output/space-fractions` 是旧版模板示例，**不是本次交付的游戏**。旧学习笔记解释的是早期版本，当前操作以本 README 为准。

原架构提到的微服务、PostgreSQL、Redis、OAuth2 和云端集群没有作为运行前提引入：当前采用本地单进程 Express、JSON 文件持久化和教师令牌，实现可直接交互的教学应用。它不等同于已部署原文档中的生产级云架构，具体适配见生成游戏的 README。

## 命令行和开发

在 `AgentProject` 根目录打开 PowerShell：

```powershell
# 源码运行图形界面
py -3 -m agent.cli gui

# 本机已准备 input/ 时调用 DeepSeek；从上一级 key.txt 或环境变量读取 Key
py -3 -m agent.cli build --max-repairs 2

# 从 GitHub 下载后，明确指定自己的两份输入文档和密钥文件
py -3 -m agent.cli build --documentation 'D:\your-inputs\Architecture_Documentation.md' --views 'D:\your-inputs\Architecture_View.md' --key-file 'D:\your-private-folder\key.txt'

# Agent 自动测试（未安装 Playwright 时，浏览器测试会跳过）
py -3 -m unittest discover -s tests -v

# 检查当前生成游戏，包括语法、模型生成的测试和独立 HTTP 验收
py -3 -c "from pathlib import Path; from agent.llm_workflow import verify_project; r=verify_project(Path('output/space-fractions-llm').resolve()); print(r['output']); raise SystemExit(0 if r['passed'] else 1)"
```

可选浏览器测试使用本机 Microsoft Edge，不访问外部网页：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install playwright
.\.venv\Scripts\python.exe -m unittest tests.test_game_browser -v
```

测试使用临时数据文件，不修改正常游戏进度。可设置 `AGENT_GAME_DIR` 对其他生成目录运行浏览器测试。游戏也可以独立运行：

```powershell
Set-Location '.\output\space-fractions-llm'
npm.cmd ci --ignore-scripts
npm.cmd test
npm.cmd start
# 浏览器打开 http://127.0.0.1:3000
```

修改 Agent 源码后，在根目录运行 `build-exe.cmd` 更新 EXE。源码改动不会自动更新旧 EXE。首次打包先运行 `py -3 -m venv .venv`，再运行 `.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt`；本机已准备好。打包支持标准 Python 和 Conda Python 的 DLL 收集。

早期离线模板教学命令仍保留，`run --template` 才走旧流程；正常 `build` 和 `run` 均走 DeepSeek 流程。
