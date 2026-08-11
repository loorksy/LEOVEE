/** Minimal JWT storage for the browser client (§4 auth). */

const ACCESS_TOKEN_KEY = "leovee.access_token";
const REFRESH_TOKEN_KEY = "leovee.refresh_token";

export type StoredTokens = {
  access_token: string;
  refresh_token: string;
};

function hasLocalStorage(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

export function getAccessToken(): string | null {
  if (!hasLocalStorage()) return null;
  return window.localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  if (!hasLocalStorage()) return null;
  return window.localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(tokens: StoredTokens): void {
  if (!hasLocalStorage()) return;
  window.localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh_token);
  window.dispatchEvent(new Event("leovee-auth-changed"));
}

export function clearTokens(): void {
  if (!hasLocalStorage()) return;
  window.localStorage.removeItem(ACCESS_TOKEN_KEY);
  window.localStorage.removeItem(REFRESH_TOKEN_KEY);
  window.dispatchEvent(new Event("leovee-auth-changed"));
}

export function isAuthenticated(): boolean {
  return getAccessToken() !== null;
}

export const AUTH_CHANGED_EVENT = "leovee-auth-changed";
