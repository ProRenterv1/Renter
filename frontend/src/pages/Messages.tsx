import { useState } from "react";
import { Header } from "../components/Header";
import { Card, CardContent } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { Search, Send, MoreVertical, ArrowLeft } from "lucide-react";
import { Separator } from "../components/ui/separator";

interface Message {
  id: number;
  senderId: string;
  text: string;
  timestamp: string;
  isOwn: boolean;
}

interface Conversation {
  id: number;
  userId: string;
  userName: string;
  userAvatar: string;
  lastMessage: string;
  lastMessageTime: string;
  unread: number;
  toolName?: string;
}

export default function Messages() {
  const [selectedConversation, setSelectedConversation] = useState<number | null>(1);
  const [messageText, setMessageText] = useState("");

  const conversations: Conversation[] = [
    {
      id: 1,
      userId: "sarah",
      userName: "Sarah Johnson",
      userAvatar: "",
      lastMessage: "Is the drill still available tomorrow?",
      lastMessageTime: "2m ago",
      unread: 2,
      toolName: "DeWalt 20V Cordless Drill"
    },
    {
      id: 2,
      userId: "mike",
      userName: "Mike Chen",
      userAvatar: "",
      lastMessage: "Thanks for the rental!",
      lastMessageTime: "1h ago",
      unread: 0,
      toolName: "Pressure Washer"
    },
    {
      id: 3,
      userId: "emma",
      userName: "Emma Davis",
      userAvatar: "",
      lastMessage: "Can I extend the rental period?",
      lastMessageTime: "3h ago",
      unread: 1,
      toolName: "Step Ladder"
    },
  ];

  const messages: Record<number, Message[]> = {
    1: [
      { id: 1, senderId: "sarah", text: "Hi! I'm interested in renting your drill.", timestamp: "10:30 AM", isOwn: false },
      { id: 2, senderId: "me", text: "Hello! Yes, it's available. When do you need it?", timestamp: "10:32 AM", isOwn: true },
      { id: 3, senderId: "sarah", text: "Is the drill still available tomorrow?", timestamp: "10:35 AM", isOwn: false },
    ],
    2: [
      { id: 1, senderId: "mike", text: "The pressure washer worked great!", timestamp: "Yesterday", isOwn: false },
      { id: 2, senderId: "me", text: "Glad to hear that! Let me know if you need it again.", timestamp: "Yesterday", isOwn: true },
      { id: 3, senderId: "mike", text: "Thanks for the rental!", timestamp: "2:15 PM", isOwn: false },
    ],
    3: [
      { id: 1, senderId: "emma", text: "Hi! I rented your ladder last week.", timestamp: "9:00 AM", isOwn: false },
      { id: 2, senderId: "emma", text: "Can I extend the rental period?", timestamp: "9:05 AM", isOwn: false },
    ],
  };

  const currentConversation = conversations.find(c => c.id === selectedConversation);
  const currentMessages = selectedConversation ? messages[selectedConversation] || [] : [];

  const handleSendMessage = () => {
    if (messageText.trim()) {
      // In a real app, this would send the message
      setMessageText("");
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />
      
      <div className="h-[calc(100vh-64px)] flex">
        {/* Conversations List */}
        <aside className="w-80 border-r bg-card flex flex-col">
          <div className="p-4 border-b">
            <h2 className="text-xl mb-3">Messages</h2>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "var(--text-muted)" }} />
              <Input 
                placeholder="Search messages..." 
                className="pl-9"
              />
            </div>
          </div>

          <div className="flex-1 overflow-y-auto">
            {conversations.map((conversation) => (
              <button
                key={conversation.id}
                onClick={() => setSelectedConversation(conversation.id)}
                className={`w-full p-4 flex items-start gap-3 hover:bg-muted/50 transition-colors border-b ${
                  selectedConversation === conversation.id ? "bg-muted" : ""
                }`}
              >
                <Avatar className="w-12 h-12 flex-shrink-0">
                  <AvatarImage src={conversation.userAvatar} />
                  <AvatarFallback className="bg-[var(--primary)]" style={{ color: "var(--primary-foreground)" }}>
                    {conversation.userName.split(" ").map(n => n[0]).join("")}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 text-left min-w-0">
                  <div className="flex items-center justify-between mb-1">
                    <p className="truncate">{conversation.userName}</p>
                    <span className="text-xs flex-shrink-0" style={{ color: "var(--text-muted)" }}>
                      {conversation.lastMessageTime}
                    </span>
                  </div>
                  {conversation.toolName && (
                    <p className="text-xs mb-1" style={{ color: "var(--primary)" }}>
                      {conversation.toolName}
                    </p>
                  )}
                  <div className="flex items-center justify-between">
                    <p className="text-sm truncate" style={{ color: "var(--text-muted)" }}>
                      {conversation.lastMessage}
                    </p>
                    {conversation.unread > 0 && (
                      <Badge className="ml-2 flex-shrink-0 bg-[var(--primary)]" style={{ color: "var(--primary-foreground)" }}>
                        {conversation.unread}
                      </Badge>
                    )}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </aside>

        {/* Chat Area */}
        {selectedConversation && currentConversation ? (
          <div className="flex-1 flex flex-col">
            {/* Chat Header */}
            <div className="p-4 border-b bg-card flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Avatar className="w-10 h-10">
                  <AvatarImage src={currentConversation.userAvatar} />
                  <AvatarFallback className="bg-[var(--primary)]" style={{ color: "var(--primary-foreground)" }}>
                    {currentConversation.userName.split(" ").map(n => n[0]).join("")}
                  </AvatarFallback>
                </Avatar>
                <div>
                  <p>{currentConversation.userName}</p>
                  {currentConversation.toolName && (
                    <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                      {currentConversation.toolName}
                    </p>
                  )}
                </div>
              </div>
              <Button variant="ghost" size="icon">
                <MoreVertical className="w-5 h-5" />
              </Button>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {currentMessages.map((message) => (
                <div
                  key={message.id}
                  className={`flex ${message.isOwn ? "justify-end" : "justify-start"}`}
                >
                  <div className={`max-w-[70%] ${message.isOwn ? "order-2" : "order-1"}`}>
                    <div
                      className={`px-4 py-2 rounded-2xl ${
                        message.isOwn
                          ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                          : "bg-muted"
                      }`}
                    >
                      <p>{message.text}</p>
                    </div>
                    <p className={`text-xs mt-1 ${message.isOwn ? "text-right" : ""}`} style={{ color: "var(--text-muted)" }}>
                      {message.timestamp}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* Message Input */}
            <div className="p-4 border-t bg-card">
              <div className="flex gap-2">
                <Input
                  placeholder="Type a message..."
                  value={messageText}
                  onChange={(e) => setMessageText(e.target.value)}
                  onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
                  className="flex-1"
                />
                <Button
                  onClick={handleSendMessage}
                  className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                  style={{ color: "var(--primary-foreground)" }}
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center" style={{ color: "var(--text-muted)" }}>
            <p>Select a conversation to start messaging</p>
          </div>
        )}
      </div>
    </div>
  );
}
