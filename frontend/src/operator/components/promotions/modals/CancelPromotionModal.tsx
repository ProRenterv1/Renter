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
import { cn } from "@/components/ui/utils";
import type { OperatorPromotionCancelPayload, OperatorPromotionListItem } from "@/operator/api";

type CancelPromotionModalProps = {
  open: boolean;
  promotion: OperatorPromotionListItem | null;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: OperatorPromotionCancelPayload) => Promise<boolean>;
};

export function CancelPromotionModal({
  open,
  promotion,
  onOpenChange,
  onSubmit,
}: CancelPromotionModalProps) {
  const [reason, setReason] = useState("");
  const [note, setNote] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setReason("");
    setNote("");
    setErrors({});
  }, [open]);

  const handleSubmit = async () => {
    const validation = validateForm({ reason });
    setErrors(validation.errors);
    if (!validation.valid) return;

    const payload: OperatorPromotionCancelPayload = {
      reason: reason.trim(),
      note: note.trim() || undefined,
    };

    setSubmitting(true);
    const ok = await onSubmit(payload);
    setSubmitting(false);
    if (ok) {
      onOpenChange(false);
    }
  };

  const listingLabel = promotion?.listing_title || (promotion ? `Listing #${promotion.listing}` : "Listing");
  const ownerLabel = promotion?.owner_email || promotion?.owner_name || "Unknown owner";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Cancel promotion</DialogTitle>
          <DialogDescription>
            Stop the promotion early and record the reason.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground">
            <div className="text-foreground font-medium">{listingLabel}</div>
            <div className="text-xs">Owner: {ownerLabel}</div>
            {promotion ? (
              <div className="text-xs">Promotion ID: {promotion.id}</div>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label>Reason</Label>
            <Textarea
              rows={3}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                clearError("reason", setErrors);
              }}
              placeholder="Required for audit trail"
            />
            {errors.reason ? <ErrorText>{errors.reason}</ErrorText> : null}
          </div>

          <div className="space-y-2">
            <Label>Refund path note (optional)</Label>
            <Textarea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Optional note for finance or support"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Canceling..." : "Cancel promotion"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function validateForm({ reason }: { reason: string }) {
  const errors: Record<string, string> = {};
  if (!reason.trim()) errors.reason = "Reason is required.";
  return { valid: Object.keys(errors).length === 0, errors };
}

function clearError(
  key: string,
  setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>,
) {
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
