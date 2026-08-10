export type AlertData = {
  id: string;
  type: string;
  symbol_id: string | null;
  condition: Record<string, unknown>;
  channels: Record<string, unknown>;
  active: boolean;
  last_triggered_at: string | null;
};

export type NotificationData = {
  id: string;
  title: string;
  message: string;
  type: string;
};
