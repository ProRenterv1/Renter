import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { RightDrawer } from "@/operator/components/RightDrawer";
import type { OperatorJobRun } from "@/operator/api";
import { copyToClipboard } from "@/operator/utils/clipboard";
import { Copy } from "lucide-react";

export function ViewJobOutputDrawer({
  open,
  onOpenChange,
  jobRun,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  jobRun: OperatorJobRun | null;
}) {
  const title = jobRun ? `Job #${jobRun.id}` : "Job output";
  const status = jobRun?.status || "—";

  const statusBadge = jobRun ? (
    <Badge className={jobStatusBadgeClass(jobRun.status)}>{jobRun.status}</Badge>
  ) : null;

  return (
    <RightDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={jobRun ? jobRun.name : undefined}
    >
      {jobRun ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm text-muted-foreground">
              Status: <span className="font-medium text-foreground">{status}</span>
            </div>
            {statusBadge}
          </div>

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <div className="text-xs text-muted-foreground">Created</div>
              <div className="font-medium">{formatDateTime(jobRun.created_at)}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Finished</div>
              <div className="font-medium">{jobRun.finished_at ? formatDateTime(jobRun.finished_at) : "—"}</div>
            </div>
            <div>
              <div className="text-xs text-muted-foreground">Requested by</div>
              <div className="font-medium">{jobRun.requested_by_id ? `#${jobRun.requested_by_id}` : "—"}</div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold">Params</div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => copyToClipboard(JSON.stringify(jobRun.params ?? {}, null, 2), "Params")}
              >
                <Copy className="w-4 h-4" />
                Copy
              </Button>
            </div>
            <pre className="max-h-60 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
              {safeJson(jobRun.params ?? {})}
            </pre>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-sm font-semibold">Output</div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => copyToClipboard(JSON.stringify(jobRun.output_json ?? null, null, 2), "Output")}
              >
                <Copy className="w-4 h-4" />
                Copy
              </Button>
            </div>
            <pre className="max-h-[28rem] overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs">
              {safeJson(jobRun.output_json ?? null)}
            </pre>
          </div>
        </div>
      ) : (
        <div className="text-sm text-muted-foreground">Select a job run to view output.</div>
      )}
    </RightDrawer>
  );
}

function safeJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function formatDateTime(value: string) {
  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toLocaleString();
}

function jobStatusBadgeClass(status: OperatorJobRun["status"]) {
  if (status === "succeeded") return "bg-[var(--success-solid)] text-white border-transparent";
  if (status === "failed") return "bg-[var(--error-solid)] text-white border-transparent";
  if (status === "running") return "bg-[var(--info-border)] text-foreground border-transparent";
  return "bg-muted text-foreground border-border";
}

