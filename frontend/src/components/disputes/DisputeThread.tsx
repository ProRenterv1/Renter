import { useEffect, useMemo, useState } from "react";
import { format } from "date-fns";
import { AlertCircle, Loader2, Send } from "lucide-react";
import { disputesAPI, type DisputeCase, type DisputeMessage } from "@/lib/api";
import { cn } from "@/lib/utils";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Label } from "../ui/label";
import { ScrollArea } from "../ui/scroll-area";
import { Textarea } from "../ui/textarea";

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
    <Card className="w-full">
      <CardHeader>
        <CardTitle className="text-base">
          Dispute #{dispute.id} · Booking #{dispute.booking} · {dispute.status}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <ScrollArea className="max-h-64 rounded-md border p-3">
          <div className="space-y-3">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground">No messages yet.</p>
            )}
            {messages.map((msg) => (
              <div key={msg.id} className="space-y-1 rounded-md bg-muted p-2">
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span className="uppercase tracking-wide">{msg.role}</span>
                  <span>{format(new Date(msg.created_at), "MMM d, yyyy h:mm a")}</span>
                </div>
                <div className="text-sm whitespace-pre-wrap">{msg.text}</div>
              </div>
            ))}
          </div>
        </ScrollArea>

        <div className="space-y-2">
          <Label htmlFor="message">Reply</Label>
          <Textarea
            id="message"
            value={messageText}
            onChange={(e) => setMessageText(e.target.value)}
            placeholder="Type your response"
            rows={3}
          />
          <div className="flex justify-end">
            <Button size="sm" onClick={() => void handleSend()} disabled={sending || !messageText}>
              <Send className="mr-2 h-4 w-4" />
              Send
            </Button>
          </div>
        </div>

        <div className="space-y-2">
          <Label>Evidence</Label>
          <div className="space-y-2">
            {(dispute.evidence ?? []).map((ev) => (
              <div
                key={ev.id}
                className={cn(
                  "flex items-center justify-between rounded-md border p-2 text-sm",
                  ev.av_status === "failed" || ev.av_status === "infected"
                    ? "border-destructive/50 text-destructive"
                    : "",
                )}
              >
                <div className="flex flex-col">
                  <span className="font-medium">
                    {ev.filename || ev.kind} ({ev.kind})
                  </span>
                  <span className="text-xs text-muted-foreground">
                    AV: {ev.av_status || "pending"}
                  </span>
                </div>
                <span className="text-xs text-muted-foreground">
                  {format(new Date(ev.created_at), "MMM d, yyyy")}
                </span>
              </div>
            ))}
            {(dispute.evidence ?? []).length === 0 && (
              <p className="text-sm text-muted-foreground">No evidence uploaded yet.</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
