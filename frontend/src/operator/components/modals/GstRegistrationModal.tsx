import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type GstRegistrationModalProps = {
  open: boolean;
  mode: "enable" | "disable";
  initialGstNumber?: string | null;
  onClose: () => void;
  onSubmit: (payload: { gstNumber?: string; reason: string }) => Promise<void>;
  onSavingChange?: (saving: boolean) => void;
};

export function GstRegistrationModal({
  open,
  mode,
  initialGstNumber,
  onClose,
  onSubmit,
  onSavingChange,
}: GstRegistrationModalProps) {
  const [gstNumber, setGstNumber] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setGstNumber(initialGstNumber?.trim() || "");
    setReason("");
    setError(null);
    setSubmitting(false);
  }, [open, initialGstNumber]);

  const trimmedNumber = gstNumber.trim();
  const trimmedReason = reason.trim();

  const canSubmit = useMemo(() => {
    if (!trimmedReason) return false;
    if (mode === "enable" && !trimmedNumber) return false;
    return true;
  }, [mode, trimmedReason, trimmedNumber]);

  const handleSubmit = async () => {
    if (!canSubmit || submitting) return;
    setSubmitting(true);
    onSavingChange?.(true);
    setError(null);
    try {
      await onSubmit({ gstNumber: trimmedNumber, reason: trimmedReason });
      onClose();
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to update GST setting.");
    } finally {
      setSubmitting(false);
      onSavingChange?.(false);
    }
  };

  const title = mode === "enable" ? "Enable GST registration" : "Disable GST registration";
  const ctaLabel = mode === "enable" ? "Enable GST" : "Disable GST";

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {mode === "enable" ? (
            <div className="space-y-2">
              <Label>GST number</Label>
              <Input
                value={gstNumber}
                onChange={(e) => setGstNumber(e.target.value)}
                placeholder="123456789RT0001"
              />
              <p className="text-xs text-muted-foreground m-0">
                Required to enable GST. Enter the CRA format with no spaces.
              </p>
            </div>
          ) : (
            <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
              GST will no longer be applied to platform fees or promotion charges.
            </div>
          )}

          <div className="space-y-2">
            <Label>Reason</Label>
            <Textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Required. Why are you making this change?"
            />
          </div>

          {error ? <p className="text-sm text-destructive m-0">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
            {submitting ? "Saving..." : ctaLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
