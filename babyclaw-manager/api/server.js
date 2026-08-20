"use strict";

const fs = require("fs");
const path = require("path");
const express = require("express");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");

const { createAuthMiddleware } = require("./lib/auth");
const {
  pickAllowedUpdates,
  validateUpdates,
  writeEnvFile,
  ALLOWED_KEYS,
} = require("./lib/envfile");
const { restartAgent } = require("./lib/restart");

function loadDotEnv(filePath) {
  if (!fs.existsSync(filePath)) return;
  const text = fs.readFileSync(filePath, "utf8");
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 1) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1);
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (process.env[key] == null) process.env[key] = value;
  }
}

loadDotEnv(path.join(__dirname, ".env"));

function readConfig() {
  const apiToken = process.env.API_TOKEN || "";
  return {
    port: Number(process.env.PORT || 3000),
    apiToken,
    allowedIps: process.env.ALLOWED_IPS || "",
    envFile: process.env.ENV_FILE || "/home/babyclaw/.env",
    tmuxSession: process.env.TMUX_SESSION || "main",
    startScript: process.env.START_SCRIPT || "/home/babyclaw/start.sh",
    babyclawUser: process.env.BABYCLAW_USER || "babyclaw",
    restartScript: process.env.RESTART_SCRIPT || "",
    restartCommand: process.env.RESTART_COMMAND || "",
  };
}

function createApp(overrides = {}) {
  const config = { ...readConfig(), ...overrides };
  const app = express();

  app.set("trust proxy", 1);
  app.use(helmet({ contentSecurityPolicy: false }));
  app.use(express.json({ limit: "32kb" }));
  app.use(
    rateLimit({
      windowMs: 15 * 60 * 1000,
      max: 60,
      standardHeaders: true,
      legacyHeaders: false,
      message: {
        ok: false,
        error: "تم تجاوز حد الطلبات، حاول لاحقاً",
        code: "rate_limited",
      },
    })
  );

  app.get("/health", (_req, res) => {
    res.json({ ok: true, service: "babyclaw-env-api" });
  });

  const auth = createAuthMiddleware({
    apiToken: config.apiToken,
    allowedIps: config.allowedIps,
  });

  app.get("/api/health", auth, (_req, res) => {
    res.json({
      ok: true,
      service: "babyclaw-env-api",
      envFile: path.basename(config.envFile),
      allowedKeys: ALLOWED_KEYS,
    });
  });

  app.post("/api/env", auth, async (req, res) => {
    try {
      const updates = pickAllowedUpdates(req.body);
      if (Object.keys(updates).length === 0) {
        return res.status(400).json({
          ok: false,
          error: "لم يتم إرسال أي متغيرات مدعومة",
          code: "empty_body",
        });
      }
      validateUpdates(updates);
      const written = writeEnvFile(config.envFile, updates);
      const restarted = await restartAgent(config);
      return res.json({
        ok: true,
        message: "تم التحديث بنجاح",
        updatedKeys: written.keys,
        restarted: true,
        restart: restarted.stdout.trim(),
      });
    } catch (error) {
      return res.status(error.status || 500).json({
        ok: false,
        error: error.message || "فشل الاتصال بالخادم",
        code: error.code || "internal",
      });
    }
  });

  app.post("/api/restart", auth, async (_req, res) => {
    try {
      const restarted = await restartAgent(config);
      return res.json({
        ok: true,
        message: "تم إعادة تشغيل الوكيل",
        restart: restarted.stdout.trim(),
      });
    } catch (error) {
      return res.status(error.status || 500).json({
        ok: false,
        error: error.message || "فشل إعادة تشغيل الوكيل",
        code: error.code || "internal",
      });
    }
  });

  app.use((req, res) => {
    res.status(404).json({ ok: false, error: "المسار غير موجود", code: "not_found" });
  });

  return app;
}

if (require.main === module) {
  if (!process.env.API_TOKEN) {
    throw new Error("API_TOKEN is required");
  }
  const app = createApp();
  const port = Number(process.env.PORT || 3000);
  const host = process.env.BIND_HOST || "127.0.0.1";
  app.listen(port, host, () => {
    console.log(`babyclaw-env-api listening on ${host}:${port}`);
  });
}

module.exports = { createApp, readConfig };
