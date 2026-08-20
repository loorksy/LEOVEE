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

function createAuthMiddleware({ apiToken, allowedIps }) {
  const allowlist = parseAllowlist(allowedIps);

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
    if (!apiToken || !timingSafeEqualString(provided, apiToken)) {
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
};
