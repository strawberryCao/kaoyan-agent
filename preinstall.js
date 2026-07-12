const { execSync, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const os = require("os");

function runCommand(command, args, options = {}) {
  console.log(`> ${command} ${args.join(" ")}`);
  const opts = { stdio: "inherit", ...options };
  return spawnSync(command, args, opts);
}

function checkCommand(command) {
  try {
    const which = os.platform() === "win32" ? "where" : "which";
    execSync(`${which} ${command}`, { stdio: "ignore" });
    return true;
  } catch {
    return false;
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
}

main();
