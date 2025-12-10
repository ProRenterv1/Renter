import { AuthStore } from "./auth";
import { jsonFetch } from "./api";
import type { EventEnvelope } from "./events";

export interface ChatMessage {
  id: number;
  sender: number | null;
  sender_is_me: boolean;
  is_read?: boolean;
  message_type: "user" | "system";
  system_kind: string | null;
  text: string;
  created_at: string;
}

export interface ChatBookingSummary {
  id: number;
  status: string;
  start_date: string;
  end_date: string;
  owner: number;
  renter: number;
  listing:
    | number
    | {
        id: number;
        title: string;
        thumbnail_url?: string | null;
        slug?: string | null;
      };
  listing_title?: string | null;
  listing_owner_first_name?: string | null;
  listing_owner_last_name?: string | null;
  listing_owner_username?: string | null;
  listing_owner_identity_verified?: boolean;
  listing_slug?: string | null;
  listing_primary_photo_url?: string | null;
  renter_first_name?: string | null;
  renter_last_name?: string | null;
  renter_username?: string | null;
  renter_avatar_url?: string | null;
  renter_identity_verified?: boolean;
}

export interface ConversationSummary {
  id: number;
  booking_id: number | null;
  listing_id: number | null;
  listing_title: string;
  other_party_name: string;
  other_party_avatar_url?: string | null;
  other_party_identity_verified?: boolean;
  is_active: boolean;
  last_message: {
    id: number;
    sender_id?: number | null;
    sender_is_me?: boolean;
    is_read?: boolean;
    message_type: "user" | "system";
    system_kind: string | null;
    text: string;
    created_at: string;
  } | null;
  last_message_at: string | null;
  unread_count: number;
}

export interface ConversationDetail {
  id: number;
  booking: ChatBookingSummary | null;
  listing_id: number | null;
  listing_title: string;
  listing_primary_photo_url?: string | null;
  is_active: boolean;
  messages: ChatMessage[];
}

export interface ChatEventPayload {
  conversation_id: number;
  booking_id: number | null;
  message: {
    id: number;
    sender?: number | null;
    sender_id?: number | null;
    sender_is_me?: boolean;
    is_read?: boolean;
    message_type: "user" | "system";
    system_kind: string | null;
    text: string;
    created_at: string;
  };
}

// GET /api/chats/
export async function fetchConversations(): Promise<ConversationSummary[]> {
  return jsonFetch<ConversationSummary[]>("/chats/", { method: "GET" });
}

// GET /api/chats/{id}/
export async function fetchConversationDetail(
  conversationId: number,
): Promise<ConversationDetail> {
  return jsonFetch<ConversationDetail>(`/chats/${conversationId}/`, {
    method: "GET",
  });
}

// POST /api/chats/start/
export async function startConversationForListing(
  listingId: number,
): Promise<ConversationDetail> {
  return jsonFetch<ConversationDetail>("/chats/start/", {
    method: "POST",
    body: { listing: listingId },
  });
}

// POST /api/chats/{id}/messages/
export async function sendChatMessage(
  conversationId: number,
  text: string,
): Promise<ChatMessage> {
  return jsonFetch<ChatMessage>(`/chats/${conversationId}/messages/`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

function normalizeEventMessage(message: ChatEventPayload["message"]): ChatMessage {
  const currentUserId = AuthStore.getCurrentUser()?.id ?? null;
  const sender = message.sender ?? message.sender_id ?? null;
  const senderIsMe =
    typeof message.sender_is_me === "boolean"
      ? message.sender_is_me
      : currentUserId !== null && sender === currentUserId;

  return {
    id: message.id,
    sender: sender ?? null,
    sender_is_me: senderIsMe,
    message_type: message.message_type,
    system_kind: message.system_kind ?? null,
    text: message.text ?? "",
    created_at: message.created_at,
    is_read: typeof message.is_read === "boolean" ? message.is_read : undefined,
  };
}

export function applyChatEvent(
  conv: ConversationDetail | null,
  event: EventEnvelope<ChatEventPayload>,
): ConversationDetail | null {
  if (!conv || event.type !== "chat:new_message") {
    return conv;
  }
  if (!event?.payload || event.payload.conversation_id !== conv.id) {
    return conv;
  }
  const msg = normalizeEventMessage(event.payload.message);
  const existingIndex = conv.messages.findIndex((m) => m.id === msg.id);
  if (existingIndex !== -1) {
    const messages = [...conv.messages];
    messages[existingIndex] = { ...messages[existingIndex], ...msg };
    return { ...conv, messages };
  }
  return {
    ...conv,
    messages: [...conv.messages, msg],
  };
}
