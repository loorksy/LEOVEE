import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { createLinkCode, listLinks, revokeLink, type LinkCode } from "@/api/telegram";
import { useLocale } from "@/i18n/context";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";

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
    <Card data-testid="telegram-settings" className="sm:max-w-lg">
      <CardHeader>
        <CardTitle>{t("telegram.title")}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("telegram.intro")}</p>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div className="flex flex-col gap-3">
          <Button
            type="button"
            className="self-start"
            onClick={() => codeMutation.mutate()}
            disabled={codeMutation.isPending}
          >
            {t("telegram.generate")}
          </Button>

          {issued ? (
            <div
              className="rounded-lg border border-border bg-muted/50 p-4"
              data-testid="telegram-link-code"
            >
              <p className="text-sm text-foreground">{t("telegram.codeLabel")}</p>
              <p className="mt-2 font-mono text-2xl tracking-widest text-foreground">
                {issued.code}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                {t("telegram.expires")}: {new Date(issued.expires_at).toLocaleTimeString()}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{issued.note}</p>
            </div>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-foreground">{t("telegram.linked")}</h3>
          {links.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("telegram.none")}</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {links.map((link) => (
                <li
                  key={link.telegram_user_id}
                  className="flex flex-col gap-2 rounded-lg border border-border p-3 sm:flex-row sm:items-center sm:justify-between"
                  data-testid={`telegram-link-${link.telegram_user_id}`}
                >
                  <span className="text-sm text-foreground">
                    {link.telegram_username ? `@${link.telegram_username}` : link.telegram_user_id}
                    <span className="ms-3 text-sm text-muted-foreground">
                      {t("telegram.lastMessage")}:{" "}
                      {link.last_message_at
                        ? new Date(link.last_message_at).toLocaleString()
                        : t("telegram.never")}
                    </span>
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="shrink-0 self-start sm:self-center"
                    onClick={() => revokeMutation.mutate(link.telegram_user_id)}
                    disabled={revokeMutation.isPending}
                  >
                    {t("telegram.revoke")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
