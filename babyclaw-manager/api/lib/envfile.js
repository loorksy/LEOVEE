"use strict";

const fs = require("fs");
const path = require("path");

const ALLOWED_KEYS = [
  "TELEGRAM_TOKEN",
  "TELEGRAM_USER_ID",
  "CLAUDE_CODE_OAUTH_TOKEN",
  "OPENAI_API_KEY",
  "TELEGRAM_CHAT_ID",
  "WORKSPACE",
];

const REQUIRED_KEYS = ["TELEGRAM_TOKEN", "TELEGRAM_USER_ID"];

function escapeEnvValue(value) {
  const text = String(value ?? "");
  if (text === "") return "";
  if (/[\s#"'$`\\]/.test(text)) {
    return `"${text.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
  }
  return text;
}

function pickAllowedUpdates(body) {
  const updates = {};
  for (const key of ALLOWED_KEYS) {
    if (Object.prototype.hasOwnProperty.call(body || {}, key)) {
      const raw = body[key];
      updates[key] = raw == null ? "" : String(raw).trim();
    }
  }
  return updates;
}

function validateUpdates(updates) {
  const missing = REQUIRED_KEYS.filter((key) => !updates[key]);
  if (missing.length > 0) {
    const error = new Error(`الحقول المطلوبة ناقصة: ${missing.join(", ")}`);
    error.code = "validation";
    error.status = 400;
    throw error;
  }
}

function upsertEnvContent(content, updates) {
  const lines = String(content || "").split(/\n/);
  const seen = new Set();
  const next = lines.map((line) => {
    const match = line.match(/^([A-Z0-9_]+)=(.*)$/);
    if (!match) return line;
    const key = match[1];
    if (!Object.prototype.hasOwnProperty.call(updates, key)) return line;
    seen.add(key);
    return `${key}=${escapeEnvValue(updates[key])}`;
  });

  for (const [key, value] of Object.entries(updates)) {
    if (seen.has(key)) continue;
    next.push(`${key}=${escapeEnvValue(value)}`);
  }

  let joined = next.join("\n");
  if (!joined.endsWith("\n")) joined += "\n";
  return joined;
}

function writeEnvFile(filePath, updates) {
  const absolute = path.resolve(filePath);
  const dir = path.dirname(absolute);
  fs.mkdirSync(dir, { recursive: true });

  let current = "";
  if (fs.existsSync(absolute)) {
    current = fs.readFileSync(absolute, "utf8");
    const stamp = new Date().toISOString().replace(/[:.]/g, "-");
    fs.copyFileSync(absolute, `${absolute}.bak-${stamp}`);
  }

  const next = upsertEnvContent(current, updates);
  const tmp = `${absolute}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, next, { encoding: "utf8", mode: 0o600 });
  fs.renameSync(tmp, absolute);
  fs.chmodSync(absolute, 0o600);
  const owner = process.env.BABYCLAW_USER || "babyclaw";
  try {
    const { execFileSync } = require("child_process");
    execFileSync("chown", [`${owner}:${owner}`, absolute]);
  } catch {
    // Running as the file owner already; ignore.
  }
  return { path: absolute, keys: Object.keys(updates) };
}

module.exports = {
  ALLOWED_KEYS,
  REQUIRED_KEYS,
  escapeEnvValue,
  pickAllowedUpdates,
  validateUpdates,
  upsertEnvContent,
  writeEnvFile,
};
