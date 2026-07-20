# Windows 桌面版摄像头与 YOLO 修复交付说明

## 1. 交付结论

本次已经修复 Windows 桌面版中“摄像头打不开、YOLO 可能因模型或路径不可用”的核心问题。

- YOLO 模型不是运行时自动下载，而是随应用内置：`streamlit/models/person_presence/yolov8n.pt`。
- Electron 现在会明确允许本地 Streamlit 页面申请视频权限。
- 摄像头预览不再依赖 YOLO 是否成功加载；模型异常时仍能看到预览，只暂停自动识别。
- YOLO 配置、数据库和 Chroma 数据写入 Electron 用户数据目录，不再尝试写入只读安装目录。
- Windows 包现在携带独立 Python 运行时，目标电脑不需要预装 Python 或 `uv`。
- “视觉证据：降级”不是预期常态：MediaPipe/OpenCV 已锁定到兼容版本，构建自检会拒绝降级状态。
- MediaPipe 姿态模型随依赖内置，首次启动不需要联网下载模型文件。
- 正确的用户数据环境变量是 `USER_DATA_PATH`，不是 `USED_DATA_PATH`。

大模型 API 设置页面属于此前已经处理的功能，不是本次改动范围。

## 2. 原因分析

### 2.1 摄像头权限没有由 Electron 主进程处理

浏览器中运行时，网站可以正常弹出摄像头授权；Electron 打包后需要主进程处理 `media` 权限。原桌面入口没有设置权限处理器，因此 WebRTC 摄像头可能直接失败。

现在只允许以下本地地址申请视频权限：

- `http://localhost:8501`
- `http://127.0.0.1:8501`
- IPv6 本机回环地址的 8501 端口

远程页面、其他端口和纯音频请求不会获得授权。

### 2.2 YOLO 不可用时阻断了整个摄像头组件

原 UI 在 YOLO 权重或依赖不可用时，不创建 WebRTC 摄像头组件，所以用户看到的是“摄像头打不开”，但根因可能只是模型没加载。

现在摄像头和模型状态已经解耦：摄像头继续显示，页面同时提示“暂不执行自动识别”。

### 2.3 安装目录与用户数据目录混用

桌面应用安装目录可能只读。Ultralytics 配置、数据库和向量库不能写到安装资源目录。

现在的目录边界为：

- 只读资源：安装目录中的 YOLO 权重和应用源码；
- 可写数据：`USER_DATA_PATH/data/` 下的数据库、Chroma 和 Ultralytics 配置。

### 2.4 `.venv` 并不等于独立 Python

Windows 虚拟环境里的解释器仍可能引用打包电脑上的 `uv` Python。仅复制 `.venv`，换到没有 Python 的电脑后可能无法启动。

预安装脚本现在会把对应的基础 Python 暂存到 `streamlit/.python-runtime`。Electron 优先使用该解释器，并通过 `PYTHONPATH` 加载 `.venv` 中的第三方依赖。

### 2.5 “视觉证据：降级”来自依赖 API 不兼容

原构建环境解析到了 MediaPipe 0.10.35 和 OpenCV 5.0.0.93。该组合不再提供当前识别器调用的 `mediapipe.solutions`、`cv2.CascadeClassifier` 等 API，因此 YOLO 虽能加载，面部、姿态和手部证据却会真实降级。

现在锁定为 MediaPipe 0.10.21、OpenCV/OpenCV Contrib 4.11.0.86 和兼容的 NumPy 1.26.4。另将姿态识别从会在首次运行下载模型的 `model_complexity=0` 改为 wheel 已内置的 `model_complexity=1`，保证离线桌面环境可启动。

## 3. 主要修改文件

