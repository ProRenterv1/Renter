import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { operatorAPI, type OperatorJobRun } from "@/operator/api";
import { useIsOperatorAdmin } from "@/operator/session";
import { DataTable } from "@/operator/components/DataTable";
import { RunJobModal } from "@/operator/components/modals/RunJobModal";
import { ViewJobOutputDrawer } from "@/operator/components/ViewJobOutputDrawer";
import { RefreshCw, Play } from "lucide-react";

const DISPUTES_JOBS: { name: string; label: string; hint: string }[] = [
  {
    name: "auto_close_missing_evidence_disputes",
    label: "Auto-close missing evidence disputes",
    hint: "Closes INTAKE_MISSING_EVIDENCE disputes past their evidence due time.",
  },
  {
    name: "recalc_dispute_window_for_bookings_missing_expires_at",
    label: "Backfill booking dispute windows",
    hint: "Computes dispute_window_expires_at for bookings with return_confirmed_at and missing expiry.",
  },
  {
    name: "scan_disputes_stuck_in_stage",
    label: "Scan disputes stuck in stage",
    hint: "Finds disputes in active stages with stale updated_at (no mutations).",
  },
];

export function JobsPage() {
  const isAdmin = useIsOperatorAdmin();
  const [runs, setRuns] = useState<OperatorJobRun[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [runModalOpen, setRunModalOpen] = useState(false);
  const [defaultJobName, setDefaultJobName] = useState<string | undefined>(undefined);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedRun, setSelectedRun] = useState<OperatorJobRun | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await operatorAPI.jobRuns();
      setRuns(data);
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to load job runs.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const columns = useMemo(() => {
    return [
      {
        key: "id",
        header: "ID",
        className: "w-[80px]",
        cell: (run: OperatorJobRun) => <span className="font-mono text-xs">#{run.id}</span>,
      },
      {
        key: "name",
        header: "Job",
        cell: (run: OperatorJobRun) => (
          <div className="min-w-0">
            <div className="font-medium">{run.name}</div>
            <div className="text-xs text-muted-foreground">
              Requested {run.requested_by_id ? `by #${run.requested_by_id}` : "—"}
            </div>
          </div>
        ),
      },
      {
        key: "status",
        header: "Status",
        className: "w-[140px]",
        cell: (run: OperatorJobRun) => (
          <Badge className={jobStatusBadgeClass(run.status)}>{run.status}</Badge>
        ),
      },
      {
        key: "created",
        header: "Created",
        className: "w-[190px]",
        cell: (run: OperatorJobRun) => <span className="text-sm">{formatDateTime(run.created_at)}</span>,
      },
      {
        key: "finished",
        header: "Finished",
        className: "w-[190px]",
        cell: (run: OperatorJobRun) => (
          <span className="text-sm">{run.finished_at ? formatDateTime(run.finished_at) : "—"}</span>
        ),
      },
    ];
  }, []);

  const handleRun = (jobName?: string) => {
    setDefaultJobName(jobName);
    setRunModalOpen(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="mb-1">Jobs</h2>
          <p className="text-muted-foreground m-0">
            Run operator jobs asynchronously and review outputs.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={load} disabled={loading}>
            <RefreshCw className="w-4 h-4" />
            {loading ? "Refreshing..." : "Refresh"}
          </Button>
          <Button onClick={() => handleRun(undefined)} disabled={!isAdmin}>
            <Play className="w-4 h-4" />
            Run job
          </Button>
        </div>
      </div>

      {error ? (
        <Card>
          <CardContent className="p-6 text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Disputes jobs</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {DISPUTES_JOBS.map((job) => (
              <div key={job.name} className="rounded-lg border border-border bg-card p-4 space-y-3">
                <div>
                  <div className="font-semibold">{job.label}</div>
                  <div className="mt-1 text-sm text-muted-foreground">{job.hint}</div>
                </div>
                <Button variant="outline" onClick={() => handleRun(job.name)} disabled={!isAdmin} className="w-full">
                  <Play className="w-4 h-4" />
                  Run
                </Button>
              </div>
            ))}
          </div>
          {!isAdmin ? (
            <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              Admin access required to run jobs.
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Recent runs</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            columns={columns}
            data={runs}
            isLoading={loading}
            emptyMessage="No job runs yet."
            getRowId={(run) => run.id}
            onRowClick={(run) => {
              setSelectedRun(run);
              setDrawerOpen(true);
            }}
          />
        </CardContent>
      </Card>

      <RunJobModal
        open={runModalOpen}
        onClose={() => setRunModalOpen(false)}
        defaultJobName={defaultJobName}
        onSubmit={async (payload) => {
          if (!isAdmin) return;
          const resp = await operatorAPI.runJob({
            name: payload.name,
            params: payload.params,
            reason: payload.reason,
          });
          toast.success(`Job queued (#${resp.job_run_id})`);
          setRunModalOpen(false);
          await load();
        }}
      />

      <ViewJobOutputDrawer
        open={drawerOpen}
        onOpenChange={(open) => {
          setDrawerOpen(open);
          if (!open) setSelectedRun(null);
        }}
        jobRun={selectedRun}
      />
    </div>
  );
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

