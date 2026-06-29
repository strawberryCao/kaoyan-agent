# Kaoyan Problem Discovery Agent

Kaoyan Problem Discovery Agent 是面向考研场景的问题发现与自适应干预 Agent。它不是普通聊天机器人，也不是多空间管理工具。当前课程 MVP 只有一个考研备考工作区。

Chat 只是输入渠道，系统中心是证据记录、晚间回顾、结构化问题发现、长期记忆和后续干预。

本项目采用 Streamlit + SQLite + LangChain 的 Agentic Workflow 架构。UI 层负责交互，Workflow 层负责编排，Agent 层使用 LangChain create_agent 调用 LLM，结构化输出通过 Pydantic response_format 约束，Repository 层统一管理数据库读写。系统通过在线聊天保存学习证据，通过晚间回顾进行结构化问题发现和长期记忆更新，并将问题写入 Problem Board，形成“证据 → 问题 → 记忆 → 干预”的闭环。

## 技术栈

- Python 3.10+
- Streamlit：Web UI 和侧边栏页面分发。
- SQLite：主业务数据库，保存会话、原始证据、晚间回顾、问题板、记忆和任务数据。
- Pydantic v2：校验 LLM 结构化输出，防止未验证数据写入核心表。
- LangChain：ChatAgent、Nightly Memory、Practice Review 等 Agent 调用链。
- OpenAI-compatible LLM API：默认按 DeepSeek/OpenAI 兼容接口配置。
- Chroma：可选向量记忆后端，用于语义检索。
- Neo4j：可选图谱后端，用于关系检索、诊断和增强。
- streamlit-webrtc、OpenCV、Ultralytics、MediaPipe：可选本地督学/专注状态识别能力。
- Docker Compose：本地启动 Neo4j 依赖。

## 环境依赖

基础环境：

- Windows / macOS / Linux 均可运行。
- Python 3.10 或更高版本；如需 MediaPipe，Python 版本需低于 3.13。
- 建议使用虚拟环境 `.venv`。
- 如启用 Neo4j 图谱后端，需要 Docker Desktop 或本地 Neo4j 服务。

Python 依赖定义在：

- `pyproject.toml`
- `requirements.txt`

安装依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

或：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 项目配置

本地配置文件使用 `.env`，示例文件为 `.env.example`。不要提交真实 API key。

LLM 配置：

```powershell
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-v4-pro
```

Embedding 配置：

```powershell
EMBEDDING_PROVIDER=siliconflow
EMBEDDING_API_KEY=your_embedding_api_key_here
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_BATCH_SIZE=16
EMBEDDING_TIMEOUT_SECONDS=20
```

记忆后端配置：

```powershell
VECTOR_BACKEND=chroma
CHROMA_PERSIST_DIR=data/chroma

GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
GRAPH_SYNC_RAW_EVENTS=false
```

可选本地督学配置：

```powershell
YOLO_FOCUS_WEIGHTS_PATH=
YOLO_FOCUS_CAMERA_ID=0
YOLO_FOCUS_CONFIDENCE_THRESHOLD=0.5
YOLO_FOCUS_INFERENCE_FPS=3
YOLO_PERSON_WEIGHTS_PATH=models/person_presence/yolov8n.pt
YOLO_PERSON_CONFIDENCE_THRESHOLD=0.35
FOCUS_PHONE_CONFIDENCE_THRESHOLD=0.35
FOCUS_VISUAL_EVIDENCE_THRESHOLD=0.55
FOCUS_PRESENCE_FOCUS_CONFIDENCE_THRESHOLD=0.65
YOLO_AWAY_CONFIRM_SECONDS=10
YOLO_BEHAVIOR_WINDOW_SECONDS=3
FOCUS_REPORT_MIN_COVERAGE=0.8
```

历史数据库 `data/app.db` 是真实本地数据文件。不要删除、重建或重置该文件。

## 部署方式

本地 Streamlit 部署：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
streamlit run app.py
```

启动后浏览器访问 Streamlit 输出的本地地址，通常为：

```text
http://localhost:8501
```

如需启用 Neo4j：

```powershell
docker compose -f docker-compose.neo4j.yml up -d
```

然后在 `.env` 中配置：

```powershell
GRAPH_BACKEND=neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
```

可选索引检查与回填：

```powershell
python scripts/check_memory_backends.py
python scripts/backfill_memory_indexes.py --all
```

## 产品结构

当前 UI 是单一考研备考工作区：

```text
Kaoyan Agent
-> 全局会话
-> 常用学习功能
-> Agent 诊断
-> 设置
```

侧边栏顺序：

1. 新建对话
2. 常用功能：今日任务 / 学习规划、督学模式、错题复习、成绩趋势
3. 最近会话
4. Agent 诊断：晚间回顾、问题板
5. 轻量激励：运势签
6. 设置

记忆库在设置里查看，不作为一级导航。

## 工程结构

正式业务包只有一个：

```text
src/kaoyan_agent/
```

关键入口：

- `app.py`：唯一 Streamlit 启动入口，只做 src bootstrap、`init_db()`、侧边栏导航和页面分发。
- `src/kaoyan_agent/ui/chat_page.py`：聊天页。
- `src/kaoyan_agent/ui/task_page.py`：今日任务 / 学习规划。
- `src/kaoyan_agent/ui/supervision_page.py`：督学模式。
- `src/kaoyan_agent/ui/mistake_review_page.py`：错题复习。
- `src/kaoyan_agent/ui/score_trend_page.py`：成绩趋势。
- `src/kaoyan_agent/ui/nightly_review_page.py`：晚间回顾。
- `src/kaoyan_agent/ui/problem_board_page.py`：问题板。
- `src/kaoyan_agent/ui/fortune_page.py`：运势签。
- `src/kaoyan_agent/ui/settings_page.py`：设置。

## 分层边界

- `ui/`：只做展示和按钮交互，不写 SQL，不直接调用 LLM。
- `workflows/`：串联 repositories、agents、services、schemas。
- `agents/`：封装推理能力，不直接写数据库。
- `repositories/`：只做 CRUD，不调 LLM，不拼 prompt。
- `db/`：只做连接、schema 初始化、兼容迁移和通用 helper。
- `schemas/`：约束结构化输出。
- `memory/`：记忆检索、门控、合并、评分等底层能力。

## 数据兼容

历史数据库里可能保留 `projects` 表和 `project_id` 字段。这些只作为兼容层保留，避免破坏已有 `data/app.db`。当前产品和 UI 不把它们作为主概念。

不要删除或重建 `data/app.db`，不要提交真实 `.env` API key。

## Pydantic 与 SQLite

Pydantic schema 和 SQLite schema 不是一回事：

- Pydantic 管 LLM 输出是否合法。
- SQLite 管合法数据如何持久化。

晚间链路必须保持：

```text
LLM raw response
-> NightlyMemoryUpdateOutput.model_validate_json()
-> typed object
-> model_dump()
-> repositories
-> SQLite
```

结构化解析失败时，只写 `nightly_reviews.raw_response`、`parse_status="failed"`、`error_message`，不写 `problem_board` 和 `memories`。

## 运行

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
streamlit run app.py
```

