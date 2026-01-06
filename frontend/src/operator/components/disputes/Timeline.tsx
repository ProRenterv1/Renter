import {
  AlertCircle,
  Bell,
  CheckCircle2,
  Clock,
  ShieldAlert,
  UserCog,
} from "lucide-react";

import { cn } from "@/components/ui/utils";
import type { OperatorDisputeTimelineItem } from "@/operator/api";

type TimelineProps = {
  items: OperatorDisputeTimelineItem[];
  emptyLabel?: string;
  className?: string;
};

export function Timeline({
  items,
  emptyLabel = "No timeline events yet.",
  className,
}: TimelineProps) {
  const sorted = [...items].sort((a, b) => {
    const aTime = new Date(a.created_at).getTime();
    const bTime = new Date(b.created_at).getTime();
    return aTime - bTime;
  });

  if (!sorted.length) {
    return (
      <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className={cn("space-y-4", className)}>
      {sorted.map((item, index) => {
        const tone = timelineTone(item.type);
        const icon = timelineIcon(item.type);
        return (
          <div key={item.id} className="relative">
            {index < sorted.length - 1 ? (
              <div className="absolute left-2.5 top-8 bottom-0 w-0.5 bg-border" />
            ) : null}
            <div className="flex gap-3">
              <div className="relative">
                <div
                  className={cn(
                    "flex h-5 w-5 items-center justify-center rounded-full border-2 bg-background",
                    tone,
                  )}
                >
                  {icon}
                </div>
              </div>
              <div className="flex-1 pb-4">
                <p className="mb-1 text-sm font-medium text-foreground">{item.label}</p>
                {item.description ? (
                  <p className="mb-1 text-xs text-muted-foreground">{item.description}</p>
                ) : null}
                <div className="flex flex-wrap items-center gap-2 text-[0.65rem] text-muted-foreground">
                  {item.actor_label ? <span>{item.actor_label}</span> : null}
                  <span>{formatDateTime(item.created_at)}</span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function timelineIcon(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes("stage") || normalized.includes("status")) {
    return <CheckCircle2 className="h-4 w-4" />;
  }
  if (normalized.includes("reminder") || normalized.includes("due")) {
    return <Bell className="h-4 w-4" />;
  }
  if (normalized.includes("flag") || normalized.includes("safety")) {
    return <ShieldAlert className="h-4 w-4" />;
  }
  if (normalized.includes("action") || normalized.includes("operator")) {
    return <UserCog className="h-4 w-4" />;
  }
  if (normalized.includes("alert") || normalized.includes("overdue")) {
    return <AlertCircle className="h-4 w-4" />;
  }
  return <Clock className="h-4 w-4" />;
}

function timelineTone(type: string) {
  const normalized = type.toLowerCase();
  if (normalized.includes("resolved") || normalized.includes("complete")) {
    return "text-[var(--success-solid)]";
  }
  if (normalized.includes("overdue") || normalized.includes("missed")) {
    return "text-destructive";
  }
  if (normalized.includes("reminder") || normalized.includes("due")) {
    return "text-[var(--warning-strong)]";
  }
  return "text-primary";
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}
