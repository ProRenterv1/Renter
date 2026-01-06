import { jsonFetch } from "./api";
import { AuthStore } from "./auth";

export type EventType =
  | "chat:new_message"
  | "booking:status_changed"
  | "booking:auto_canceled"
  | "booking:pickup_confirmed"
  | "booking:late"
  | "booking:not_returned"
  | "booking:review_invite"
  | "booking:return_requested"
  | string;

export interface EventEnvelope<T = any> {
  id: string;
  type: EventType;
  payload: T;
}

export interface EventStreamResponse<T = any> {
  cursor: string;
  events: EventEnvelope<T>[];
  now?: string;
}

export async function fetchEventsOnce<T = any>(
  cursor: string | null,
  timeoutSeconds: number,
  signal?: AbortSignal,
): Promise<EventStreamResponse<T>> {
  const params = new URLSearchParams();
  if (cursor && cursor.trim()) {
    params.set("cursor", cursor.trim());
  }
  params.set("timeout", String(timeoutSeconds));
  const query = params.toString();
  const path = `/events/stream/${query ? `?${query}` : ""}`;

  return jsonFetch<EventStreamResponse<T>>(path, {
    method: "GET",
    signal,
  });
}

export interface EventStreamOptions<T = any> {
  cursor?: string | null;
  timeoutSeconds?: number;
  onEvents: (events: EventEnvelope<T>[], cursor: string) => void;
  onError?: (error: unknown) => void;
}

export interface EventStreamHandle {
  stop(): void;
}

function startLongPollStream<T = any>(
  options: EventStreamOptions<T>,
): EventStreamHandle {
  const { onEvents, onError, timeoutSeconds = 25, cursor: initialCursor = null } = options;

  let cursor: string | null = initialCursor;
  let stopped = false;
  const controller = new AbortController();
  const perRequestTimeout = Math.min(Math.max(timeoutSeconds, 0), 60);

  const notifyError = (err: unknown) => {
    if (onError) {
      onError(err);
    } else {
      // eslint-disable-next-line no-console
      console.warn("events: stream error", err);
    }
  };

  const loop = async () => {
    while (!stopped) {
      try {
        const response = await fetchEventsOnce<T>(
          cursor,
          perRequestTimeout,
          controller.signal,
        );
        cursor = response.cursor || cursor;
        if (response.events && response.events.length > 0 && cursor) {
          onEvents(response.events, cursor);
        }
      } catch (err) {
        if (stopped) {
          return;
        }
        notifyError(err);
        await new Promise((resolve) => setTimeout(resolve, 3000));
      }
    }
  };

  void loop();

  return {
    stop() {
      if (stopped) {
        return;
      }
      stopped = true;
      controller.abort();
    },
  };
}

export function startEventStream<T = any>(
  options: EventStreamOptions<T>,
): EventStreamHandle {
  const supportsWebSocket =
    typeof window !== "undefined" && typeof WebSocket !== "undefined";
  const accessToken = supportsWebSocket ? AuthStore.getAccess() : null;

  if (!supportsWebSocket || !accessToken) {
    return startLongPollStream(options);
  }

  const notifyError = (err: unknown) => {
    if (options.onError) {
      options.onError(err);
    } else {
      // eslint-disable-next-line no-console
      console.warn("events: stream error", err);
    }
  };

  const loc = window.location;
  const protocol = loc.protocol === "https:" ? "wss:" : "ws:";
  const wsPath = "/ws/events/";
  const url = `${protocol}//${loc.host}${wsPath}?token=${encodeURIComponent(accessToken)}`;

  let ws: WebSocket | null;
  try {
    ws = new WebSocket(url);
  } catch (err) {
    notifyError(err);
    return startLongPollStream(options);
  }

  let closedByClient = false;

  ws.onmessage = (event: MessageEvent) => {
    try {
      const parsed = JSON.parse(event.data as string) as EventStreamResponse<T>;
      if (!parsed || !Array.isArray(parsed.events) || parsed.events.length === 0) {
        return;
      }
      const nextCursor = parsed.cursor || "";
      options.onEvents(parsed.events, nextCursor);
    } catch (err) {
      notifyError(err);
    }
  };

  ws.onerror = (event) => {
    notifyError(event);
  };

  ws.onclose = () => {
    if (!closedByClient) {
      notifyError(new Error("events websocket closed"));
    }
  };

  return {
    stop() {
      if (!ws) {
        return;
      }
      closedByClient = true;
      if (ws.readyState === WebSocket.OPEN) {
        ws.close(1000, "client stop");
      } else if (ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      } else if (ws.readyState === WebSocket.CLOSING) {
        // let existing close complete
      }
      ws = null;
    },
  };
}

// Example usage:
//
// const handle = startEventStream({
//   onEvents: (events, cursor) => {
//     for (const event of events) {
//       switch (event.type) {
//         case "chat:new_message":
//           // update chat store...
//           break;
//         case "booking:status_changed":
//           // refetch bookings or patch local booking state...
//           break;
//       }
//     }
//   },
// });
//
// // later, e.g. in a React useEffect cleanup:
// // handle.stop();

