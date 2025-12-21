import { cn } from "@/components/ui/utils";
import type { OperatorDisputeMessage } from "@/operator/api";

type MessageThreadProps = {
  messages: OperatorDisputeMessage[];
  emptyLabel?: string;
  className?: string;
};

export function MessageThread({
  messages,
  emptyLabel = "No messages yet.",
  className,
}: MessageThreadProps) {
  const sorted = [...messages].sort((a, b) => {
    const aTime = new Date(a.created_at).getTime();
    const bTime = new Date(b.created_at).getTime();
    return aTime - bTime;
  });

  if (sorted.length === 0) {
    return (
      <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      {sorted.map((message) => {
        const tone = messageTone(message.author_role);
        return (
          <div key={message.id} className={cn("flex", tone.align)}>
            <div className={cn("max-w-[80%] rounded-xl border p-3 text-sm", tone.bubble)}>
              <div className="flex items-center justify-between gap-3 text-[0.65rem] uppercase tracking-wide text-muted-foreground">
                <span>{formatRoleLabel(message)}</span>
                <span className="normal-case">{formatDateTime(message.created_at)}</span>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm">
                {message.body || "(no message)"}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function messageTone(role: OperatorDisputeMessage["author_role"]) {
  if (role === "operator") {
    return {
      align: "justify-end",
      bubble:
        "bg-[var(--info-bg)] text-[var(--info-text)] border-[var(--info-border)]",
    };
  }
  if (role === "system") {
    return {
      align: "justify-center",
      bubble:
        "bg-[var(--warning-bg)] text-[var(--warning-text)] border-[var(--warning-border)]",
    };
  }
  if (role === "owner") {
    return {
      align: "justify-start",
      bubble: "bg-muted/50 text-foreground border-border",
    };
  }
  return {
    align: "justify-start",
    bubble: "bg-card text-foreground border-border",
  };
}

function formatRoleLabel(message: OperatorDisputeMessage) {
  const roleLabel = formatRole(message.author_role);
  const label = message.author_label?.trim();
  if (label) {
    return `${roleLabel} • ${label}`;
  }
  return roleLabel;
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatRole(role: OperatorDisputeMessage["author_role"]) {
  if (role === "operator") return "Operator";
  if (role === "system") return "System";
  if (role === "owner") return "Owner";
  if (role === "renter") return "Renter";
  return role;
}
