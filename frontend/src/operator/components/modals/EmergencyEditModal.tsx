import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { Textarea } from '../../../components/ui/textarea';
import { Label } from '../../../components/ui/label';
import { AlertTriangle } from 'lucide-react';

interface EmergencyEditModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentTitle: string;
  currentDescription: string;
  onConfirm: (data: { title: string; description: string }) => void;
  loading?: boolean;
}

export function EmergencyEditModal({
  open,
  onOpenChange,
  currentTitle,
  currentDescription,
  onConfirm,
  loading = false,
}: EmergencyEditModalProps) {
  const safeTitle = typeof currentTitle === "string" ? currentTitle : "";
  const safeDescription = typeof currentDescription === "string" ? currentDescription : "";
  const [title, setTitle] = useState(safeTitle);
  const [description, setDescription] = useState(safeDescription);
  const [confirmTyped, setConfirmTyped] = useState('');

  useEffect(() => {
    if (open) {
      setTitle(typeof currentTitle === "string" ? currentTitle : "");
      setDescription(typeof currentDescription === "string" ? currentDescription : "");
      setConfirmTyped('');
    }
  }, [open, currentTitle, currentDescription]);

  const baselineTitle = typeof currentTitle === "string" ? currentTitle : "";
  const baselineDescription = typeof currentDescription === "string" ? currentDescription : "";
  const hasChanges =
    title.trim() !== baselineTitle || description.trim() !== baselineDescription;
  const canConfirm = hasChanges && title.trim().length > 0 && confirmTyped === 'CONFIRM';

  const handleConfirm = () => {
    if (canConfirm) {
      onConfirm({ title: title.trim(), description: description.trim() });
      setConfirmTyped('');
    }
  };

  const handleCancel = () => {
    setTitle(currentTitle);
    setDescription(currentDescription);
    setConfirmTyped('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-destructive" />
            Emergency Edit Listing
          </DialogTitle>
          <DialogDescription>
            Make emergency edits to this listing. Use this only for urgent content moderation.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Title */}
          <div className="space-y-2">
            <Label htmlFor="title">
              Listing Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Enter listing title..."
              maxLength={100}
            />
            <p className="text-xs text-muted-foreground">{title.length}/100 characters</p>
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="description">Listing Description</Label>
            <Textarea
              id="description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Enter listing description..."
              rows={6}
              maxLength={1000}
            />
            <p className="text-xs text-muted-foreground">{description.length}/1000 characters</p>
          </div>

          {/* Confirmation */}
          {hasChanges && (
            <div className="space-y-2">
              <Label htmlFor="confirmation">
                Type <span className="font-mono font-bold">CONFIRM</span> to apply changes
              </Label>
              <Input
                id="confirmation"
                value={confirmTyped}
                onChange={(e) => setConfirmTyped(e.target.value)}
                placeholder="CONFIRM"
                autoComplete="off"
              />
            </div>
          )}

          {/* Warning */}
          <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
            <p className="text-sm text-destructive m-0">
              <strong>Warning:</strong> Emergency edits bypass owner approval and are logged for
              audit. The listing owner will be notified of these changes.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel} disabled={loading}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={!canConfirm || loading}>
            {loading ? 'Saving...' : 'Apply Emergency Edit'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
