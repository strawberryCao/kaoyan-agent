const { app, BrowserWindow, dialog } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");

let mainWindow;
let streamlitProcess = null;

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

  streamlitProcess = spawn(pythonExecutable, [
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
  ]);

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
