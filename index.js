const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

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
  yoloFocusWeightsPath: "",
  yoloFocusCameraId: 0,
  yoloFocusConfidenceThreshold: 0.5,
  yoloFocusInferenceFps: 3,
  yoloPersonWeightsPath: "models/person_presence/yolov8n.pt",
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

app.on("ready", () => {
  if (!fs.existsSync(configPath)) {
    fs.writeFileSync(
      configPath,
      JSON.stringify(defaultConfig, null, 2),
      "utf8",
    );
  }

  const config = JSON.parse(fs.readFileSync(configPath, { encoding: "utf8" }));
  const appPyPath = getResourcePath(path.join("streamlit", "app.py"));

  if (!fs.existsSync(appPyPath)) {
    showErrorDialog(
      "File Not Found",
      `Cannot find Streamlit entry file:\n${appPyPath}\n\nPlease ensure the application is installed correctly.`,
    );
    app.quit();
    return;
  }

  let pythonExecutable;
  const venvPath = getResourcePath(
    path.join("streamlit", ".venv", "Scripts", "python.exe"),
  );

  if (fs.existsSync(venvPath)) {
    pythonExecutable = venvPath;
    console.log("Using packaged Python:", pythonExecutable);
  } else {
    pythonExecutable = "python";
    console.log("Using system Python");
  }

  console.log(
    `Starting Streamlit: ${pythonExecutable} -m streamlit run ${appPyPath} --server.headless true --server.enableCORS false --server.enableXsrfProtection false`,
  );

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
    {
      env: {
        ...process.env,
        ...configToEnv(config),
        USER_DATA_PATH: userDataPath,
      },
    },
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
