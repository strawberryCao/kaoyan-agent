"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const projectRoot = path.resolve(__dirname, "..");
const streamlitDir = path.join(projectRoot, "streamlit");
const pythonExecutable =
  process.platform === "win32"
    ? path.join(streamlitDir, ".python-runtime", "python.exe")
    : path.join(streamlitDir, ".venv", "bin", "python");
const venvSitePackages =
  process.platform === "win32"
    ? path.join(streamlitDir, ".venv", "Lib", "site-packages")
    : path.join(streamlitDir, ".venv", "lib", "python3", "site-packages");
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
  fail(`Self-contained Python runtime not found: ${pythonExecutable}. Run npm run preinstall first.`);
}
if (!fs.existsSync(venvSitePackages)) {
  fail(`Python dependencies not found: ${venvSitePackages}. Run npm run preinstall first.`);
}
if (!fs.existsSync(modelPath) || fs.statSync(modelPath).size < 1_000_000) {
  fail(`YOLO model is missing or incomplete: ${modelPath}`);
}

const pythonCheck = String.raw`
import importlib.util
import json
import sys
from pathlib import Path

required = ["cv2", "ultralytics", "av", "streamlit_webrtc", "torch"]
missing = [name for name in required if importlib.util.find_spec(name) is None]
if missing:
    raise SystemExit("missing Python modules: " + ", ".join(missing))

from kaoyan_agent.services.local_yolo_focus_recognizer import LocalYoloFocusRecognizer

recognizer = LocalYoloFocusRecognizer(
    None,
    person_weights_path=Path(sys.argv[1]),
    check_camera=False,
)
if not recognizer.is_fully_available():
    diagnostic = {
        "status_message": recognizer.status_message(),
        "coco": recognizer.debug.get("coco", {}),
        "mediapipe": recognizer.debug.get("mediapipe", {}),
        "opencv_face": recognizer.debug.get("opencv_face", {}),
    }
    raise SystemExit(
        "visual runtime is degraded: "
        + json.dumps(diagnostic, ensure_ascii=False, default=str)
    )
print("Desktop visual runtime OK: YOLO, camera dependencies, and local visual evidence are fully available.")
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
        venvSitePackages,
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
