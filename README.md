# Kaoyan Problem Discovery Agent

Kaoyan Problem Discovery Agent 是面向考研场景的问题发现与自适应干预 Agent。它不是普通聊天机器人，也不是多空间管理工具。当前课程 MVP 只有一个考研备考工作区。

Chat 只是输入渠道，系统中心是证据记录、晚间回顾、结构化问题发现、长期记忆和后续干预。

本项目采用 Streamlit + SQLite + LangChain 的 Agentic Workflow 架构。UI 层负责交互，Workflow 层负责编排，Agent 层使用 LangChain create_agent 调用 LLM，结构化输出通过 Pydantic response_format 约束，Repository 层统一管理数据库读写。系统通过在线聊天保存学习证据，通过晚间回顾进行结构化问题发现和长期记忆更新，并将问题写入 Problem Board，形成“证据 → 问题 → 记忆 → 干预”的闭环。

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

Supervision mode:

```text
supervision_page
-> render_pomodoro_supervision_panel()
-> FocusWorkflow
-> FocusSupervisionAgent
-> run_structured_vision_agent(response_format=FocusStateRecognitionOutput)
-> FocusRepository / RawEventRepository
-> focus_state_events / focus_reports / raw_events
```

Camera supervision uses a `streamlit-webrtc` video stream plus an in-memory
latest-frame sampler. After the user authorizes the camera, the app periodically
recognizes the current study state without asking the learner to click during
the focus block. The app does not persist raw camera images by default; it stores
state labels, confidence, explanations, and generated focus-report signals for
nightly review. If the configured model or provider does not support vision, the
workflow records an `unknown` state and keeps a local fallback report path.

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
