import { format } from "date-fns";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";
import { JsonDiffDrawer } from "@/operator/components/JsonDiffDrawer";
import type { OperatorAuditEvent } from "@/operator/api";

type AuditJsonDiffDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  event: OperatorAuditEvent | null;
  loading?: boolean;
};

export function AuditJsonDiffDrawer({
  open,
  onOpenChange,
  event,
  loading = false,
}: AuditJsonDiffDrawerProps) {
  const before = event?.before_json ?? (event as any)?.before ?? null;
  const after = event?.after_json ?? (event as any)?.after ?? null;
  const meta = event?.meta_json ?? (event as any)?.meta ?? null;

  const actorLabel = event?.actor
    ? event.actor.name || event.actor.email || `Operator #${event.actor.id}`
    : "Unknown operator";
  const entityLabel = event ? formatEntity(event.entity_type, event.entity_id) : "--";
  const timestampLabel = event?.created_at ? formatDateTime(event.created_at) : "--";
  const hasDiff = before !== null || after !== null;

  const headerContent = event ? (
    <div className="space-y-4 text-sm">
      <div className="grid gap-3 md:grid-cols-2">
        <InfoRow label="Action" value={event.action} />
        <InfoRow label="Entity" value={entityLabel} />
        <InfoRow label="Operator" value={actorLabel} />
        <InfoRow label="Timestamp" value={timestampLabel} />
      </div>
      <Separator />
      <div className="grid gap-3 md:grid-cols-2">
        <InfoRow label="IP address" value={event.ip || "--"} />
        <InfoRow label="User agent" value={event.user_agent || "--"} />
      </div>
      {event.reason ? (
        <div className="rounded-md border border-border bg-muted/40 p-3">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Reason</div>
          <p className="mt-2 text-sm text-foreground whitespace-pre-wrap">{event.reason}</p>
        </div>
      ) : null}
      {meta ? (
        <div className="rounded-md border border-border bg-card p-3">
          <div className="text-xs uppercase tracking-wide text-muted-foreground">Meta</div>
          <pre className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap">
            {safeStringify(meta)}
          </pre>
        </div>
      ) : null}
    </div>
  ) : (
    <div className="rounded-md border border-border bg-muted/30 p-4 text-sm text-muted-foreground">
      Select an audit event to view details.
    </div>
  );

  return (
    <JsonDiffDrawer
      open={open}
      onOpenChange={onOpenChange}
      before={before}
      after={after}
      title="Audit event"
      description={event ? event.action : "Audit details"}
      headerContent={
        <div className="space-y-2">
          {loading ? (
            <Badge variant="outline" className="w-fit">
              Loading details...
            </Badge>
          ) : null}
          {!loading && !hasDiff ? (
            <Badge variant="outline" className="w-fit text-muted-foreground">
              No JSON diff available
            </Badge>
          ) : null}
          {headerContent}
        </div>
      }
    />
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("text-sm", value === "--" ? "text-muted-foreground" : "text-foreground")}>
        {value}
      </div>
    </div>
  );
}

function formatEntity(entityType: string, entityId: string) {
  const normalized = formatLabel(entityType);
  if (!entityId) return normalized || "--";
  return `${normalized} #${entityId}`;
}

function formatLabel(value: string) {
  if (!value) return "--";
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  try {
    return format(parsed, "PPP p");
  } catch {
    return parsed.toLocaleString();
  }
}

function safeStringify(value: unknown) {
  if (value === undefined) return "undefined";
  try {
    const result = JSON.stringify(value, null, 2);
    return result ?? String(value);
  } catch {
    return String(value);
  }
}
