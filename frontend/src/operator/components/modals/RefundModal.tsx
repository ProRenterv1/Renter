import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { AlertTriangle } from "lucide-react";

type RefundModalProps = {
  open: boolean;
  onClose: () => void;
  onSubmit: (payload: { amount?: string; reason: string; notify_user: boolean }) => Promise<void>;
  defaultAmount?: string;
};

export function RefundModal({ open, onClose, onSubmit, defaultAmount }: RefundModalProps) {
  const [amount, setAmount] = useState<string>(defaultAmount || "");
  const [reason, setReason] = useState<string>("");
  const [notify, setNotify] = useState<boolean>(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({ amount: amount.trim() || undefined, reason: reason.trim(), notify_user: notify });
      onClose();
      setReason("");
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to process refund.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            Issue Refund
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <Label htmlFor="refund-amount">Amount (optional)</Label>
            <Input
              id="refund-amount"
              type="number"
              min="0"
              step="0.01"
              placeholder="Full refund if left blank"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="refund-reason">Reason</Label>
            <Textarea
              id="refund-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why is this refund being issued?"
              rows={3}
            />
          </div>
          <div className="flex items-center gap-2">
            <Checkbox id="notify-user" checked={notify} onCheckedChange={(v) => setNotify(Boolean(v))} />
            <Label htmlFor="notify-user">Notify renter about this refund</Label>
          </div>
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Money-impacting action. Double-check amount and reason before confirming.
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting || !reason.trim()}>
            {submitting ? "Processing..." : "Confirm refund"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
