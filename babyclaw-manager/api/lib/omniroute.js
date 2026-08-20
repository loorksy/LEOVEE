"use strict";

const fs = require("fs");

const DEFAULT_BASE_URL = "http://127.0.0.1:20128";
const OPENAI_URL = "https://api.openai.com/v1";

function readEnvValue(filePath, key) {
  if (!filePath || !fs.existsSync(filePath)) return "";
  const prefix = `${key}=`;
  for (const line of fs.readFileSync(filePath, "utf8").split("\n")) {
    if (!line.startsWith(prefix)) continue;
    let value = line.slice(prefix.length);
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    return value.trim();
  }
  return "";
}

function cookieHeader(setCookie) {
  const raw = Array.isArray(setCookie) ? setCookie.join("\n") : String(setCookie || "");
  if (!raw) return "";
  return raw
    .split(/[\n,]/)
    .map((part) => part.trim())
    .map((part) => part.split(";")[0].trim())
    .filter((part) => part.includes("=") && !/^(Max-Age|Path|Expires|HttpOnly|Secure|SameSite)=/i.test(part))
    .join("; ");
}

function authHeaders(session) {
  const headers = { "content-type": "application/json" };
  if (session.cookie) headers.cookie = session.cookie;
  if (session.token) headers.authorization = `Bearer ${session.token}`;
  if (session.csrf) headers["x-csrf-token"] = session.csrf;
  return headers;
}

function connectionsFrom(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.connections)) return payload.connections;
  if (Array.isArray(payload?.providers)) return payload.providers;
  if (Array.isArray(payload?.data)) return payload.data;
  return [];
}

async function login(baseUrl, password, fetchFn = fetch) {
  const res = await fetchFn(`${baseUrl}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ password }),
  });
  const json = await res.json().catch(() => ({}));
  const token = json.token || json.accessToken || json.jwt || "";
  const csrf = json.csrfToken || json.csrf || "";
  return {
    ok: res.ok,
    status: res.status,
    cookie: cookieHeader(res.headers.get("set-cookie")),
    token,
    csrf,
    json,
  };
}

async function loginWithCandidates(baseUrl, passwords, fetchFn = fetch) {
  let last = { ok: false, status: 0 };
  for (const password of passwords.filter(Boolean)) {
    last = await login(baseUrl, password, fetchFn);
    if (last.ok) return last;
  }
  return last;
}

function passwordCandidates(omniEnvFile) {
  return [
    readEnvValue(omniEnvFile, "INITIAL_PASSWORD"),
    "CHANGEME",
    "123456",
  ];
}

async function upsertOpenAiProvider({
  baseUrl = DEFAULT_BASE_URL,
  apiKey,
  omniEnvFile = "/opt/leovee/omniroute.env",
  passwords,
  fetchFn = fetch,
} = {}) {
  const key = String(apiKey || "").trim();
  if (!key) return { ok: true, skipped: true };

  const session = await loginWithCandidates(
    baseUrl,
    passwords || passwordCandidates(omniEnvFile),
    fetchFn
  );
  if (!session.ok) {
    const error = new Error("تعذر تسجيل الدخول إلى OmniRoute لربط مفتاح OpenAI");
    error.status = 502;
    error.code = "omniroute_auth";
    throw error;
  }

  const headers = authHeaders(session);
  const listRes = await fetchFn(`${baseUrl}/api/providers`, { headers });
  const listJson = await listRes.json().catch(() => ({}));
  const existing = connectionsFrom(listJson).find(
    (item) => String(item.provider || item.type || "").toLowerCase() === "openai"
  );

  const body = {
    provider: "openai",
    name: "OpenAI",
    url: OPENAI_URL,
    apiKey: key,
    isActive: true,
  };

  const target = existing?.id
    ? `${baseUrl}/api/providers/${existing.id}`
    : `${baseUrl}/api/providers`;
  const method = existing?.id ? "PATCH" : "POST";
  const res = await fetchFn(target, {
    method,
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok && res.status !== 409) {
    const error = new Error("تعذر ربط مفتاح OpenAI داخل OmniRoute");
    error.status = 502;
    error.code = "omniroute_provider";
    throw error;
  }
  return { ok: true, updated: Boolean(existing?.id) };
}

module.exports = {
  DEFAULT_BASE_URL,
  OPENAI_URL,
  readEnvValue,
  cookieHeader,
  connectionsFrom,
  login,
  loginWithCandidates,
  passwordCandidates,
  upsertOpenAiProvider,
};
