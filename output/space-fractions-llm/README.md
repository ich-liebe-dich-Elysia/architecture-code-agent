# 星际分数探索（Space Fractions）

面向六年级学生的中文分数闯关游戏。每局随机抽取 5 道分数题，答对一题获得 10 点能量，答完即可登上星际排行榜。

## 快速开始

```bash
npm install
npm test
npm start
```

启动后在浏览器打开 <http://localhost:3000> 即可开始游戏。

- 运行环境：Node.js 22 及以上（CommonJS）。
- 唯一外部依赖：Express 4.22.3。前端为原生 HTML/CSS/JS，无构建步骤、无 CDN、无外部图片与字体。

## 玩法说明

1. 在首页输入名字（1 到 24 个字符，留空使用“星际学员”），点击“开始探索”。
2. 每题有 4 个选项，点击选项后按“提交答案”。答对 +10 分，答错 +0 分，同一题只计分一次。
3. 提交后显示正确答案与解析，点击“下一题”继续；5 题完成后显示最终成绩。
4. 中途可以暂停，刷新页面后可通过“继续上次探索”恢复未完成的游戏。
5. 键盘操作：数字键 1-4 选择选项，回车提交或进入下一题。

## 教师端（题库管理）

点击顶部导航“教师端”，输入管理员令牌后可以读取并编辑题库。

- 本地演示令牌：`space-fractions-admin`（可通过环境变量 `ADMIN_TOKEN` 覆盖）。
- 该令牌只是本地教学演示用的口令，**不是任何真实密钥**，与 DeepSeek 或其他服务的密钥无关。
- 令牌只保存在浏览器 sessionStorage 中，不会写入 HTML 源码。
- 题库必须是 5 到 100 题的数组，每题包含 `id`、`prompt`、`options`（4 个互不相同的字符串）、`answer`（必须是选项之一）、`explanation`。
- 管理员修改题库不会影响已经开始的对局：每局开始时会把当次题目复制到会话快照中。

## 数据持久化

- 默认数据文件：`data/store.json`（可用环境变量 `DATA_FILE` 指定其他路径）。
- 保存方式：先写入临时文件再原子重命名，避免写入中断导致数据损坏。
- 重启服务后会加载已有数据；如果数据文件损坏或结构无效，服务会直接报错退出，而不会静默清空数据。
- 数据文件包含题库、进行中的对局和排行榜记录。

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查，返回 `{status:'ok'}` |
| POST | `/api/games` | 开始新对局，body 可选 `{playerName}` |
| GET | `/api/games/:id` | 查询对局快照 |
| POST | `/api/games/:id/answers` | 提交答案，body `{answer, questionId?}` |
| POST | `/api/games/:id/pause` | 暂停对局 |
| POST | `/api/games/:id/resume` | 恢复对局 |
| GET | `/api/help` | 中文玩法与分数技巧 |
| GET | `/api/leaderboard` | 已完成对局排行榜（最多 20 条，按分数降序） |
| GET | `/api/admin/questions` | 读取完整题库（需要 `x-admin-token`） |
| PUT | `/api/admin/questions` | 覆盖题库（需要 `x-admin-token`） |

兼容别名（对应原始架构中的旧接口）：`GET /health`、`GET /play`（开局）、`GET /scores/:id`（查看成绩）。

公共题目对象只包含 `id`、`prompt`、`options`，提交前不会返回 `answer` 与 `explanation`。

## 架构适配说明

原始架构文档描述的是微服务方案（PostgreSQL、Redis、RabbitMQ、Elasticsearch、OAuth2、Kubernetes、Terraform 等）。本任务要求交付一个**本地可运行、无数据库服务器**的教学演示程序，因此做了如下如实适配，并未声称已部署任何云服务：

| 架构文档中的设计 | 本地实现 |
| --- | --- |
| 微服务拆分（Game/Question/User/Admin 组件） | 单个 Express 进程内的模块划分：`src/app.js` 负责游戏与用户会话，`src/questions.js` 负责题库 |
| PostgreSQL 持久化 | 本地 JSON 文件 `data/store.json`，原子写入 |
| Redis 缓存 | 无（单进程内存状态） |
| RabbitMQ / Elasticsearch | 无（无异步消息与全文检索需求） |
| OAuth2 认证 | 管理员接口使用 `x-admin-token` 简单令牌校验 |
| Kubernetes 3 副本部署 | 提供 `Dockerfile`，可单容器运行；未部署编排系统 |
| Prometheus 可观测性 | 提供 `/api/health` 健康检查端点 |

## Docker

```bash
docker build -t space-fractions .
docker run --rm -p 3000:3000 -e HOST=0.0.0.0 space-fractions
```

镜像基于 `node:22-alpine`，使用 `npm install --omit=dev --ignore-scripts` 安装依赖。容器内通过 `ENV HOST=0.0.0.0` 允许外部访问；本地直接 `npm start` 时默认绑定 `127.0.0.1`。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `PORT` | `3000` | 监听端口 |
| `HOST` | `127.0.0.1` | 监听地址 |
| `DATA_FILE` | `data/store.json` | 数据文件路径 |
| `ADMIN_TOKEN` | `space-fractions-admin` | 管理员令牌 |

## 测试

```bash
npm test
```

测试使用 `node:test` 与真实 HTTP 请求（临时数据文件 + 随机端口），覆盖健康检查、开局、答对计分、答错与非法答案、暂停/恢复、完成与排行榜、持久化与损坏检测、管理员鉴权与题库校验。
