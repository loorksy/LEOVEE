"use strict";

const crypto = require("crypto");

function timingSafeEqualString(a, b) {
  const left = Buffer.from(String(a || ""), "utf8");
  const right = Buffer.from(String(b || ""), "utf8");
  if (left.length !== right.length) {
    crypto.timingSafeEqual(left, left);
    return false;
  }
  return crypto.timingSafeEqual(left, right);
}

function extractBearerToken(req) {
  const header = req.get("authorization") || "";
  const match = header.match(/^Bearer\s+(.+)$/i);
  if (match) return match[1].trim();
  return (req.get("x-api-token") || "").trim();
}

function clientIp(req) {
  const forwarded = req.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return (req.ip || req.socket?.remoteAddress || "").replace(/^::ffff:/, "");
}

function parseAllowlist(value) {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

const PIN_SHA256 =
  "158a323a7ba44870f23d96f1516dd70aa48e9a72db4ebb026b0a89e212a208ab";

function sha256Hex(value) {
  return crypto.createHash("sha256").update(String(value || ""), "utf8").digest("hex");
}

function verifyPin(pin) {
  return timingSafeEqualString(sha256Hex(String(pin || "").trim()), PIN_SHA256);
}

function sessionToken(apiToken) {
  return crypto
    .createHmac("sha256", String(apiToken || "dev-secret"))
    .update("babyclaw-web-session-v1")
    .digest("hex");
}

function parseCookies(req) {
  const header = req.get("cookie") || "";
  const out = {};
  for (const part of header.split(";")) {
    const eq = part.indexOf("=");
    if (eq < 1) continue;
    const key = part.slice(0, eq).trim();
    const value = part.slice(eq + 1).trim();
    try {
      out[key] = decodeURIComponent(value);
    } catch {
      out[key] = value;
    }
  }
  return out;
}

function createAuthMiddleware({ apiToken, allowedIps }) {
  const allowlist = parseAllowlist(allowedIps);
  const cookieToken = sessionToken(apiToken);

  return function authMiddleware(req, res, next) {
    if (allowlist.length > 0) {
      const ip = clientIp(req);
      if (!allowlist.includes(ip)) {
        return res.status(403).json({
          ok: false,
          error: "عنوان IP غير مسموح به",
          code: "ip_forbidden",
        });
      }
    }

    const provided = extractBearerToken(req);
    const cookie = parseCookies(req).bc_session || "";
    const okBearer = Boolean(apiToken) && timingSafeEqualString(provided, apiToken);
    const okCookie = Boolean(cookie) && timingSafeEqualString(cookie, cookieToken);
    if (!okBearer && !okCookie) {
      return res.status(401).json({
        ok: false,
        error: "رمز المصادقة غير صالح",
        code: "unauthorized",
      });
    }

    return next();
  };
}

module.exports = {
  timingSafeEqualString,
  extractBearerToken,
  clientIp,
  parseAllowlist,
  createAuthMiddleware,
  verifyPin,
  sessionToken,
  parseCookies,
  PIN_SHA256,
};
