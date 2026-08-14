import type { AdminConversationItem } from "@/features/admin/types";
import { useLocale } from "@/i18n/context";

type Props = {
  conversations: AdminConversationItem[];
  loading?: boolean;
  error?: boolean;
};

/** Platform-admin only — `GET /api/v1/admin/conversations` (§36). Support gets 403. */
export function AdminConversationsPanel({ conversations, loading, error }: Props) {
  const { t } = useLocale();
  return (
    <section
      data-testid="admin-conversations-panel"
      className="rounded-lg border border-slate-800 bg-leovee-panel p-6"
    >
      <h2 className="text-lg font-semibold text-slate-100">{t("admin.conversations.title")}</h2>
      {loading && <p className="mt-2 text-slate-400">{t("common.loading")}</p>}
      {error && <p className="mt-2 text-amber-400">{t("common.error.load")}</p>}
      {!loading && !error && conversations.length === 0 && (
        <p className="mt-2 text-slate-400">{t("admin.conversations.empty")}</p>
      )}
      <ul className="mt-4 space-y-2 text-sm">
        {conversations.map((conversation) => (
          <li
            key={conversation.id}
            data-testid={`admin-conversation-${conversation.id}`}
            className="rounded border border-slate-800 p-3"
          >
            <p className="text-slate-100">{conversation.title}</p>
            <p className="text-xs text-slate-500">{conversation.mode}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
