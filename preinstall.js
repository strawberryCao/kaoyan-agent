const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

function runCommand(command, args, options = {}) {
  console.log(`> ${command} ${args.join(" ")}`);
  const opts = { stdio: "inherit", ...options };
  return spawnSync(command, args, opts);
}

function checkCommand(command) {
  const result = spawnSync(command, ["--version"], { stdio: "ignore" });
  return !result.error && result.status === 0;
}

function stageWindowsPythonRuntime(streamlitDir) {
  if (process.platform !== "win32") {
    return;
  }

  const venvConfigPath = path.join(streamlitDir, ".venv", "pyvenv.cfg");
  if (!fs.existsSync(venvConfigPath)) {
    throw new Error(`Virtual environment config not found: ${venvConfigPath}`);
  }

  const config = fs.readFileSync(venvConfigPath, "utf8");
  const homeMatch = config.match(/^home\s*=\s*(.+)$/m);
  if (!homeMatch) {
    throw new Error(`Python runtime home is missing from ${venvConfigPath}`);
  }

  const runtimeSource = fs.realpathSync(homeMatch[1].trim());
  const sourcePython = path.join(runtimeSource, "python.exe");
  if (!fs.existsSync(sourcePython)) {
    throw new Error(`Python runtime is incomplete: ${sourcePython}`);
  }

  const runtimeTarget = path.join(streamlitDir, ".python-runtime");
  console.log(`Staging self-contained Python runtime from ${runtimeSource}`);
  fs.rmSync(runtimeTarget, { recursive: true, force: true });
  const systemRoot = process.env.SystemRoot || "C:\\Windows";
  const robocopy = path.join(systemRoot, "System32", "Robocopy.exe");
  const copyResult = spawnSync(
    robocopy,
    [
      runtimeSource,
      runtimeTarget,
      "/E",
      "/COPY:DAT",
      "/DCOPY:DAT",
      "/R:1",
      "/W:1",
      "/NFL",
      "/NDL",
      "/NJH",
      "/NJS",
      "/NP",
    ],
    { stdio: "inherit" },
  );
  if (copyResult.error || copyResult.status === null || copyResult.status >= 8) {
    throw (
      copyResult.error ||
      new Error(`Robocopy failed with code ${copyResult.status}`)
    );
  }

  if (!fs.existsSync(path.join(runtimeTarget, "python.exe"))) {
    throw new Error(`Failed to stage Python runtime at ${runtimeTarget}`);
  }
}

function main() {
  console.log("Checking for uv...");
  if (!checkCommand("uv")) {
    console.error(
      "Error: uv is not installed. Please install from https://docs.astral.sh/uv/",
    );
    process.exit(1);
  }
  console.log("uv found.");

  const streamlitDir = path.join(__dirname, "streamlit");
  if (!fs.existsSync(streamlitDir)) {
    console.error(`Error: ${streamlitDir} directory not found.`);
    process.exit(1);
  }
  process.chdir(streamlitDir);
  console.log(`Entering ${streamlitDir}`);

  const venvPath = path.join(streamlitDir, ".venv");
  if (!fs.existsSync(venvPath)) {
    console.log("Creating virtual environment (uv venv)...");
    const venvResult = runCommand("uv", ["venv"]);
    if (venvResult.status !== 0) {
      console.error("uv venv failed.");
      process.exit(1);
    }
    console.log("uv venv created.");
  } else {
    console.log("Virtual environment already exists, skipping uv venv.");
  }

  console.log("Syncing dependencies (uv sync)...");
  const syncResult = runCommand("uv", ["sync"]);
  if (syncResult.status !== 0) {
    console.error("uv sync failed.");
    process.exit(1);
  }
  console.log("uv sync completed.");
  stageWindowsPythonRuntime(streamlitDir);
}

main();