## 阅读顺序

1. `app.py`
2. `src/kaoyan_agent/ui/shared.py`
3. `src/kaoyan_agent/ui/chat_page.py`
4. `src/kaoyan_agent/ui/task_page.py`
5. `src/kaoyan_agent/ui/supervision_page.py`
6. `src/kaoyan_agent/ui/mistake_review_page.py`
7. `src/kaoyan_agent/ui/score_trend_page.py`
8. `src/kaoyan_agent/ui/nightly_review_page.py`
9. `src/kaoyan_agent/ui/settings_page.py`
10. `src/kaoyan_agent/workflows/nightly_memory_workflow.py`
11. `src/kaoyan_agent/repositories/`

## 验证

```powershell
.\.venv\Scripts\python.exe -m compileall app.py src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe -c "from kaoyan_agent.db import init_db; init_db(); print('ok')"
```

## LangChain Agent Path

ChatAgent, Nightly Memory, and Practice Review now use LangChain first, while keeping the original fallback paths.

Online chat:

```text
chat_page
-> OnlineSessionWorkflow.handle_user_message()
-> QueryRewriter
-> Router
-> MemoryRetriever
-> ContextBuilder
-> ChatAgent
-> create_agent(tools=[list_open_problems_tool, list_today_tasks_tool, search_memory_tool])
-> LLMClient.chat() fallback
-> ChatRepository / RawEventRepository / AgentRunRepository
```

ChatAgent tools are read-only. They can list open problems, list today's tasks, and search existing memory/problem context. They never create tasks, update status, delete data, or write SQLite rows.

Nightly review:

```text
nightly_review_page
-> NightlyMemoryWorkflow
-> NightlyMemoryAgent
-> create_langchain_model()
-> create_agent(response_format=NightlyMemoryUpdateOutput)
-> response["structured_response"]
-> model_dump()
-> repositories
-> SQLite
```

Practice review:

```text
mistake_review_panel
-> PlanningWorkflow.generate_and_save_practice_card()
-> PracticeReviewAgent
-> create_agent(response_format=PracticeReviewCard)
-> normalize_card()
-> PracticeReviewRepository.create_card()
```

`LLMClient.chat()` remains the stable OpenAI-compatible fallback. The LangChain
factory is `create_langchain_model(settings, temperature=0.3)`. It tries
`langchain_deepseek.ChatDeepSeek` first, then `langchain_openai.ChatOpenAI`.
For DeepSeek structured output, prefer a tool-calling/structured-output-capable
model such as `deepseek-chat`; do not use `deepseek-reasoner` as the main model
for this path.

This version intentionally does not use LangGraph. A future version can consider mapping `OnlineSessionWorkflow` to LangGraph StateGraph only if the workflow becomes complex enough to need state-graph orchestration.

References:

- [LangChain structured output](https://docs.langchain.com/oss/python/langchain/structured-output)
- [ChatDeepSeek integration](https://docs.langchain.com/oss/python/integrations/chat/deepseek)
- [ChatOpenAI integration](https://docs.langchain.com/oss/python/integrations/chat/openai)

## Embedding API Configuration

Nightly memory gates can use a low-cost embedding API for small-scale SQLite
cosine similarity. The default provider is SiliconFlow `BAAI/bge-m3`; OpenAI
embeddings are not used by default.

```powershell
EMBEDDING_PROVIDER=siliconflow
EMBEDDING_API_KEY=your_embedding_api_key_here
EMBEDDING_BASE_URL=https://api.siliconflow.cn/v1
EMBEDDING_MODEL=BAAI/bge-m3
EMBEDDING_BATCH_SIZE=16
EMBEDDING_TIMEOUT_SECONDS=20
```

If the embedding key is missing or the request fails, the nightly workflow keeps
running and falls back to lexical matching. Gate diagnostics record the
embedding status and error.

## Memory Backends

SQLite is the primary store. Chroma stores memory/problem embeddings for
semantic retrieval, and Neo4j stores graph relations for retrieval boosts and
diagnostics.

Start Neo4j locally:

```powershell
docker run --name kaoyan-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/password neo4j:latest
```

Or use:

```powershell
docker compose -f docker-compose.neo4j.yml up -d
```

Then set `NEO4J_PASSWORD=password` in your local `.env`, run:

```powershell
python scripts/check_memory_backends.py
python scripts/backfill_memory_indexes.py --all
```
