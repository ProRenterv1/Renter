import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { AlertTriangle, ShieldCheck } from "lucide-react";

type Mode = "capture" | "release";

type DepositActionModalProps = {
  open: boolean;
  mode: Mode;
  onClose: () => void;
  onSubmit: (payload: { amount?: string; reason: string }) => Promise<void>;
};

export function DepositActionModal({ open, mode, onClose, onSubmit }: DepositActionModalProps) {
  const [amount, setAmount] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isCapture = mode === "capture";
  const title = isCapture ? "Capture deposit" : "Release deposit";
  const warning = isCapture
    ? "Capturing will charge the renter’s card using the existing deposit hold."
    : "Releasing will cancel the deposit hold if not already captured.";

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ amount: isCapture ? amount.trim() : undefined, reason: reason.trim() });
      onClose();
      setReason("");
      setAmount("");
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to process deposit action.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isCapture ? <AlertTriangle className="w-5 h-5 text-amber-500" /> : <ShieldCheck className="w-5 h-5 text-emerald-500" />}
            {title}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {isCapture && (
            <div>
              <Label htmlFor="deposit-amount">Amount</Label>
              <Input
                id="deposit-amount"
                type="number"
                min="0"
                step="0.01"
                placeholder="e.g. 150.00"
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="deposit-reason">Reason</Label>
            <Textarea
              id="deposit-reason"
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why are you performing this deposit action?"
            />
          </div>
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            {warning}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !reason.trim() || (isCapture && !amount.trim())}>
            {submitting ? "Processing..." : isCapture ? "Capture" : "Release"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
