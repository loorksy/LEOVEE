"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

const { createApp } = require("../server");
const { upsertEnvContent, pickAllowedUpdates, validateUpdates } = require("../lib/envfile");
const { timingSafeEqualString } = require("../lib/auth");

function startServer(app) {
  return new Promise((resolve) => {
    const server = http.createServer(app);
    server.listen(0, "127.0.0.1", () => {
      const { port } = server.address();
      resolve({ server, port });
    });
  });
}

async function request(port, method, urlPath, { token, body, ip } = {}) {
  const res = await fetch(`http://127.0.0.1:${port}${urlPath}`, {
    method,
    headers: {
      "content-type": "application/json",
      ...(token ? { authorization: `Bearer ${token}` } : {}),
      ...(ip ? { "x-forwarded-for": ip } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const json = await res.json();
  return { status: res.status, json };
}

test("upsertEnvContent updates existing keys and appends new ones", () => {
  const next = upsertEnvContent("FOO=old\nTELEGRAM_TOKEN=abc\n", {
    TELEGRAM_TOKEN: "new-token",
    TELEGRAM_USER_ID: "42",
  });
  assert.match(next, /TELEGRAM_TOKEN=new-token/);
  assert.match(next, /TELEGRAM_USER_ID=42/);
  assert.match(next, /FOO=old/);
});

test("pickAllowedUpdates ignores unknown keys", () => {
  const picked = pickAllowedUpdates({
    TELEGRAM_TOKEN: "t",
    PATH: "/evil",
    NODE_OPTIONS: "x",
  });
  assert.deepEqual(Object.keys(picked), ["TELEGRAM_TOKEN"]);
});

test("validateUpdates requires telegram fields", () => {
  assert.throws(() => validateUpdates({ TELEGRAM_TOKEN: "" }), /ناقصة/);
});

test("timingSafeEqualString rejects mismatched tokens", () => {
  assert.equal(timingSafeEqualString("abc", "abc"), true);
  assert.equal(timingSafeEqualString("abc", "abd"), false);
  assert.equal(timingSafeEqualString("abc", "ab"), false);
});

test("API health, deploy, and restart flow", async (t) => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "babyclaw-api-"));
  const envFile = path.join(tmpDir, ".env");
  const marker = path.join(tmpDir, "restarted.txt");
  fs.writeFileSync(envFile, "WORKSPACE=/tmp/ws\n");

  const app = createApp({
    apiToken: "test-token-1234567890",
    allowedIps: "",
    envFile,
    restartCommand: `touch '${marker}' && echo restarted`,
  });
  const { server, port } = await startServer(app);
  t.after(() => {
    server.close();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  const unauth = await request(port, "GET", "/api/health");
  assert.equal(unauth.status, 401);

  const health = await request(port, "GET", "/api/health", { token: "test-token-1234567890" });
  assert.equal(health.status, 200);
  assert.equal(health.json.ok, true);

  const publicHealth = await request(port, "GET", "/health");
  assert.equal(publicHealth.status, 200);

  const home = await request(port, "GET", "/");
  assert.equal(home.status, 200);
  assert.equal(home.json.ok, true);

  const htmlHome = await fetch(`http://127.0.0.1:${port}/`, {
    headers: { accept: "text/html" },
  });
  assert.equal(htmlHome.status, 200);
  assert.match(await htmlHome.text(), /أدخل رمز الدخول للمتابعة/);

  const badPin = await request(port, "POST", "/api/login", { body: { pin: "0000" } });
  assert.equal(badPin.status, 401);

  const loginRes = await fetch(`http://127.0.0.1:${port}/api/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ pin: "2026" }),
  });
  assert.equal(loginRes.status, 200);
  const cookie = String(loginRes.headers.get("set-cookie") || "");
  assert.match(cookie, /bc_session=/);

  const cookieHealth = await fetch(`http://127.0.0.1:${port}/api/health`, {
    headers: { cookie },
  });
  assert.equal(cookieHealth.status, 200);

  const deploy = await request(port, "POST", "/api/env", {
    token: "test-token-1234567890",
    body: {
      TELEGRAM_TOKEN: "bot-token",
      TELEGRAM_USER_ID: "99",
      OPENAI_API_KEY: "sk-test",
      PATH: "/should-not-write",
    },
  });
  assert.equal(deploy.status, 200, JSON.stringify(deploy.json));
  assert.equal(deploy.json.ok, true);
  const written = fs.readFileSync(envFile, "utf8");
  assert.match(written, /TELEGRAM_TOKEN=bot-token/);
  assert.match(written, /TELEGRAM_USER_ID=99/);
  assert.doesNotMatch(written, /PATH=\/should-not-write/);
  assert.equal(fs.existsSync(marker), true);

  const restart = await request(port, "POST", "/api/restart", {
    token: "test-token-1234567890",
  });
  assert.equal(restart.status, 200);
  assert.equal(restart.json.ok, true);
});

test("IP allowlist rejects unknown clients", async (t) => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "babyclaw-api-"));
  const app = createApp({
    apiToken: "allowlist-token",
    allowedIps: "203.0.113.10",
    envFile: path.join(tmpDir, ".env"),
    restartCommand: "true",
  });
  const { server, port } = await startServer(app);
  t.after(() => {
    server.close();
    fs.rmSync(tmpDir, { recursive: true, force: true });
  });

  const denied = await request(port, "GET", "/api/health", {
    token: "allowlist-token",
    ip: "198.51.100.20",
  });
  assert.equal(denied.status, 403);

  const allowed = await request(port, "GET", "/api/health", {
    token: "allowlist-token",
    ip: "203.0.113.10",
  });
  assert.equal(allowed.status, 200);
});
