import { apiUrl } from "@/api/config";
import { clearTokens, getAccessToken } from "@/api/authStore";

export class ApiError extends Error {
  readonly status: number;
  readonly code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type ApiFetchOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  headers?: Record<string, string>;
  auth?: boolean;
};

function buildQuery(query: ApiFetchOptions["query"]): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

async function parseErrorDetail(response: Response): Promise<{ message: string; code?: string }> {
  try {
    const data = (await response.json()) as { detail?: unknown };
    if (typeof data.detail === "string") {
      return { message: data.detail };
    }
    if (data.detail && typeof data.detail === "object") {
      const detail = data.detail as { message?: string; code?: string };
      return { message: detail.message ?? response.statusText, code: detail.code };
    }
  } catch {
    // Body was not JSON; fall through to status text.
  }
  return { message: response.statusText || `Request failed with ${response.status}` };
}

/** Thin fetch wrapper: attaches bearer auth, serializes JSON, normalizes errors. */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const { method = "GET", body, query, headers, auth = true } = options;
  const finalHeaders: Record<string, string> = { ...headers };
  if (body !== undefined) {
    finalHeaders["Content-Type"] = "application/json";
  }
  if (auth) {
    const token = getAccessToken();
    if (token) {
      finalHeaders.Authorization = `Bearer ${token}`;
    }
  }

  const response = await fetch(`${apiUrl(path)}${buildQuery(query)}`, {
    method,
    headers: finalHeaders,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!response.ok) {
    if (response.status === 401 && auth) {
      clearTokens();
    }
    const { message, code } = await parseErrorDetail(response);
    throw new ApiError(response.status, message, code);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}
