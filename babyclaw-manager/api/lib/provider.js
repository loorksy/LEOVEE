"use strict";

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const { readEnvFile, writeEnvFile } = require("./envfile");

const PROVIDERS = ["claude", "openai", "omniroute"];

function normalizeProvider(value) {
  const provider = String(value || "claude").trim().toLowerCase();
  return PROVIDERS.includes(provider) ? provider : "claude";
}

function routingFor(values) {
  const provider = normalizeProvider(values.AI_PROVIDER);
  const omniUrl = String(values.OMNIROUTE_URL || "http://127.0.0.1:20128").replace(/\/+$/, "");
  const omniKey = String(values.OMNIROUTE_API_KEY || "local").trim();
  const customModel = String(values.AI_MODEL || "").trim();

  if (provider === "openai") {
    return {
      AI_PROVIDER: "openai",
      ANTHROPIC_BASE_URL: omniUrl,
      ANTHROPIC_AUTH_TOKEN: omniKey,
      ANTHROPIC_MODEL: customModel || "openai/gpt-4o-mini",
      CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY: "1",
    };
  }
  if (provider === "omniroute") {
    return {
      AI_PROVIDER: "omniroute",
      ANTHROPIC_BASE_URL: omniUrl,
      ANTHROPIC_AUTH_TOKEN: omniKey,
      ANTHROPIC_MODEL: customModel || "auto",
      CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY: "1",
    };
  }
  return {
    AI_PROVIDER: "claude",
    ANTHROPIC_BASE_URL: "",
    ANTHROPIC_AUTH_TOKEN: "",
    ANTHROPIC_MODEL: customModel,
    CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY: "",
  };
}

function writeClaudeSettings(homeDir, routing) {
  const dir = path.join(homeDir, ".claude");
  fs.mkdirSync(dir, { recursive: true });
  const env = {};
  for (const [key, value] of Object.entries(routing)) {
    if (!value || key === "AI_PROVIDER") continue;
    env[key] = value;
  }
  const file = path.join(dir, "settings.json");
  fs.writeFileSync(file, `${JSON.stringify({ env }, null, 2)}\n`, { mode: 0o600 });
  try {
    const owner = process.env.BABYCLAW_USER || "babyclaw";
    execFileSync("chown", ["-R", `${owner}:${owner}`, dir]);
  } catch {
    // ignore when not root
  }
}

function applyProvider(envFile, extra = {}) {
  const current = { ...readEnvFile(envFile), ...extra };
  const routing = routingFor(current);
  if (routing.AI_PROVIDER !== "claude" && process.env.SKIP_OMNIROUTE !== "1") {
    const script = path.resolve(__dirname, "..", "..", "scripts", "ensure-omniroute.sh");
    if (fs.existsSync(script)) {
      try {
        execFileSync("bash", [script], { timeout: 180000, stdio: "pipe" });
      } catch (error) {
        const wrapped = new Error(
          `تعذر تشغيل OmniRoute: ${error.stderr || error.message}`
        );
        wrapped.status = 500;
        wrapped.code = "omniroute_failed";
        throw wrapped;
      }
    }
  }
  const written = writeEnvFile(envFile, {
    AI_PROVIDER: routing.AI_PROVIDER,
    AI_MODEL: current.AI_MODEL || "",
    OMNIROUTE_URL: current.OMNIROUTE_URL || "http://127.0.0.1:20128",
    OMNIROUTE_API_KEY: current.OMNIROUTE_API_KEY || "",
    ...routing,
  });
  const homeDir = path.dirname(path.resolve(envFile));
  writeClaudeSettings(homeDir, routing);
  return { provider: routing.AI_PROVIDER, routing, written };
}

module.exports = {
  PROVIDERS,
  normalizeProvider,
  routingFor,
  writeClaudeSettings,
  applyProvider,
};
