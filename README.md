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
- yolo

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
