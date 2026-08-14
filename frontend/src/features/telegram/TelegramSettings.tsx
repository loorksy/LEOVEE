import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createLinkCode, listLinks, revokeLink, type LinkCode } from "@/api/telegram";
import { useLocale } from "@/i18n/context";

/**
 * Linking a Telegram account, from inside the platform (ADR 0009).
 *
 * The promise is made twice on purpose — once here before the user decides, and
 * again by the agent the moment the link succeeds. "Nothing is ever sent unless
 * you ask" is the whole difference between this and the notification channel
 * D5 rules out, and a user who links without understanding that will read the
 * first silent day as the feature being broken.
 *
 * The code is shown once and never retrievable. There is no "show again" — it
 * is hashed the moment it is stored, so the server genuinely cannot produce it.
 */
export function TelegramSettings() {
  const { t } = useLocale();
  const queryClient = useQueryClient();
  const [issued, setIssued] = useState<LinkCode | null>(null);

  const linksQuery = useQuery({ queryKey: ["telegram-links"], queryFn: listLinks });

  const codeMutation = useMutation({
    mutationFn: createLinkCode,
    onSuccess: (code) => setIssued(code),
  });

  const revokeMutation = useMutation({
    mutationFn: revokeLink,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["telegram-links"] });
    },
  });

  const links = linksQuery.data ?? [];

  return (
    <section className="flex flex-col gap-6" data-testid="telegram-settings">
      <header>
        <h2 className="text-xl font-semibold text-slate-100">{t("telegram.title")}</h2>
        <p className="mt-1 text-slate-400">{t("telegram.intro")}</p>
      </header>

      <div className="flex flex-col gap-3">
        <button
          type="button"
          className="self-start rounded bg-sky-600 px-4 py-2 text-white"
          onClick={() => codeMutation.mutate()}
          disabled={codeMutation.isPending}
        >
          {t("telegram.generate")}
        </button>

        {issued ? (
          <div
            className="rounded border border-slate-700 bg-slate-900 p-4"
            data-testid="telegram-link-code"
          >
            <p className="text-slate-300">{t("telegram.codeLabel")}</p>
            <p className="mt-2 font-mono text-2xl tracking-widest text-slate-100">
              {issued.code}
            </p>
            <p className="mt-2 text-sm text-slate-400">
              {t("telegram.expires")}: {new Date(issued.expires_at).toLocaleTimeString()}
            </p>
            <p className="mt-2 text-sm text-slate-400">{issued.note}</p>
          </div>
        ) : null}
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-lg text-slate-200">{t("telegram.linked")}</h3>
        {links.length === 0 ? (
          <p className="text-slate-400">{t("telegram.none")}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {links.map((link) => (
              <li
                key={link.telegram_user_id}
                className="flex items-center justify-between rounded border border-slate-700 p-3"
                data-testid={`telegram-link-${link.telegram_user_id}`}
              >
                <span className="text-slate-200">
                  {link.telegram_username ? `@${link.telegram_username}` : link.telegram_user_id}
                  <span className="ms-3 text-sm text-slate-400">
                    {t("telegram.lastMessage")}:{" "}
                    {link.last_message_at
                      ? new Date(link.last_message_at).toLocaleString()
                      : t("telegram.never")}
                  </span>
                </span>
                <button
                  type="button"
                  className="rounded border border-slate-600 px-3 py-1 text-slate-200"
                  onClick={() => revokeMutation.mutate(link.telegram_user_id)}
                  disabled={revokeMutation.isPending}
                >
                  {t("telegram.revoke")}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