- `index.js`：安装摄像头权限处理器，设置用户数据路径、YOLO 配置路径和独立 Python 运行环境。
- `desktop_runtime.js`：实现本地来源校验、Electron 权限策略和可写配置路径解析。
- `preinstall.js`：修复 Windows 下 `uv` 检测，并暂存独立 Python 运行时。
- `package.json`：将权限模块、`.venv`、独立 Python 和 Streamlit 资源加入桌面包；增加构建前检查及测试命令。
- `scripts/check-desktop-runtime.js`：构建前实例化完整识别器，实际加载 YOLO 和本地视觉提取器；检测到降级状态会终止构建。
- `streamlit/pyproject.toml`：锁定兼容的 MediaPipe、OpenCV 和 OpenCV Contrib 版本。
- `streamlit/src/kaoyan_agent/services/local_yolo_focus_recognizer.py`：把 Ultralytics 配置目录迁移到可写用户目录，并使用 MediaPipe 内置的离线姿态模型。
- `streamlit/src/kaoyan_agent/ui/components/pomodoro_supervision_panel.py`：解除摄像头预览对 YOLO 可用状态的依赖。
- `streamlit/src/kaoyan_agent/core/settings.py`：把 Chroma 默认目录迁移到用户数据目录。
- `tests/desktop_runtime.test.js`、`streamlit/tests/test_focus_supervision.py`：增加回归测试。

## 4. 已完成验证

2026-07-20 在 Windows 上完成以下验证：

1. `npm run test:desktop`：4 项通过，包括“降级状态阻止构建”的回归测试。
2. `python -m pytest streamlit/tests/test_focus_supervision.py ...`：25 项通过，包括 MediaPipe 离线模型回归测试。
3. Python 编译检查：通过。
4. `npm run check:desktop`：通过，完整识别器不是降级状态。
5. YOLO 权重实际加载：通过，包含 `person` 和 `cell_phone` 类别；OpenCV 本地视觉提取器实际加载。
6. `npm run dist -- --dir`：通过，成功生成 `dist/win-unpacked/Streamlit.exe`。
7. 直接使用成品目录中的 `.python-runtime/python.exe` 再次加载成品内 YOLO 和本地视觉证据：通过，版本为 MediaPipe 0.10.21、OpenCV 4.11.0、NumPy 1.26.4，输出 `PACKAGED_FULL_VISUAL_OK`。
8. 成品 `app.asar` 已确认包含 `index.js` 和 `desktop_runtime.js`。
9. 正式 NSIS 安装包生成：通过。

本次生成的安装包信息：

- 文件：`dist/Streamlit Setup 1.0.0.exe`
- 大小：539.2 MiB（565347563 字节）
- SHA-256：`C31D6E1CFB89E6EEBB9D20BDCD69D5E6363F9B1A457B7DD589E21B168AC254FB`
- 签名状态：`NotSigned`

该安装包可用于项目内部测试。因为当前没有配置 Windows 代码签名证书，Windows SmartScreen 可能显示未知发布者；对外正式分发前建议由负责人完成产品名称、图标和代码签名配置。

尚需负责人或测试人员完成一次真实摄像头人工验收，因为自动化测试不能代替摄像头硬件授权和画面检查。

## 5. 负责人验收步骤

1. 在 Windows 打开“设置 → 隐私和安全性 → 相机”。
2. 开启“相机访问”和“允许桌面应用访问相机”。
3. 关闭微信、腾讯会议、浏览器会议页面等可能占用摄像头的程序。
4. 启动桌面应用并开始一个番茄钟。
5. 开启视觉督学，确认能看到实时画面。
6. 人进入和离开画面，确认人员状态能变化。
7. 手机出现在画面中，确认能够产生手机相关识别结果。
8. 暂停或结束番茄钟，确认摄像头停止。

若有画面但没有识别结果，先执行 `npm run check:desktop` 检查模型；若完全没有画面，优先检查 Windows 权限和摄像头占用。

## 6. 从干净仓库构建

构建机需要 Node.js、npm 和 `uv`。目标用户电脑不需要这些工具。

```powershell
npm ci
npm run check:desktop
npm run test:desktop
npm run dist
```

`npm ci` 会执行 `preinstall.js`，完成 Python 依赖同步和独立运行时暂存。`npm run dist` 会先执行运行时自检，自检失败时不会继续生成安装包。

