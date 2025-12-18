import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";

type JobParamDef =
  | { key: string; label: string; type: "int"; default: number; help?: string }
  | { key: string; label: string; type: "bool"; default: boolean; help?: string };

type JobDef = {
  name: string;
  label: string;
  group: string;
  description?: string;
  params: JobParamDef[];
};

const JOB_DEFS: JobDef[] = [
  {
    name: "auto_close_missing_evidence_disputes",
    label: "Auto-close disputes missing evidence",
    group: "Disputes",
    description: "Closes disputes stuck in INTAKE_MISSING_EVIDENCE past the evidence due time.",
    params: [{ key: "limit", label: "Limit", type: "int", default: 2000, help: "Max disputes to scan." }],
  },
  {
    name: "recalc_dispute_window_for_bookings_missing_expires_at",
    label: "Backfill booking dispute windows",
    group: "Disputes",
    description: "Recalculates dispute_window_expires_at for bookings with a return confirmation but no expiry.",
    params: [
      { key: "limit", label: "Limit", type: "int", default: 5000, help: "Max bookings to scan." },
      { key: "dry_run", label: "Dry run", type: "bool", default: true, help: "If enabled, no rows are written." },
    ],
  },
  {
    name: "scan_disputes_stuck_in_stage",
    label: "Scan disputes stuck in stage",
    group: "Disputes",
    description: "Lists disputes with stale updated_at in active stages (no mutations).",
    params: [
      { key: "stale_hours", label: "Stale hours", type: "int", default: 48, help: "How old is considered stale." },
      { key: "limit", label: "Limit", type: "int", default: 500, help: "Max disputes to return." },
    ],
  },
];

type RunJobModalProps = {
  open: boolean;
  onClose: () => void;
  defaultJobName?: string;
  onSubmit: (payload: { name: string; params: Record<string, unknown>; reason: string }) => Promise<void>;
};

export function RunJobModal({ open, onClose, defaultJobName, onSubmit }: RunJobModalProps) {
  const defaultName = defaultJobName || JOB_DEFS[0]?.name || "";
  const [name, setName] = useState(defaultName);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const job = useMemo(() => JOB_DEFS.find((j) => j.name === name) || null, [name]);
  const paramsDefs = job?.params || [];

  const [intParams, setIntParams] = useState<Record<string, string>>({});
  const [boolParams, setBoolParams] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (!open) return;
    setName(defaultName);
    setReason("");
    setError(null);
  }, [open, defaultName]);

  useEffect(() => {
    const nextInt: Record<string, string> = {};
    const nextBool: Record<string, boolean> = {};
    for (const def of paramsDefs) {
      if (def.type === "int") nextInt[def.key] = String(def.default);
      if (def.type === "bool") nextBool[def.key] = Boolean(def.default);
    }
    setIntParams(nextInt);
    setBoolParams(nextBool);
  }, [name]); // eslint-disable-line react-hooks/exhaustive-deps

  const canSubmit = Boolean(name && reason.trim() && !submitting);

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const params: Record<string, unknown> = {};
      for (const def of paramsDefs) {
        if (def.type === "int") {
          const raw = intParams[def.key];
          const parsed = Number.parseInt(String(raw), 10);
          params[def.key] = Number.isFinite(parsed) ? parsed : def.default;
        } else if (def.type === "bool") {
          params[def.key] = Boolean(boolParams[def.key]);
        }
      }
      await onSubmit({ name, params, reason: reason.trim() });
      onClose();
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to enqueue job.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Run job</DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Job</Label>
            <Select value={name} onValueChange={setName}>
              <SelectTrigger>
                <SelectValue placeholder="Select job" />
              </SelectTrigger>
              <SelectContent>
                {groupedJobs(JOB_DEFS).map(({ group, jobs }) => (
                  <SelectGroup key={group}>
                    <SelectLabel>{group}</SelectLabel>
                    {jobs.map((j) => (
                      <SelectItem key={j.name} value={j.name}>
                        {j.label}
                      </SelectItem>
                    ))}
                  </SelectGroup>
                ))}
              </SelectContent>
            </Select>
            {job?.description ? <p className="text-xs text-muted-foreground m-0">{job.description}</p> : null}
          </div>

          {paramsDefs.length ? (
            <div className="space-y-3">
              <Label>Parameters</Label>
              <div className="space-y-3">
                {paramsDefs.map((def) =>
                  def.type === "int" ? (
                    <div key={def.key} className="space-y-1">
                      <Label className="text-sm">{def.label}</Label>
                      <Input
                        type="number"
                        step="1"
                        value={intParams[def.key] ?? ""}
                        onChange={(e) => setIntParams((prev) => ({ ...prev, [def.key]: e.target.value }))}
                      />
                      {def.help ? <p className="text-xs text-muted-foreground m-0">{def.help}</p> : null}
                    </div>
                  ) : (
                    <div key={def.key} className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2">
                      <div>
                        <div className="text-sm font-medium">{def.label}</div>
                        {def.help ? <div className="text-xs text-muted-foreground">{def.help}</div> : null}
                      </div>
                      <Switch
                        checked={Boolean(boolParams[def.key])}
                        onCheckedChange={(checked) => setBoolParams((prev) => ({ ...prev, [def.key]: Boolean(checked) }))}
                      />
                    </div>
                  ),
                )}
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label>Reason</Label>
            <Textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Required. Why are you running this job?"
            />
          </div>

          {error ? <p className="text-sm text-destructive m-0">{error}</p> : null}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit}>
            {submitting ? "Enqueuing..." : "Run job"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function groupedJobs(jobs: JobDef[]) {
  const map = new Map<string, JobDef[]>();
  for (const job of jobs) {
    map.set(job.group, [...(map.get(job.group) || []), job]);
  }
  return Array.from(map.entries()).map(([group, groupJobs]) => ({
    group,
    jobs: groupJobs.sort((a, b) => a.label.localeCompare(b.label)),
  }));
}
