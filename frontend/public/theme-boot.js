// Applied before first paint so there is no flash of the wrong theme — the
// same storage key and default src/api/themeStore.ts reads/writes on every
// toggle. Dark is the designed case (a trading terminal read at night), so
// an unset preference resolves to dark rather than following the OS.
//
// A static file under public/, not an inline <script> in index.html: the
// production CSP (docker/caddy/Caddyfile.prod) is script-src 'self' with no
// 'unsafe-inline', and that policy is mirrored on the dev server
// (vite.config.ts) so a CSP violation shows up here, in a browser, rather
// than only in production.
(function () {
  try {
    var stored = localStorage.getItem("leovee-theme");
    var dark = stored ? stored === "dark" : true;
    document.documentElement.classList.toggle("dark", dark);
  } catch (e) {
    document.documentElement.classList.add("dark");
  }
})();
