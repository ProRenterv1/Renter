import type React from "react";
import { useEffect, useMemo, useState } from "react";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";
import { formatCurrency, parseMoney } from "@/lib/utils";
import type {
  OperatorDisputeResolvePayload,
  OperatorDisputeBookingContext,
} from "@/operator/api";

const DECISION_OPTIONS = [
  { value: "renter", label: "Renter" },
  { value: "owner", label: "Owner" },
  { value: "partial", label: "Partial" },
  { value: "deny", label: "Deny" },
] as const;

type ResolveDisputeModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: OperatorDisputeResolvePayload) => Promise<boolean>;
  booking: OperatorDisputeBookingContext | null;
  openedByRole?: OperatorDisputeResolvePayload["opened_by_role"];
};

export function ResolveDisputeModal({
  open,
  onOpenChange,
  onSubmit,
  booking,
  openedByRole,
}: ResolveDisputeModalProps) {
  const [decision, setDecision] = useState<OperatorDisputeResolvePayload["decision"]>("renter");
  const [refundAmount, setRefundAmount] = useState("");
  const [captureAmount, setCaptureAmount] = useState("");
  const [suspendListing, setSuspendListing] = useState(false);
  const [markRenterSuspicious, setMarkRenterSuspicious] = useState(false);
  const [markOwnerSuspicious, setMarkOwnerSuspicious] = useState(false);
  const [notes, setNotes] = useState("");
  const [confirmText, setConfirmText] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [step, setStep] = useState<"form" | "confirm">("form");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setDecision("renter");
    setRefundAmount("");
    setCaptureAmount("");
    setSuspendListing(false);
    setMarkRenterSuspicious(false);
    setMarkOwnerSuspicious(false);
    setNotes("");
    setConfirmText("");
    setErrors({});
    setStep("form");
  }, [open]);

  const { refundValue, captureValue, depositHold, depositReleaseLabel, ownerPayout } = useMemo(() => {
    const refundValue = parseAmount(refundAmount);
    const captureValue = parseAmount(captureAmount);
    const depositHoldCents = booking?.totals?.deposit_hold_cents;
    const depositHold =
      typeof depositHoldCents === "number" && Number.isFinite(depositHoldCents)
        ? depositHoldCents / 100
        : null;
    let depositReleaseLabel = "--";
    if (depositHold !== null) {
      depositReleaseLabel = captureValue.value < depositHold ? "Yes" : "No";
    }
    return {
      refundValue,
      captureValue,
      depositHold,
      depositReleaseLabel,
      ownerPayout: captureValue.value,
    };
  }, [refundAmount, captureAmount, booking]);

  const handleContinue = () => {
    const validation = validateForm({ decision, notes, refundValue, captureValue });
    setErrors(validation.errors);
    if (!validation.valid) return;
    setStep("confirm");
  };

  const handleSubmit = async () => {
    if (confirmText.trim().toUpperCase() !== "CONFIRM") {
      setErrors((prev) => ({ ...prev, confirm: "Type CONFIRM to submit." }));
      return;
    }

    setSubmitting(true);
    const ok = await onSubmit({
      decision,
      refund_amount: refundValue.value,
      deposit_capture_amount: captureValue.value,
      reason: notes.trim(),
      opened_by_role: openedByRole,
      suspend_listing: suspendListing,
      mark_renter_suspicious: markRenterSuspicious,
      mark_owner_suspicious: markOwnerSuspicious,
      notes: notes.trim(),
    });
    setSubmitting(false);
    if (ok) {
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Resolve dispute</DialogTitle>
          <DialogDescription>
            Choose a decision, apply financial actions, and confirm the outcome.
          </DialogDescription>
        </DialogHeader>

        {step === "form" ? (
          <div className="space-y-5 py-2">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Decision</Label>
                <Select
                  value={decision}
                  onValueChange={(value) => {
                    setDecision(value as OperatorDisputeResolvePayload["decision"]);
                    clearError("decision", setErrors);
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select decision" />
                  </SelectTrigger>
                  <SelectContent>
                    {DECISION_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {errors.decision ? <ErrorText>{errors.decision}</ErrorText> : null}
              </div>
            <div className="space-y-2">
              <Label>Reason</Label>
              <Textarea
                rows={3}
                value={notes}
                onChange={(e) => {
                  setNotes(e.target.value);
                  clearError("notes", setErrors);
                }}
                placeholder="Provide the reason for this resolution"
              />
              {errors.notes ? <ErrorText>{errors.notes}</ErrorText> : null}
            </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>Refund amount (CAD)</Label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={refundAmount}
                  onChange={(e) => {
                    setRefundAmount(e.target.value);
                    clearError("refund", setErrors);
                  }}
                />
                {errors.refund ? <ErrorText>{errors.refund}</ErrorText> : null}
              </div>
              <div className="space-y-2">
                <Label>Deposit capture amount (CAD)</Label>
                <Input
                  type="number"
                  step="0.01"
                  placeholder="0.00"
                  value={captureAmount}
                  onChange={(e) => {
                    setCaptureAmount(e.target.value);
                    clearError("capture", setErrors);
                  }}
                />
                {errors.capture ? <ErrorText>{errors.capture}</ErrorText> : null}
              </div>
            </div>

            <Separator />

            <div className="grid gap-3 sm:grid-cols-2">
              <CheckboxRow
                checked={suspendListing}
                onCheckedChange={setSuspendListing}
                label="Suspend listing (safety)"
              />
              <CheckboxRow
                checked={markRenterSuspicious}
                onCheckedChange={setMarkRenterSuspicious}
                label="Mark renter suspicious"
              />
              <CheckboxRow
                checked={markOwnerSuspicious}
                onCheckedChange={setMarkOwnerSuspicious}
                label="Mark owner suspicious"
              />
            </div>
          </div>
        ) : (
          <div className="space-y-4 py-2">
            <div className="rounded-lg border border-border bg-muted/40 p-4">
              <div className="text-sm font-semibold text-foreground">Resolution impact</div>
              <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                <SummaryRow label="Decision" value={formatLabel(decision)} />
                <SummaryRow label="Refund" value={formatCurrency(refundValue.value, "CAD")} />
                <SummaryRow label="Capture" value={formatCurrency(captureValue.value, "CAD")} />
                <SummaryRow label="Owner payout from capture" value={formatCurrency(ownerPayout, "CAD")} />
                <SummaryRow label="Deposit release" value={depositReleaseLabel} />
                {depositHold !== null ? (
                  <SummaryRow label="Deposit hold" value={formatCurrency(depositHold, "CAD")} />
                ) : null}
              </div>
              <Separator className="my-3" />
              <div className="space-y-2 text-xs text-muted-foreground">
                {suspendListing ? <div>Listing will be suspended.</div> : null}
                {markRenterSuspicious ? <div>Renter will be marked suspicious.</div> : null}
                {markOwnerSuspicious ? <div>Owner will be marked suspicious.</div> : null}
                <div>Reason: {notes.trim()}</div>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Type CONFIRM to submit</Label>
              <Input
                value={confirmText}
                onChange={(e) => {
                  setConfirmText(e.target.value);
                  clearError("confirm", setErrors);
                }}
                placeholder="CONFIRM"
              />
              {errors.confirm ? <ErrorText>{errors.confirm}</ErrorText> : null}
            </div>
          </div>
        )}

        <DialogFooter>
          {step === "confirm" ? (
            <Button variant="outline" onClick={() => setStep("form")}>Back</Button>
          ) : (
            <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          )}
          {step === "confirm" ? (
            <Button
              onClick={handleSubmit}
              disabled={submitting}
            >
              {submitting ? "Resolving..." : "Confirm resolution"}
            </Button>
          ) : (
            <Button onClick={handleContinue}>Continue</Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CheckboxRow({
  checked,
  onCheckedChange,
  label,
}: {
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
  label: string;
}) {
  return (
    <label className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
      <Checkbox checked={checked} onCheckedChange={(value) => onCheckedChange(Boolean(value))} />
      {label}
    </label>
  );
}

function validateForm({
  decision,
  notes,
  refundValue,
  captureValue,
}: {
  decision: string;
  notes: string;
  refundValue: ReturnType<typeof parseAmount>;
  captureValue: ReturnType<typeof parseAmount>;
}) {
  const errors: Record<string, string> = {};
  if (!decision) errors.decision = "Select a decision.";
  if (!notes.trim()) errors.notes = "Reason is required.";
  if (!refundValue.valid) errors.refund = refundValue.error;
  if (!captureValue.valid) errors.capture = captureValue.error;
  return { valid: Object.keys(errors).length === 0, errors };
}

function parseAmount(raw: string) {
  const trimmed = raw.trim();
  if (!trimmed) return { value: 0, valid: true, error: "" };
  const normalized = trimmed.replace(/,/g, "");
  const numeric = Number(normalized);
  if (!Number.isFinite(numeric)) {
    return { value: 0, valid: false, error: "Enter a valid amount." };
  }
  if (numeric < 0) {
    return { value: numeric, valid: false, error: "Amount must be positive." };
  }
  return { value: parseMoney(numeric), valid: true, error: "" };
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

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>{label}</span>
      <span className={cn("text-foreground", "font-medium")}>{value}</span>
    </div>
  );
}

function ErrorText({ children }: { children: string }) {
  return <p className={cn("text-xs text-destructive", "mt-1")}>{children}</p>;
}
