"use strict";

const { execFile } = require("child_process");
const fs = require("fs");
const path = require("path");

function runCommand(command, args, timeoutMs = 20000) {
  return new Promise((resolve, reject) => {
    execFile(
      command,
      args,
      { timeout: timeoutMs, windowsHide: true },
      (error, stdout, stderr) => {
        if (error) {
          const wrapped = new Error(
            stderr?.toString().trim() || error.message || "فشل إعادة تشغيل الوكيل"
          );
          wrapped.code = "restart_failed";
          wrapped.status = 500;
          wrapped.stdout = stdout?.toString() || "";
          wrapped.stderr = stderr?.toString() || "";
          reject(wrapped);
          return;
        }
        resolve({
          stdout: stdout?.toString() || "",
          stderr: stderr?.toString() || "",
        });
      }
    );
  });
}

function resolveRestartScript(explicitPath) {
  if (explicitPath && fs.existsSync(explicitPath)) return explicitPath;
  const sibling = path.resolve(__dirname, "..", "..", "scripts", "restart-agent.sh");
  if (fs.existsSync(sibling)) return sibling;
  const local = path.resolve(__dirname, "..", "restart-agent.sh");
  if (fs.existsSync(local)) return local;
  return explicitPath || sibling;
}

async function restartAgent(config) {
  if (config.restartCommand) {
    return runCommand("bash", ["-lc", config.restartCommand]);
  }

  const script = resolveRestartScript(config.restartScript);
  if (!script || !fs.existsSync(script)) {
    const error = new Error("سكربت إعادة التشغيل غير موجود");
    error.status = 500;
    error.code = "restart_script_missing";
    throw error;
  }

  return runCommand("bash", [
    script,
    config.tmuxSession || "main",
    config.startScript || "/home/babyclaw/start.sh",
    config.babyclawUser || "babyclaw",
  ]);
}

module.exports = {
  runCommand,
  resolveRestartScript,
  restartAgent,
};
