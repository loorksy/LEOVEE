import { apiFetch } from "@/api/httpClient";

export type LinkCode = {
  code: string;
  expires_at: string;
  note: string;
};

export type LinkedAccount = {
  telegram_user_id: number;
  telegram_username: string | null;
  linked_at: string;
  last_message_at: string | null;
};

export async function createLinkCode(): Promise<LinkCode> {
  return apiFetch<LinkCode>("/api/v1/telegram/link-code", { method: "POST" });
}

export async function listLinks(): Promise<LinkedAccount[]> {
  return apiFetch<LinkedAccount[]>("/api/v1/telegram/links");
}

export async function revokeLink(telegramUserId: number): Promise<void> {
  await apiFetch<void>(`/api/v1/telegram/links/${telegramUserId}`, { method: "DELETE" });
}
