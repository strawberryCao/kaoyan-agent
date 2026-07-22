"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync, execSync } = require("child_process");

function getResourcePath(relativePath) {
  const projectRoot = path.resolve(__dirname, "..");
  return path.join(projectRoot, relativePath);
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

  const systemPython = isWin ? "python.exe" : "python";
  try {
    const whichCmd = isWin ? "where" : "which";
    const result = execSync(`${whichCmd} ${systemPython}`, {
      encoding: "utf8",
      shell: true,
    });
    if (result.trim()) return { executable: systemPython, type: "system" };
  } catch (_) {}

  return { executable: systemPython, type: "system" };
}

function getSitePackages(pythonExe) {
  try {
    const cmd = `"${pythonExe}" -c "import sysconfig; print(sysconfig.get_path('purelib'))"`;
    const sitePackages = execSync(cmd, {
      encoding: "utf-8",
      shell: true,
    }).trim();
    if (sitePackages && fs.existsSync(sitePackages)) return sitePackages;
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
    if (!sitePackages) sitePackages = guessSitePackages(pythonInfo.root, isWin);
  } else if (pythonInfo.type === "embedded") {
    const embeddedDir = path.dirname(pythonInfo.executable);
    const possibleVenv = path.join(embeddedDir, "..", ".venv");
    if (fs.existsSync(possibleVenv)) {
      sitePackages = guessSitePackages(possibleVenv, isWin);
      if (sitePackages)
        console.log("Using .venv site-packages for embedded Python.");
    }
    if (!sitePackages) {
      sitePackages = getSitePackages(pythonInfo.executable);
    }
  } else {
    sitePackages = getSitePackages(pythonInfo.executable);
  }

  if (!sitePackages && isWin) {
    const streamlitResourcePath = getResourcePath("streamlit");
    const fallbackVenv = path.join(
      streamlitResourcePath,
      ".venv",
      "Lib",
      "site-packages",
    );
    if (fs.existsSync(fallbackVenv)) {
      console.warn("Using fallback Windows site-packages path:", fallbackVenv);
      sitePackages = fallbackVenv;
    }
  }

  return sitePackages;
}

const projectRoot = path.resolve(__dirname, "..");
const streamlitDir = path.join(projectRoot, "streamlit");

const pythonInfo = getPythonInfo();
const pythonExecutable = pythonInfo.executable;
console.log(`Using Python: ${pythonExecutable} (type: ${pythonInfo.type})`);

const sitePackagesPath = resolveSitePackages(pythonInfo);
if (!sitePackagesPath) {
  console.error(
    "Could not resolve site-packages. Please ensure Python dependencies are installed.",
  );
  process.exit(1);
}
console.log(`Resolved site-packages: ${sitePackagesPath}`);

const modelPath = path.join(
  streamlitDir,
  "models",
  "person_presence",
  "yolov8n.pt",
);

const runtimeTempRoot = path.join(projectRoot, "tmp");

function fail(message) {
  console.error(`Desktop runtime check failed: ${message}`);
  process.exit(1);
}

if (!fs.existsSync(pythonExecutable)) {
  fail(
    `Self-contained Python runtime not found: ${pythonExecutable}. Run npm run preinstall first.`,
  );
}

if (!fs.existsSync(sitePackagesPath)) {
  fail(
    `Python dependencies not found: ${sitePackagesPath}. Run npm run preinstall first.`,
  );
}

if (!fs.existsSync(modelPath) || fs.statSync(modelPath).size < 1_000_000) {
  fail(`YOLO model is missing or incomplete: ${modelPath}`);
}

const pythonCheck = String.raw`
import importlib.util
import sys

required = ["cv2", "ultralytics", "av", "streamlit_webrtc", "torch"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit("missing Python modules: " + ", ".join(missing))

from ultralytics import YOLO

model = YOLO(sys.argv[1])
labels = {
    str(value).strip().lower().replace("-", "_").replace(" ", "_")
    for value in (getattr(model, "names", {}) or {}).values()
}
missing_labels = {"person", "cell_phone"} - labels
if missing_labels:
    raise SystemExit("YOLO model lacks required labels: " + ", ".join(sorted(missing_labels)))
print("Desktop visual runtime OK: person/cell_phone model and camera dependencies are available.")
`;

fs.mkdirSync(runtimeTempRoot, { recursive: true });
const runtimeConfigDir = fs.mkdtempSync(
  path.join(runtimeTempRoot, "desktop-yolo-check-"),
);

let result;
try {
  result = spawnSync(pythonExecutable, ["-c", pythonCheck, modelPath], {
    cwd: streamlitDir,
    encoding: "utf8",
    env: {
      ...process.env,
      PYTHONPATH: [
        path.join(streamlitDir, "src"),
        sitePackagesPath,
        process.env.PYTHONPATH,
      ]
        .filter(Boolean)
        .join(path.delimiter),
      YOLO_CONFIG_DIR: runtimeConfigDir,
    },
  });
} finally {
  fs.rmSync(runtimeConfigDir, { recursive: true, force: true });
}

if (result.stdout) {
  process.stdout.write(result.stdout);
}
if (result.stderr) {
  process.stderr.write(result.stderr);
}
if (result.error) {
  fail(result.error.message);
}
if (result.status !== 0) {
  fail(`Python validation exited with code ${result.status}.`);
}
