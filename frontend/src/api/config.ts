/** API base URL. Empty = same-origin (Caddy proxies `/api` and `/health`). */
export function getApiBase(): string {
  const raw = import.meta.env.VITE_API_URL;
  if (raw === undefined || raw === "") {
    return "";
  }
  return String(raw).replace(/\/$/, "");
}

/** Build a URL for an API or health path (must start with `/`). */
export function apiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const base = getApiBase();
  return base ? `${base}${normalized}` : normalized;
}
