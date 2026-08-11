import { apiFetch } from "@/api/httpClient";
import { clearTokens, setTokens } from "@/api/authStore";
import { clearWorkspaceId } from "@/api/workspaceStore";

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
};

export async function login(email: string, password: string): Promise<TokenResponse> {
  const tokens = await apiFetch<TokenResponse>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
    auth: false,
  });
  setTokens(tokens);
  return tokens;
}

export async function signup(
  email: string,
  password: string,
  organizationName?: string,
): Promise<TokenResponse> {
  const tokens = await apiFetch<TokenResponse>("/api/v1/auth/signup", {
    method: "POST",
    body: { email, password, organization_name: organizationName },
    auth: false,
  });
  setTokens(tokens);
  return tokens;
}

export function logout(): void {
  clearTokens();
  clearWorkspaceId();
}
