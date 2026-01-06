import { useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { CalendarRange, Download } from "lucide-react";

type ExportModalProps = {
  open: boolean;
  title: string;
  requireOwner?: boolean;
  onClose: () => void;
  onDownload: (params: { from?: string; to?: string; owner_id?: string }) => Promise<void>;
};

export function ExportModal({ open, title, requireOwner, onClose, onDownload }: ExportModalProps) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [ownerId, setOwnerId] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onDownload({ from: from || undefined, to: to || undefined, owner_id: ownerId || undefined });
      onClose();
    } catch (err: any) {
      setError(err?.message || "Unable to download export.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarRange className="w-5 h-5 text-primary" />
            {title}
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <Label htmlFor="export-from">From</Label>
              <Input id="export-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="export-to">To</Label>
              <Input id="export-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
            </div>
          </div>
          {requireOwner && (
            <div className="space-y-2">
              <Label htmlFor="export-owner">Owner ID</Label>
              <Input
                id="export-owner"
                type="number"
                value={ownerId}
                onChange={(e) => setOwnerId(e.target.value)}
                placeholder="Owner user id"
              />
            </div>
          )}
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleDownload} disabled={submitting || (requireOwner && !ownerId)}>
            <Download className="w-4 h-4 mr-2" />
            {submitting ? "Preparing..." : "Download CSV"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
