"use strict";

const {
  app,
  BrowserWindow,
  dialog,
  session,
  Menu,
  shell,
} = require("electron");
const { spawn, execSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const {
  installCameraPermissionHandlers,
  resolveWritableConfigEnv,
} = require("./desktop_runtime");

app.commandLine.appendSwitch('gtk-version', '4');

let mainWindow;
let streamlitProcess = null;

const userDataPath = app.getPath("userData");
const configPath = path.join(userDataPath, "config.json");

const defaultConfig = {
  llmApiKey: "your_api_key_here",
  llmBaseUrl: "https://api.deepseek.com/v1",
  llmModel: "deepseek-v4-pro",
  embeddingProvider: "siliconflow",
  embeddingModel: "BAAI/bge-m3",
  embeddingApiKey: "",
  embeddingBaseUrl: "https://api.siliconflow.cn/v1",
  embeddingBatchSize: 16,
  embeddingTimeoutSeconds: 20,
  graphBackend: "neo4j",
  neo4jUri: "bolt://localhost:7687",
  neo4jUsername: "neo4j",
  neo4jPassword: "",
  graphSyncRawEvents: false,
  yoloFocusCameraId: 0,
  yoloFocusConfidenceThreshold: 0.5,
  yoloFocusInferenceFps: 3,
  yoloPersonConfidenceThreshold: 0.35,
  focusPhoneConfidenceThreshold: 0.35,
  focusVisualEvidenceThreshold: 0.55,
  focusPresenceFocusConfidenceThreshold: 0.65,
  yoloAwayConfirmSeconds: 10,
  yoloBehaviorWindowSeconds: 3,
  focusReportMinCoverage: 0.8,
};

function camelToScreamingSnake(str) {
  return str.replace(/([a-z])([A-Z])/g, "$1_$2").toUpperCase();
}

function configToEnv(config) {
  const env = {};
  for (const key of Object.keys(config)) {
    const envKey = camelToScreamingSnake(key);
    let value = config[key];
    if (typeof value === "boolean") {
      value = value ? "true" : "false";
    } else if (value !== undefined && value !== null) {
      value = String(value);
    }
    env[envKey] = value;
  }
  return env;
}

function getResourcePath(relativePath) {
  let basePath;
  if (app.isPackaged) {
    basePath = path.join(process.resourcesPath);
  } else {
    basePath = path.join(__dirname);
  }
  return path.join(basePath, relativePath);
}

function showErrorDialog(title, message) {
  dialog.showErrorBox(title, message);
}

function getPythonInfo() {
  const streamlitResourcePath = getResourcePath("streamlit");
  const isWin = process.platform === "win32";

  const embeddedPython = path.join(
    streamlitResourcePath,
    ".python-runtime",
    isWin ? "python.exe" : "python",
  );
  if (fs.existsSync(embeddedPython)) {
    return { executable: embeddedPython, type: "embedded" };
  }

  const venvRoot = path.join(streamlitResourcePath, ".venv");
  const venvBinDir = isWin ? "Scripts" : "bin";
  const venvPython = path.join(
    venvRoot,
    venvBinDir,
    isWin ? "python.exe" : "python",
  );
  if (fs.existsSync(venvPython)) {
    return { executable: venvPython, type: "venv", root: venvRoot };
  }

  return { executable: "python", type: "system" };
}

function getSitePackages(pythonExe) {
  try {
    const cmd = `"${pythonExe}" -c "import sysconfig; print(sysconfig.get_path('purelib'))"`;
    const sitePackages = execSync(cmd, { encoding: "utf-8" }).trim();
    if (sitePackages && fs.existsSync(sitePackages)) {
      return sitePackages;
    }
    console.warn(`Resolved site-packages path does not exist: ${sitePackages}`);
    return null;
  } catch (err) {
    console.warn("Failed to get site-packages via sysconfig:", err.message);
    return null;
  }
}

function guessSitePackages(venvRoot, isWin) {
  if (isWin) {
    const winPath = path.join(venvRoot, "Lib", "site-packages");
    return fs.existsSync(winPath) ? winPath : null;
  } else {
    const libDir = path.join(venvRoot, "lib");
    if (fs.existsSync(libDir)) {
      const entries = fs.readdirSync(libDir);
      const pyDir = entries.find((e) => e.startsWith("python3."));
      if (pyDir) {
        const guessed = path.join(libDir, pyDir, "site-packages");
        return fs.existsSync(guessed) ? guessed : null;
      }
    }
    return null;
  }
}

function resolveSitePackages(pythonInfo) {
  const isWin = process.platform === "win32";
  let sitePackages = null;

  if (pythonInfo.type === "venv" && pythonInfo.root) {
    sitePackages = getSitePackages(pythonInfo.executable);
    if (!sitePackages) {
      sitePackages = guessSitePackages(pythonInfo.root, isWin);
    }
  } else if (pythonInfo.type === "embedded") {
    sitePackages = getSitePackages(pythonInfo.executable);
    if (!sitePackages) {
      const embeddedDir = path.dirname(pythonInfo.executable);
      const possibleVenv = path.join(embeddedDir, "..", ".venv");
      if (fs.existsSync(possibleVenv)) {
        sitePackages = guessSitePackages(possibleVenv, isWin);
      }
    }
  } else {
    sitePackages = getSitePackages(pythonInfo.executable);
  }

  return sitePackages;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1368,
    height: 912,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  mainWindow.loadURL("http://localhost:8501");

  mainWindow.webContents.on(
    "did-fail-load",
    (event, errorCode, errorDescription) => {
      showErrorDialog(
        "Loading Failed",
        `Failed to load Streamlit UI.\nError: ${errorDescription} (${errorCode})`,
      );
    },
  );

  mainWindow.on("closed", () => {
    mainWindow = null;
    if (streamlitProcess) {
      streamlitProcess.kill();
      streamlitProcess = null;
    }
  });
}

function buildApplicationMenu() {
  const template = [
    {
      label: "文件",
      submenu: [
        {
          label: "配置文件",
          click() {
            shell.openPath(configPath).catch((err) => {
              dialog.showErrorBox("打开失败", err.message);
            });
          },
        },
        {
          label: "还原文件",
          click() {
            dialog
              .showMessageBox({
                type: "question",
                message:
                  "此操作将恢复默认配置，当前配置将被覆盖，确定要继续吗？",
                buttons: ["取消", "确定"],
                defaultId: 0,
                cancelId: 0,
              })
              .then(({ response }) => {
                if (response === 1) {
                  try {
                    fs.writeFileSync(
                      configPath,
                      JSON.stringify(defaultConfig, null, 2),
                      "utf8",
                    );
                    dialog
                      .showMessageBox({
                        type: "info",
      
                        message: "已还原文件，重启应用以使新配置生效。",
                      })
                      .then(() => {
                        app.exit(0);
                      });
                  } catch (err) {
                    dialog.showErrorBox("还原失败", err.message);
                  }
                }
              });
          },
        },
        { type: "separator" },
        { label: "退出", role: "quit" },
      ],
    },
    {
      label: "编辑",
      submenu: [
        { label: "撤销", role: "undo" },
        { label: "重做", role: "redo" },
        { type: "separator" },
        { label: "剪切", role: "cut" },
        { label: "复制", role: "copy" },
        { label: "粘贴", role: "paste" },
        { label: "删除", role: "delete" },
        { type: "separator" },
        { label: "全选", role: "selectAll" },
      ],
    },
    {
      label: "视图",
      submenu: [
        { label: "重新加载", role: "reload" },
        { label: "强制重新加载", role: "forceReload" },
        { label: "开发者工具", role: "toggleDevTools" },
        { type: "separator" },
        { label: "实际大小", role: "resetZoom" },
        { label: "放大", role: "zoomIn" },
        { label: "缩小", role: "zoomOut" },
        { type: "separator" },
        { label: "全屏", role: "togglefullscreen" },
      ],
    },
    {
      label: "窗口",
      submenu: [
        { label: "最小化", role: "minimize" },
        { label: "关闭", role: "close" },
        ...(process.platform === "darwin"
          ? [{ label: "前置全部", role: "front" }]
          : []),
      ],
    },
  ];

  if (process.platform === "darwin") {
    template.unshift({
      label: app.name,
      submenu: [{ label: "退出", role: "quit" }],
    });
  }

  return Menu.buildFromTemplate(template);
}

app.on("ready", () => {
  const menu = buildApplicationMenu();
  Menu.setApplicationMenu(menu);

  installCameraPermissionHandlers(session.defaultSession);

  if (!fs.existsSync(configPath)) {
    fs.writeFileSync(
      configPath,
      JSON.stringify(defaultConfig, null, 2),
      "utf8",
    );
  }

  const config = JSON.parse(fs.readFileSync(configPath, { encoding: "utf8" }));
  const appPyPath = getResourcePath(path.join("streamlit", "app.py"));
  const yoloConfigPath = path.join(userDataPath, "data", "ultralytics");
  const configEnvironment = resolveWritableConfigEnv(
    configToEnv(config),
    userDataPath,
  );

  fs.mkdirSync(yoloConfigPath, { recursive: true });

  if (!fs.existsSync(appPyPath)) {
    showErrorDialog(
      "File Not Found",
      `Cannot find Streamlit entry file:\n${appPyPath}\n\nPlease ensure the application is installed correctly.`,
    );
    app.quit();
    return;
  }

  const pythonInfo = getPythonInfo();
  const pythonExecutable = pythonInfo.executable;
  console.log(`Using Python: ${pythonExecutable} (type: ${pythonInfo.type})`);

  let venvSitePackagesPath = resolveSitePackages(pythonInfo);
  if (venvSitePackagesPath) {
    console.log(`Resolved site-packages: ${venvSitePackagesPath}`);
  } else {
    console.warn(
      "Could not locate site-packages; PYTHONPATH may be incomplete.",
    );
  }

  console.log(
    `Starting Streamlit: ${pythonExecutable} -m streamlit run ${appPyPath} --server.headless true --server.enableCORS false --server.enableXsrfProtection false`,
  );

  const env = {
    ...process.env,
    ...configEnvironment,
    USER_DATA_PATH: userDataPath,
    YOLO_CONFIG_DIR: yoloConfigPath,
  };
  if (venvSitePackagesPath) {
    env.PYTHONPATH = [venvSitePackagesPath, process.env.PYTHONPATH]
      .filter(Boolean)
      .join(path.delimiter);
  }

  streamlitProcess = spawn(
    pythonExecutable,
    [
      "-m",
      "streamlit",
      "run",
      appPyPath,
      "--server.headless",
      "true",
      "--server.enableCORS",
      "false",
      "--server.enableXsrfProtection",
      "false",
    ],
    { env },
  );

  streamlitProcess.stdout.on("data", (data) => {
    const output = data.toString();
    console.log(`[Streamlit stdout]: ${output}`);

    if (output.includes("You can now view your Streamlit app")) {
      if (!mainWindow) {
        createWindow();
      }
    }
  });

  streamlitProcess.stderr.on("data", (data) => {
    console.error(`[Streamlit stderr]: ${data}`);
  });

  streamlitProcess.on("error", (err) => {
    console.error("Failed to start Streamlit process:", err);
    showErrorDialog(
      "Startup Error",
      `Unable to start Streamlit process.\n\n${err.message}`,
    );
    app.quit();
  });

  streamlitProcess.on("exit", (code) => {
    console.log(`Streamlit process exited with code: ${code}`);
    if (code !== 0 && code !== null) {
      showErrorDialog(
        "Streamlit Crashed",
        `Streamlit process exited unexpectedly with code ${code}.\nThe application will now close.`,
      );
    }
    if (mainWindow) {
      mainWindow.close();
    }
    app.quit();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
