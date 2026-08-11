import { useEffect, useRef } from "react";
import { buildAuthenticatedStreamUrl } from "@/api/realtime";
import type { NotificationData } from "@/features/alerts/types";

export type NotificationStreamEvent = {
  event: "notification";
  notification: NotificationData;
};

function isNotificationEvent(payload: unknown): payload is NotificationStreamEvent {
  if (typeof payload !== "object" || payload === null) return false;
  const candidate = payload as Record<string, unknown>;
  return candidate.event === "notification" && typeof candidate.notification === "object";
}

export type UseNotificationsStreamOptions = {
  workspaceId: string | null | undefined;
  enabled?: boolean;
  onNotification: (notification: NotificationData) => void;
};

/**
 * Subscribes to `/ws/v1/stream?channels=notifications` for alert-triggered
 * fan-out (phase 30 — `alert_service.fan_out_notification`).
 */
export function useNotificationsStream(options: UseNotificationsStreamOptions): void {
  const { workspaceId, enabled = true, onNotification } = options;
  const onNotificationRef = useRef(onNotification);
  onNotificationRef.current = onNotification;

  useEffect(() => {
    if (!enabled || !workspaceId) return undefined;
    const url = buildAuthenticatedStreamUrl({
      channels: ["notifications"],
      workspaceId,
    });
    if (!url) return undefined;

    const socket = new WebSocket(url);
    socket.onmessage = (event: MessageEvent<string>) => {
      let payload: unknown;
      try {
        payload = JSON.parse(event.data);
      } catch {
        return;
      }
      if (isNotificationEvent(payload)) {
        onNotificationRef.current(payload.notification);
      }
    };

    return () => {
      socket.close();
    };
  }, [enabled, workspaceId]);
}
