# Kaoyan Agent – Electron 桌面应用

本项目基于 **Electron** 将 **Streamlit** 智能体应用打包为跨平台桌面程序。

Streamlit 部分负责学习干预、记忆系统和专注督学等核心功能，Electron 提供原生窗口和系统集成。

## 前置条件

- **Node.js** ≥ 18 (推荐 LTS)

- **Python** ≥ 3.10 (推荐 3.11 或 3.12)

- **uv** (Python 包管理器，[安装指南](https://docs.astral.sh/uv/))

- **Git**

## 快速开始

### 克隆仓库

```bash
git clone https://github.com/strawberryCao/kaoyan-agent.git
cd kaoyan-agent
```

### 安装 Node.js 依赖

```bash
npm install
```

### 配置 Python 环境

本项目中的 Streamlit 应用位于 `streamlit/` 目录，依赖 Python 虚拟环境。你可以通过以下任一方式完成配置：

- **方式一 (推荐)**：运行项目预置脚本，自动完成虚拟环境创建与依赖同步

  ```bash
  npm run preinstall
  ```

- **方式二 (手动)**：进入 `streamlit/` 目录，使用 `uv` 管理工具手动配置

  ```bash
  cd streamlit
  uv venv
  uv sync
  cd ..
  ```

> **注意**：Electron 打包时会自动将 `streamlit/` 目录作为额外资源复制，并期望 `streamlit/.venv/Scripts/python.exe` (Windows) 或 `streamlit/.venv/bin/python` (macOS/Linux) 存在，因此务必先执行 `uv sync`。

## 开发模式运行

在根目录下执行：

```bash
npm start
```

Electron 窗口会启动，并自动拉起 Streamlit 服务 (默认监听 `http://localhost:8501`)。

首次启动可能会稍慢，请留意控制台输出。

## 打包为可安装程序

```bash
npm run dist
```

打包产物会输出到 `dist/` 目录，根据操作系统生成对应的安装包 (Windows 为 NSIS 安装包，macOS 为 `.dmg`)。

打包时会包含整个 `streamlit/` 目录及其虚拟环境，因此请确保在打包前已经完成 `uv sync`。

## 生产环境配置

> 打包后的应用 **不会读取** 项目目录下的 `.env` 文件，而是直接从用户配置目录中的 `config.json` 加载配置。
> 你可以在以下位置找到或创建该文件：

| 平台    | 路径                                            |
| ------- | ----------------------------------------------- |
| Windows | `%APPDATA%\app\config.json`                     |
| macOS   | `~/Library/Application Support/app/config.json` |
| Linux   | `~/.config/app/config.json`                     |

`config.json` 示例内容：

```json
{
  "llmApiKey": "your_api_key_here",
  "llmBaseUrl": "https://api.deepseek.com/v1",
  "llmModel": "deepseek-v4-pro",
  "embeddingProvider": "siliconflow",
  "embeddingModel": "BAAI/bge-m3",
  "embeddingApiKey": "",
  "embeddingBaseUrl": "https://api.siliconflow.cn/v1",
  "embeddingBatchSize": 16,
  "embeddingTimeoutSeconds": 20,
  "vectorBackend": "chroma",
  "chromaPersistDir": "data/chroma",
  "graphBackend": "neo4j",
  "neo4jUri": "bolt://localhost:7687",
  "neo4jUsername": "neo4j",
  "neo4jPassword": "",
  "graphSyncRawEvents": false,
  "yoloFocusWeightsPath": "",
  "yoloFocusCameraId": 0,
  "yoloFocusConfidenceThreshold": 0.5,
  "yoloFocusInferenceFps": 3,
  "yoloPersonWeightsPath": "models/person_presence/yolov8n.pt",
  "yoloPersonConfidenceThreshold": 0.35,
  "focusPhoneConfidenceThreshold": 0.35,
  "focusVisualEvidenceThreshold": 0.55,
  "focusPresenceFocusConfidenceThreshold": 0.65,
  "yoloAwayConfirmSeconds": 10,
  "yoloBehaviorWindowSeconds": 3,
  "focusReportMinCoverage": 0.8
}
```
