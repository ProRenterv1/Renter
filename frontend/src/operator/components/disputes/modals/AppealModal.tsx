import type React from "react";
import { useEffect, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/components/ui/utils";
import type { OperatorDisputeAppealPayload } from "@/operator/api";

type AppealModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: OperatorDisputeAppealPayload) => Promise<boolean>;
};

export function AppealModal({ open, onOpenChange, onSubmit }: AppealModalProps) {
  const [reason, setReason] = useState("");
  const [newEvidence, setNewEvidence] = useState(false);
  const [dueAt, setDueAt] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setReason("");
    setNewEvidence(false);
    setDueAt(getDefaultDueAt(48));
    setErrors({});
  }, [open]);

  const handleSubmit = async () => {
    const validation = validateForm({ reason, dueAt });
    setErrors(validation.errors);
    if (!validation.valid) return;

    const payload: OperatorDisputeAppealPayload = {
      reason: reason.trim(),
      new_evidence_uploaded: newEvidence,
      due_at: validation.dueAtIso,
    };

    setSubmitting(true);
    const ok = await onSubmit(payload);
    setSubmitting(false);
    if (ok) {
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Open appeal</DialogTitle>
          <DialogDescription>
            Create an appeal flow and set a new evidence due date.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="space-y-2">
            <Label>Appeal reason</Label>
            <Textarea
              rows={4}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                clearError("reason", setErrors);
              }}
              placeholder="Why is this dispute being appealed?"
            />
            {errors.reason ? <ErrorText>{errors.reason}</ErrorText> : null}
          </div>

          <div className="space-y-2">
            <Label>Due date</Label>
            <Input
              type="datetime-local"
              value={dueAt}
              onChange={(e) => {
                setDueAt(e.target.value);
                clearError("dueAt", setErrors);
              }}
            />
            {errors.dueAt ? <ErrorText>{errors.dueAt}</ErrorText> : null}
          </div>

          <label className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
            <Checkbox checked={newEvidence} onCheckedChange={(value) => setNewEvidence(Boolean(value))} />
            New evidence uploaded
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Opening..." : "Open appeal"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function validateForm({ reason, dueAt }: { reason: string; dueAt: string }) {
  const errors: Record<string, string> = {};
  if (!reason.trim()) errors.reason = "Reason is required.";
  if (!dueAt) errors.dueAt = "Select a due date.";

  const dueAtIso = toIsoString(dueAt);
  if (dueAt && !dueAtIso) errors.dueAt = "Enter a valid due date.";

  return { valid: Object.keys(errors).length === 0, errors, dueAtIso: dueAtIso ?? "" };
}

function toIsoString(value: string) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function getDefaultDueAt(hoursAhead: number) {
  const now = new Date();
  now.setHours(now.getHours() + hoursAhead);
  return toInputDateTime(now);
}

function toInputDateTime(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function clearError(key: string, setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>) {
  setErrors((prev) => {
    if (!prev[key]) return prev;
    const next = { ...prev };
    delete next[key];
    return next;
  });
}

function ErrorText({ children }: { children: string }) {
  return <p className={cn("text-xs text-destructive", "mt-1")}>{children}</p>;
}
