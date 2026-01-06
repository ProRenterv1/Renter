import { Badge } from "@/components/ui/badge";
import { cn } from "@/components/ui/utils";

type StageBadgeProps = {
  stage: string;
  className?: string;
};

type CountdownChipProps = {
  dueAt?: string | Date | null;
  kind?: "evidence" | "rebuttal";
  label?: string;
  className?: string;
};

type AvStatusChipProps = {
  status: string;
  className?: string;
};

type PromotedBadgeProps = {
  label?: string;
  className?: string;
};

const STAGE_STYLES: Record<string, { label: string; className: string }> = {
  intake: {
    label: "Intake",
    className: "bg-[var(--info-bg)] text-[var(--info-text)] border-[var(--info-border)]",
  },
  awaiting_rebuttal: {
    label: "Awaiting rebuttal",
    className: "bg-[var(--warning-bg)] text-[var(--warning-text)] border-[var(--warning-border)]",
  },
  under_review: {
    label: "Under review",
    className: "bg-[var(--accent)] text-[var(--accent-foreground)] border-border",
  },
  resolved: {
    label: "Resolved",
    className: "bg-[var(--success-bg)] text-[var(--success-text)] border-[var(--success-border)]",
  },
};

const AV_STATUS_STYLES: Record<string, { label: string; className: string }> = {
  clean: {
    label: "Clean",
    className: "bg-[var(--success-bg)] text-[var(--success-text)] border-[var(--success-border)]",
  },
  pending: {
    label: "Pending",
    className: "bg-[var(--info-bg)] text-[var(--info-text)] border-[var(--info-border)]",
  },
  blocked: {
    label: "Blocked",
    className: "bg-[var(--warning-bg)] text-[var(--warning-text)] border-[var(--warning-border)]",
  },
  failed: {
    label: "Failed",
    className: "bg-[var(--error-bg)] text-[var(--error-text)] border-[var(--error-border)]",
  },
  infected: {
    label: "Infected",
    className: "bg-[var(--error-solid)] text-white border-transparent",
  },
};

export function StageBadge({ stage, className }: StageBadgeProps) {
  const normalized = normalizeKey(stage);
  const fallbackLabel = toTitleCase(stage || "Stage");
  const config = STAGE_STYLES[normalized] ?? {
    label: fallbackLabel,
    className: "bg-muted text-muted-foreground border-border",
  };

  return (
    <Badge
      variant="outline"
      className={cn("rounded-full px-3 py-1 text-[0.7rem] font-semibold", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}

export function CountdownChip({ dueAt, kind = "evidence", label, className }: CountdownChipProps) {
  if (!dueAt) return null;
  const parsed = typeof dueAt === "string" || dueAt instanceof Date ? new Date(dueAt) : null;
  if (!parsed || Number.isNaN(parsed.getTime())) {
    return (
      <Badge variant="outline" className={cn("rounded-full px-3 py-1 text-[0.7rem]", className)}>
        {label ?? (kind === "rebuttal" ? "Rebuttal due" : "Evidence due")} - --
      </Badge>
    );
  }

  const { timeLabel, isOverdue } = formatCountdown(parsed);
  const baseLabel = label ?? (kind === "rebuttal" ? "Rebuttal due" : "Evidence due");
  const toneClass = isOverdue
    ? "bg-[var(--error-bg)] text-[var(--error-text)] border-[var(--error-border)]"
    : "bg-[var(--warning-bg)] text-[var(--warning-text)] border-[var(--warning-border)]";
  const statusLabel = isOverdue ? `Overdue ${timeLabel}` : timeLabel;

  return (
    <Badge variant="outline" className={cn("rounded-full px-3 py-1 text-[0.7rem]", toneClass, className)}>
      {baseLabel} - {statusLabel}
    </Badge>
  );
}

export function AvStatusChip({ status, className }: AvStatusChipProps) {
  const normalized = normalizeKey(status);
  const fallbackLabel = toTitleCase(status || "Status");
  const config = AV_STATUS_STYLES[normalized] ?? {
    label: fallbackLabel,
    className: "bg-muted text-muted-foreground border-border",
  };

  return (
    <Badge
      variant="outline"
      className={cn("rounded-full px-3 py-1 text-[0.7rem] font-semibold", config.className, className)}
    >
      {config.label}
    </Badge>
  );
}

export function PromotedBadge({ label = "Promoted", className }: PromotedBadgeProps) {
  return (
    <Badge
      variant="outline"
      className={cn(
        "rounded-full border-transparent bg-[var(--promoted)] px-3 py-1 text-[0.7rem] font-semibold text-[#7a4b1c]",
        className,
      )}
    >
      {label}
    </Badge>
  );
}

function normalizeKey(value: string) {
  return value
    .toLowerCase()
    .replace(/\s+/g, "_")
    .replace(/-+/g, "_")
    .trim();
}

function toTitleCase(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
}

function formatCountdown(target: Date) {
  const diffMs = target.getTime() - Date.now();
  const isOverdue = diffMs < 0;
  const absMinutes = Math.max(Math.floor(Math.abs(diffMs) / 60000), 0);

  const days = Math.floor(absMinutes / 1440);
  const hours = Math.floor((absMinutes % 1440) / 60);
  const minutes = absMinutes % 60;

  const parts: string[] = [];
  if (days > 0) {
    parts.push(`${days}d`);
    if (hours > 0) {
      parts.push(`${hours}h`);
    }
  } else {
    if (hours > 0) {
      parts.push(`${hours}h`);
    }
    if (hours < 6) {
      parts.push(`${minutes}m`);
    }
  }
  if (parts.length === 0) {
    parts.push("0m");
  }

  return { timeLabel: parts.join(" "), isOverdue };
}
