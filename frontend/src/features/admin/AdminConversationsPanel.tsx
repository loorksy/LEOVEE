import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardInset, CardTitle } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
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
    <Card data-testid="admin-conversations-panel">
      <CardHeader>
        <CardTitle>{t("admin.conversations.title")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {loading && (
          <div className="flex flex-col gap-2" data-testid="admin-conversations-loading">
            <Skeleton className="h-12 w-full" />
            <Skeleton className="h-12 w-full" />
          </div>
        )}
        {error && <p className="text-sm text-destructive">{t("common.error.load")}</p>}
        {!loading && !error && conversations.length === 0 && (
          <p className="text-sm text-muted-foreground">{t("admin.conversations.empty")}</p>
        )}
        {!loading && conversations.length > 0 && (
          <ul className="flex flex-col gap-2">
            {conversations.map((conversation) => (
              <li key={conversation.id} data-testid={`admin-conversation-${conversation.id}`}>
                <CardInset className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
                  <p className="truncate text-sm text-foreground">{conversation.title}</p>
                  <Badge variant="neutral" className="w-fit">
                    {conversation.mode}
                  </Badge>
                </CardInset>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
