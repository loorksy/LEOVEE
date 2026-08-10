import { getApiBase } from "@/api/config";
import { getAccessToken } from "@/api/authStore";

export type StreamChannel = "candles" | "annotations" | "notifications";

export type BuildStreamUrlParams = {
  token: string;
  symbols?: string[];
  channels?: StreamChannel[];
  workspaceId?: string;
};

/** Build the `/ws/v1/stream` URL, deriving ws/wss from the API base or current origin. */
export function buildStreamUrl(params: BuildStreamUrlParams): string {
  const base = getApiBase();
  let origin: string;
  if (base) {
    origin = base.replace(/^http/, "ws");
  } else if (typeof window !== "undefined" && window.location) {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    origin = `${protocol}//${window.location.host}`;
  } else {
    origin = "ws://localhost";
  }

  const search = new URLSearchParams();
  search.set("token", params.token);
  if (params.symbols?.length) {
    search.set("symbols", params.symbols.join(","));
  }
  if (params.channels?.length) {
    search.set("channels", params.channels.join(","));
  }
  if (params.workspaceId) {
    search.set("workspace_id", params.workspaceId);
  }
  return `${origin}/ws/v1/stream?${search.toString()}`;
}

/** Convenience: build the stream URL using the currently stored access token. */
export function buildAuthenticatedStreamUrl(
  params: Omit<BuildStreamUrlParams, "token">,
): string | null {
  const token = getAccessToken();
  if (!token) return null;
  return buildStreamUrl({ ...params, token });
}