如 Electron Builder 报 `spawn powershell.exe ENOENT`，说明当前终端的 PATH 缺少 Windows PowerShell，可在当前终端执行：

```powershell
$env:Path = "$env:SystemRoot\System32\WindowsPowerShell\v1.0;$env:Path"
npm run dist
```

如果最后生成 NSIS 时下载 `nsis-resources-3.4.1.7z` 报 `ECONNRESET`，这是构建资源网络问题，不是应用代码失败。官方资源地址为：

```text
https://github.com/electron-userland/electron-builder-binaries/releases/download/nsis-resources-3.4.1/nsis-resources-3.4.1.7z
```

下载后必须核对 SHA-256：

```text
593a9a92ef958321293ac6a2ee61e64bf1bd543142a5bd6b3d310709cc924103
```

将其解压后，可通过 `ELECTRON_BUILDER_NSIS_RESOURCES_DIR` 指向包含 `plugins` 的解压目录，再对 `dist/win-unpacked` 执行 `electron-builder --win nsis --prepackaged`。本次正式安装包就是按该方式成功生成的。

生成结果位于 `dist/`。`dist/win-unpacked` 可以用于内部快速测试；正式交付建议使用 `npm run dist` 产生的 NSIS 安装包。

## 7. 推荐提交方式

建议提交代码分支和 PR，不要把 `.venv`、`.python-runtime`、`dist`、数据库或用户配置提交到 Git。

当前修复分支：`fix/desktop-yolo-camera`。

先检查改动：

```powershell
git status --short
git diff --check
```

只暂存本次修复文件：

```powershell
git add .gitignore README.md index.js package.json preinstall.js desktop_runtime.js scripts/check-desktop-runtime.js tests/desktop_runtime.test.js streamlit/README.md streamlit/src/kaoyan_agent/core/settings.py streamlit/src/kaoyan_agent/services/local_yolo_focus_recognizer.py streamlit/src/kaoyan_agent/ui/components/pomodoro_supervision_panel.py streamlit/tests/test_focus_supervision.py DESKTOP_YOLO_CAMERA_HANDOFF.md
```

提交并推送：

```powershell
git commit -m "fix(desktop): package YOLO runtime and grant camera access"
git push -u origin fix/desktop-yolo-camera
```

随后向仓库 `main` 分支发起 PR。不要使用 `git add .`，避免误加入本地数据或构建产物。

## 8. 可直接发给负责人的说明

> 负责人你好，Windows 桌面版摄像头、YOLO 以及“视觉证据：降级”问题已经修复。原问题包括 Electron 未处理摄像头权限、YOLO 不可用时 UI 阻断摄像头组件、运行配置可能写入只读安装目录、虚拟环境依赖开发机 Python，以及新版 MediaPipe/OpenCV API 不兼容。现在 YOLO 和 MediaPipe 姿态模型均随包内置，不在运行时下载；摄像头与模型状态已解耦；用户数据统一写入 `USER_DATA_PATH`；安装包携带独立 Python；构建自检会拒绝视觉降级状态。已通过 4 项 Electron 测试、25 项视觉督学测试、成品内 YOLO/视觉提取器实际加载检查、Windows 未安装版构建和正式 NSIS 安装包构建。当前安装包未配置代码签名，适合内部测试；请按本文第 5 节再进行一次真实摄像头人工验收。

<!-- START: 正式版本删掉以下内容 -->

## 9. 呼叫小火龙

> CJH 大王不好！
> 本少这边刚测试了最新 Windows 桌面包，摄像头能正常打开，画面也有了。但发现一个现象：UI 上提示 “视觉证据：降级”，实际测试人进画面和手机进画面，状态变化也不明显。
> 本少想确认这个 “视觉证据：降级” 是设计时做的提示 (只支持专注和分心两类)，还是模型实际加载出了问题导致推理能力不全？
> 麻烦看下，有结论直接回复。

<!-- END: 正式版本删掉以下内容 -->
