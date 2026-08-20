"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("http");

const {
  cookieHeader,
  connectionsFrom,
  upsertOpenAiProvider,
} = require("../lib/omniroute");

test("cookieHeader keeps session cookies from Set-Cookie", () => {
  assert.match(
    cookieHeader("bc=1; Path=/; HttpOnly, other=2; Path=/"),
    /bc=1/
  );
});

test("connectionsFrom reads several OmniRoute list shapes", () => {
  assert.equal(connectionsFrom({ connections: [{ provider: "openai" }] }).length, 1);
  assert.equal(connectionsFrom([{ provider: "openai" }]).length, 1);
});

test("upsertOpenAiProvider logs in and creates an OpenAI connection", async (t) => {
  const calls = [];
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
    });
    req.on("end", () => {
      calls.push({ method: req.method, url: req.url, body });
      res.setHeader("content-type", "application/json");
      if (req.url === "/api/auth/login") {
        res.setHeader("set-cookie", "omni=session; Path=/; HttpOnly");
        res.end(JSON.stringify({ token: "jwt-1" }));
        return;
      }
      if (req.method === "GET" && req.url === "/api/providers") {
        res.end(JSON.stringify({ connections: [] }));
        return;
      }
      if (req.method === "POST" && req.url === "/api/providers") {
        res.statusCode = 201;
        res.end(JSON.stringify({ id: "p1", provider: "openai" }));
        return;
      }
      res.statusCode = 404;
      res.end("{}");
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const { port } = server.address();
  const result = await upsertOpenAiProvider({
    baseUrl: `http://127.0.0.1:${port}`,
    apiKey: "sk-test",
    passwords: ["secret"],
  });
  assert.equal(result.ok, true);
  assert.equal(result.updated, false);
  assert.equal(calls[0].url, "/api/auth/login");
  assert.equal(calls[2].method, "POST");
  assert.match(calls[2].body, /sk-test/);
});

test("upsertOpenAiProvider patches an existing OpenAI connection", async (t) => {
  const server = http.createServer((req, res) => {
    let body = "";
    req.on("data", (chunk) => {
      body += chunk;
    });
    req.on("end", () => {
      res.setHeader("content-type", "application/json");
      if (req.url === "/api/auth/login") {
        res.end(JSON.stringify({ token: "jwt-1" }));
        return;
      }
      if (req.method === "GET" && req.url === "/api/providers") {
        res.end(JSON.stringify({ connections: [{ id: "abc", provider: "openai" }] }));
        return;
      }
      if (req.method === "PATCH" && req.url === "/api/providers/abc") {
        res.end(JSON.stringify({ id: "abc" }));
        return;
      }
      res.statusCode = 404;
      res.end("{}");
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  t.after(() => server.close());
  const { port } = server.address();
  const result = await upsertOpenAiProvider({
    baseUrl: `http://127.0.0.1:${port}`,
    apiKey: "sk-new",
    passwords: ["secret"],
  });
  assert.equal(result.updated, true);
});
