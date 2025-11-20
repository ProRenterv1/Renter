import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  applyChatEvent,
  fetchConversationDetail,
  sendChatMessage,
  type ChatEventPayload,
  type ConversationDetail,
} from "@/lib/chat";
import { startEventStream } from "@/lib/events";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type MessagesProps = {
  conversationId: number;
};

const ChatMessages: React.FC<MessagesProps> = ({ conversationId }) => {
  const [conversation, setConversation] = useState<ConversationDetail | null>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const chatClosed =
    !conversation ||
    !conversation.is_active ||
    conversation.booking.status === "canceled" ||
    conversation.booking.status === "completed";

  const loadConversation = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchConversationDetail(conversationId);
      setConversation(data);
    } catch (err) {
      console.error("chat: failed to load conversation", err);
      setError("Unable to load this conversation.");
      setConversation(null);
    } finally {
      setLoading(false);
    }
  }, [conversationId]);

  useEffect(() => {
    setConversation(null);
    setInput("");
    void loadConversation();
  }, [loadConversation]);

  useEffect(() => {
    const handle = startEventStream<ChatEventPayload>({
      onEvents: (events) => {
        setConversation((current) => {
          let next = current;
          for (const event of events) {
            next = applyChatEvent(next, event);
          }
          return next;
        });
      },
    });

    return () => handle.stop();
  }, []);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [conversation?.messages.length]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || chatClosed) {
      return;
    }
    setSending(true);
    try {
      const message = await sendChatMessage(conversationId, text);
      setConversation((current) => {
        if (!current) {
          return current;
        }
        if (current.messages.some((existing) => existing.id === message.id)) {
          return current;
        }
        return { ...current, messages: [...current.messages, message] };
      });
      setInput("");
    } catch (err) {
      console.error("chat: failed to send message", err);
    } finally {
      setSending(false);
    }
  };

  if (loading && !conversation) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        Loading chat...
      </div>
    );
  }

  if (error || !conversation) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
        <p>{error ?? "Conversation could not be loaded."}</p>
        <Button variant="outline" size="sm" onClick={() => void loadConversation()}>
          Retry
        </Button>
      </div>
    );
  }

  const formatDate = (iso: string | null | undefined) => {
    if (!iso) return null;
    try {
      return new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
      }).format(new Date(iso));
    } catch {
      return iso;
    }
  };

  const formatMessageTime = (iso: string | null | undefined) => {
    if (!iso) return "";
    try {
      return new Intl.DateTimeFormat(undefined, {
        hour: "numeric",
        minute: "2-digit",
      }).format(new Date(iso));
    } catch {
      return iso ?? "";
    }
  };

  const bookingListing = conversation.booking.listing;
  const listingInfo =
    typeof bookingListing === "object" && bookingListing
      ? bookingListing
      : null;
  const listingTitle =
    conversation.booking.listing_title ||
    listingInfo?.title ||
    "Booking conversation";
  const listingSlug = conversation.booking.listing_slug || listingInfo?.slug || null;
  const listingLink = listingSlug ? `/listings/${listingSlug}` : null;
  const bookingRange = (() => {
    const start = formatDate(conversation.booking.start_date);
    const end = formatDate(conversation.booking.end_date);
    if (start && end) {
      return `${start} - ${end}`;
    }
    return start ?? end ?? "";
  })();
  const listingInitial = listingTitle.trim().slice(0, 1).toUpperCase() || "L";
  const listingImage =
    conversation.booking.listing_primary_photo_url ??
    listingInfo?.thumbnail_url ??
    null;

  const renderListingMedia = () => {
    const media = listingImage ? (
      <img
        src={listingImage}
        alt={listingTitle}
        className="h-14 w-14 rounded-lg object-cover"
      />
    ) : (
      <div className="flex h-14 w-14 items-center justify-center rounded-lg bg-muted text-sm font-medium text-muted-foreground">
        {listingInitial}
      </div>
    );
    if (listingLink) {
      return (
        <Link to={listingLink} className="shrink-0 focus:outline-none focus:ring-2 focus:ring-ring">
          {media}
        </Link>
      );
    }
    return media;
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-4">
          {renderListingMedia()}
          <div>
            {listingLink ? (
              <Link
                to={listingLink}
                className="text-sm font-medium text-primary hover:underline focus:outline-none focus:ring-2 focus:ring-ring"
              >
                {listingTitle}
              </Link>
            ) : (
              <p className="text-sm font-medium">{listingTitle}</p>
            )}
            <p className="text-xs text-muted-foreground">
              Booking #{conversation.booking.id}
              {bookingRange ? ` - ${bookingRange}` : ""}
            </p>
          </div>
        </div>
        <div className="text-xs text-muted-foreground">
          Status: <span className="font-medium">{conversation.booking.status}</span>
        </div>
      </div>

      <div ref={listRef} className="flex-1 space-y-2 overflow-y-auto bg-muted/30 px-4 py-3">
        {conversation.messages.length === 0 && (
          <div className="py-8 text-center text-xs text-muted-foreground">
            No messages yet. Start the conversation below.
          </div>
        )}

        {conversation.messages.map((msg) => {
          const isSystem = msg.message_type === "system";
          const isMine = msg.sender_is_me;
          const sentAt = formatMessageTime(msg.created_at);

          if (isSystem) {
            return (
              <div
                key={msg.id}
                className="my-4 flex items-center gap-3 text-[11px] text-muted-foreground"
              >
                <div className="h-px flex-1 bg-border" />
                <div className="flex items-center gap-2 rounded-full bg-muted px-3 py-1">
                  <span>{msg.text || msg.system_kind}</span>
                  {sentAt ? (
                    <span className="text-[10px] text-muted-foreground/80">{sentAt}</span>
                  ) : null}
                </div>
                <div className="h-px flex-1 bg-border" />
              </div>
            );
          }

          return (
            <div
              key={msg.id}
              className={`flex w-full items-end gap-2 ${
                isMine ? "justify-end" : "justify-start"
              }`}
            >
              {!isMine && sentAt ? (
                <span className="text-[10px] text-muted-foreground">{sentAt}</span>
              ) : null}
              <div
                className={`max-w-[70%] rounded-2xl px-3 py-2 text-sm ${
                  isMine
                    ? "bg-primary text-primary-foreground"
                    : "border border-border bg-card text-foreground"
                }`}
              >
                <p>{msg.text}</p>
              </div>
              {isMine && sentAt ? (
                <span className="text-[10px] text-muted-foreground">{sentAt}</span>
              ) : null}
            </div>
          );
        })}
      </div>

      <div className="border-t px-4 py-3">
        <div className="flex items-center gap-2">
          <Input
            type="text"
            value={input}
            disabled={chatClosed || sending}
            placeholder={
              chatClosed ? "Chat is closed for this booking" : "Type a message..."
            }
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void handleSend();
              }
            }}
          />
          <Button
            onClick={() => void handleSend()}
            disabled={chatClosed || sending || !input.trim()}
          >
            {sending ? "Sending..." : "Send"}
          </Button>
        </div>
        {chatClosed && (
          <p className="mt-2 text-xs text-muted-foreground">
            This conversation is read-only because the booking is closed.
          </p>
        )}
      </div>
    </div>
  );
};

export default ChatMessages;
