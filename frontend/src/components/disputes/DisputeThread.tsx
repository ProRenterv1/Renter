import { useEffect, useMemo, useState } from "react";
import { format } from "date-fns";
import { AlertCircle, FileText, Loader2, MessageSquare, Send } from "lucide-react";
import { disputesAPI, type DisputeCase, type DisputeMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "../ui/avatar";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";

interface DisputeThreadProps {
  disputeId: number;
}

export function DisputeThread({ disputeId }: DisputeThreadProps) {
  const [dispute, setDispute] = useState<DisputeCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messageText, setMessageText] = useState("");
  const [sending, setSending] = useState(false);

  const loadDispute = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await disputesAPI.retrieve(disputeId);
      setDispute(data);
    } catch (err) {
      setError("Unable to load dispute. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDispute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disputeId]);

  const messages = useMemo<DisputeMessage[]>(() => dispute?.messages ?? [], [dispute]);

  const handleSend = async () => {
    if (!messageText.trim()) {
      return;
    }
    setSending(true);
    try {
      const created = await disputesAPI.createMessage(disputeId, messageText.trim());
      setDispute((prev) =>
        prev
          ? {
              ...prev,
              messages: [...(prev.messages ?? []), created],
            }
          : prev,
      );
      setMessageText("");
    } catch (err) {
      setError("Could not send message. Please retry.");
    } finally {
      setSending(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading dispute…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4" />
        {error}
      </div>
    );
  }

  if (!dispute) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="bg-card border rounded-lg p-6">
        <h3 className="font-medium mb-4">Evidence Submitted</h3>
        <div className="space-y-4">
          {(dispute.evidence ?? []).map((ev) => {
            const isImage = ev.content_type?.startsWith("image/");
            const isVideo = ev.content_type?.startsWith("video/");
            const description =
              (ev as DisputeEvidenceWithDescription).description ?? ev.filename ?? ev.kind;
            const evidenceUrl = ev.s3_key;
            return (
              <div key={ev.id} className="border rounded-lg p-4">
                <div className="flex items-start gap-4">
                  <div className="w-32 h-32 bg-muted rounded-lg flex items-center justify-center overflow-hidden">
                    {isImage && evidenceUrl ? (
                      <img src={evidenceUrl} alt={description} className="w-full h-full object-cover" />
                    ) : isVideo && evidenceUrl ? (
                      <video
                        src={evidenceUrl}
                        className="w-full h-full object-cover"
                        muted
                        playsInline
                      />
                    ) : (
                      <FileText className="w-12 h-12 text-muted-foreground" />
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <Badge variant="outline" className="text-xs uppercase">
                        {ev.kind}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        AV: {ev.av_status || "pending"}
                      </Badge>
                    </div>
                    <p className="text-sm mb-2 break-words">{description}</p>
                    <p className="text-xs text-muted-foreground">
                      Uploaded: {format(new Date(ev.created_at), "MMM d, yyyy h:mm a")}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}

          {(dispute.evidence ?? []).length === 0 && (
            <div className="border rounded-lg p-6 text-center text-sm text-muted-foreground">
              No evidence uploaded yet.
            </div>
          )}
        </div>
      </div>

      <div className="bg-card border rounded-lg">
        <div className="p-6 border-b">
          <h3 className="font-medium flex items-center gap-2">
            <MessageSquare className="w-5 h-5" />
            Dispute Conversation
          </h3>
        </div>

        <div className="p-6 space-y-4 max-h-96 overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">No messages yet.</p>
          )}
          {messages.map((message) => {
            const isSupport = message.role === "admin" || message.role === "system";
            const roleLabel = isSupport ? "Support Team" : message.role.toUpperCase();
            return (
              <div
                key={message.id}
                className={cn(
                  "flex gap-3",
                  isSupport ? "bg-muted/50 -mx-6 px-6 py-4 rounded-none md:rounded-none" : "",
                )}
              >
                <Avatar className="w-8 h-8">
                  <AvatarFallback
                    className={isSupport ? "bg-orange-500 text-white" : "bg-[var(--primary)]"}
                    style={isSupport ? undefined : { color: "var(--primary-foreground)" }}
                  >
                    {isSupport ? "RS" : roleLabel.slice(0, 2)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-medium text-sm">{roleLabel}</span>
                    {isSupport ? (
                      <Badge variant="secondary" className="text-xs">
                        Support Team
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] uppercase tracking-wide">
                        {roleLabel}
                      </Badge>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {format(new Date(message.created_at), "MMM d, yyyy h:mm a")}
                    </span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{message.text}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="p-4 border-t">
          <div className="flex gap-2">
            <input
              type="text"
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="Type your message..."
              className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] bg-background"
            />
            <Button
              onClick={() => void handleSend()}
              disabled={sending || !messageText.trim()}
              className="flex items-center gap-2"
            >
              <Send className="h-4 w-4" />
              Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

type DisputeEvidenceWithDescription = {
  description?: string | null;
};
