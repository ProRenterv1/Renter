import { useCallback, useEffect, useMemo, useState } from "react";
import { Search } from "lucide-react";

import ChatMessages from "@/components/chat/Messages";
import { Header } from "@/components/Header";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  fetchConversations,
  type ConversationSummary,
} from "@/lib/chat";
import { startEventStream } from "@/lib/events";

const getInitials = (name: string) =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("") || "??";

export default function MessagesPage() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [unreadConversationIds, setUnreadConversationIds] = useState<Set<number>>(
    () => new Set(),
  );

  const loadConversations = useCallback(async () => {
    try {
      const data = await fetchConversations();
      setConversations(data);
      setError(null);
      return data;
    } catch (err) {
      console.error("chat: failed to load conversations", err);
      setError("Unable to load conversations right now.");
      return [];
    }
  }, []);

  useEffect(() => {
    let active = true;
    setLoading(true);
    loadConversations()
      .then((data) => {
        if (!active) {
          return;
        }
        if (data.length > 0) {
          setSelectedConversationId((prev) => prev ?? data[0].id);
        } else {
          setSelectedConversationId(null);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [loadConversations]);

  useEffect(() => {
    const handle = startEventStream({
      onEvents: (events) => {
        let shouldRefresh = false;
        const newlyUnread: number[] = [];
        setConversations((prev) => {
          let changed = false;
          let next = prev;
          for (const event of events) {
            if (event.type !== "chat:new_message" || !event.payload) {
              continue;
            }
            const idx = next.findIndex((conv) => conv.id === event.payload.conversation_id);
            if (idx === -1) {
              shouldRefresh = true;
              if (!event.payload.message?.sender_is_me) {
                newlyUnread.push(event.payload.conversation_id);
              }
              continue;
            }
            if (!changed) {
              next = [...next];
              changed = true;
            }
            const message = event.payload.message;
            next[idx] = {
              ...next[idx],
              last_message: {
                id: message.id,
                message_type: message.message_type,
                system_kind: message.system_kind,
                text: message.text,
                created_at: message.created_at,
              },
              last_message_at: message.created_at,
            };
            if (
              !message.sender_is_me &&
              event.payload.conversation_id !== selectedConversationId
            ) {
              newlyUnread.push(event.payload.conversation_id);
            }
          }
          return changed ? next : prev;
        });
        if (newlyUnread.length > 0) {
          setUnreadConversationIds((prev) => {
            let changed = false;
            const next = new Set(prev);
            for (const id of newlyUnread) {
              if (!next.has(id)) {
                next.add(id);
                changed = true;
              }
            }
            return changed ? next : prev;
          });
        }
        if (shouldRefresh) {
          void loadConversations();
        }
      },
    });
    return () => handle.stop();
  }, [loadConversations, selectedConversationId]);

  useEffect(() => {
    if (selectedConversationId === null) {
      return;
    }
    const exists = conversations.some((conv) => conv.id === selectedConversationId);
    if (!exists) {
      setSelectedConversationId(conversations[0]?.id ?? null);
    }
  }, [conversations, selectedConversationId]);

  useEffect(() => {
    if (selectedConversationId === null) {
      return;
    }
    setUnreadConversationIds((prev) => {
      if (!prev.has(selectedConversationId)) {
        return prev;
      }
      const next = new Set(prev);
      next.delete(selectedConversationId);
      return next;
    });
  }, [selectedConversationId]);

  const filteredConversations = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) {
      return conversations;
    }
    return conversations.filter((conv) => {
      const listingMatch = conv.listing_title.toLowerCase().includes(query);
      const nameMatch = conv.other_party_name.toLowerCase().includes(query);
      return listingMatch || nameMatch;
    });
  }, [conversations, search]);

  const sortedConversations = useMemo(() => {
    return [...filteredConversations].sort((a, b) => {
      const aTime = a.last_message_at ? new Date(a.last_message_at).getTime() : 0;
      const bTime = b.last_message_at ? new Date(b.last_message_at).getTime() : 0;
      return bTime - aTime;
    });
  }, [filteredConversations]);

  return (
    <div className="min-h-screen bg-background">
      <Header />
      <div className="flex h-[calc(100vh-64px)]">
        <aside className="flex w-80 flex-col border-r bg-card">
          <div className="border-b p-4">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-xl">Messages</h2>
              <Button variant="ghost" size="sm" onClick={() => void loadConversations()}>
                Refresh
              </Button>
            </div>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search conversations…"
                className="pl-9"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto">
            {loading && (
              <div className="p-4 text-sm text-muted-foreground">Loading chats…</div>
            )}
            {error && (
              <Card className="m-4">
                <CardContent className="py-3 text-sm text-destructive">{error}</CardContent>
              </Card>
            )}
            {!loading && sortedConversations.length === 0 && !error && (
              <div className="p-4 text-sm text-muted-foreground">
                No conversations yet.
              </div>
            )}
            {sortedConversations.map((conversation) => {
              const isSelected = conversation.id === selectedConversationId;
              const isUnread = unreadConversationIds.has(conversation.id);
              const lastMessage = conversation.last_message;
              const lastMessageText =
                lastMessage?.text ??
                (lastMessage ? lastMessage.system_kind : "No messages yet");
              const lastMessagePrefix = (() => {
                if (!lastMessage) {
                  return "";
                }
                if (lastMessage.sender_is_me) {
                  return "You: ";
                }
                const firstName = conversation.other_party_name.split(" ").find(Boolean);
                return firstName ? `${firstName}: ` : "";
              })();
              return (
                <button
                  key={conversation.id}
                  type="button"
                  onClick={() => setSelectedConversationId(conversation.id)}
                  className={`flex w-full flex-col gap-1 border-b px-4 py-3 text-left transition-colors ${
                    isSelected ? "bg-muted" : "hover:bg-muted/70"
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <Avatar className="h-10 w-10">
                      <AvatarFallback>{getInitials(conversation.other_party_name)}</AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                      <p
                        className={`leading-tight ${
                          isUnread ? "font-semibold text-foreground" : "font-medium"
                        }`}
                      >
                        {conversation.other_party_name}
                      </p>
                      <p className="text-xs text-muted-foreground">{conversation.listing_title}</p>
                      <p
                        className={`truncate text-sm ${
                          isUnread ? "font-semibold text-foreground" : "text-muted-foreground"
                        }`}
                      >
                        {lastMessagePrefix}
                        {lastMessageText}
                      </p>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </aside>
        <div className="flex flex-1 flex-col">
          {selectedConversationId ? (
            <ChatMessages conversationId={selectedConversationId} />
          ) : (
            <div className="flex flex-1 items-center justify-center text-muted-foreground">
              {loading ? "Loading chats…" : "Select a conversation to start messaging"}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
