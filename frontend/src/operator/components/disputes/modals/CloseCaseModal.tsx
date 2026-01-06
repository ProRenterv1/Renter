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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/components/ui/utils";
import type { OperatorDisputeClosePayload } from "@/operator/api";

const REASON_OPTIONS = [
  { value: "late", label: "Late" },
  { value: "duplicate", label: "Duplicate" },
  { value: "no_evidence", label: "No evidence" },
] as const;

type CloseCaseModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: OperatorDisputeClosePayload) => Promise<boolean>;
};

export function CloseCaseModal({ open, onOpenChange, onSubmit }: CloseCaseModalProps) {
  const [reason, setReason] = useState<OperatorDisputeClosePayload["reason"]>("late");
  const [notes, setNotes] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState<"form" | "confirm">("form");

  useEffect(() => {
    if (!open) return;
    setReason("late");
    setNotes("");
    setErrors({});
    setStep("form");
  }, [open]);

  const handleContinue = () => {
    const validation = validateForm({ reason, notes });
    setErrors(validation.errors);
    if (!validation.valid) return;
    setStep("confirm");
  };

  const handleSubmit = async () => {
    setSubmitting(true);
    const ok = await onSubmit({ reason, notes: notes.trim() });
    setSubmitting(false);
    if (ok) {
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Close case</DialogTitle>
          <DialogDescription>
            Close the dispute and record a reason for audit.
          </DialogDescription>
        </DialogHeader>

        {step === "form" ? (
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>Reason</Label>
              <Select
                value={reason}
                onValueChange={(value) => {
                  setReason(value as OperatorDisputeClosePayload["reason"]);
                  clearError("reason", setErrors);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select reason" />
                </SelectTrigger>
                <SelectContent>
                  {REASON_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.reason ? <ErrorText>{errors.reason}</ErrorText> : null}
            </div>
            <div className="space-y-2">
              <Label>Notes</Label>
              <Textarea
                rows={4}
                value={notes}
                onChange={(e) => {
                  setNotes(e.target.value);
                  clearError("notes", setErrors);
                }}
                placeholder="Explain why this case is being closed"
              />
              {errors.notes ? <ErrorText>{errors.notes}</ErrorText> : null}
            </div>
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <div className="rounded-md border border-border bg-muted/40 p-4 text-sm">
              <div className="text-sm font-semibold text-foreground">Confirm closure</div>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <div className="flex items-center justify-between">
                  <span>Reason</span>
                  <span className="text-foreground">{formatLabel(reason)}</span>
                </div>
                <div>
                  <div className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">Notes</div>
                  <p className="text-sm text-foreground whitespace-pre-wrap">{notes.trim()}</p>
                </div>
              </div>
            </div>
            <div className="rounded-md border border-[var(--warning-border)] bg-[var(--warning-bg)] p-3 text-xs text-[var(--warning-text)]">
              Closing the case will stop any active evidence or rebuttal flows.
            </div>
          </div>
        )}

        <DialogFooter>
          {step === "confirm" ? (
            <Button variant="outline" onClick={() => setStep("form")}>
              Back
            </Button>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
          )}
          {step === "confirm" ? (
            <Button onClick={handleSubmit} disabled={submitting}>
              {submitting ? "Closing..." : "Close case"}
            </Button>
          ) : (
            <Button onClick={handleContinue}>Continue</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function validateForm({ reason, notes }: { reason: string; notes: string }) {
  const errors: Record<string, string> = {};
  if (!reason) errors.reason = "Select a reason.";
  if (!notes.trim()) errors.notes = "Notes are required.";
  return { valid: Object.keys(errors).length === 0, errors };
}

function formatLabel(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
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
