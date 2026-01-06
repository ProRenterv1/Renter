import { useState } from 'react';
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

interface DeactivateListingModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  listingTitle: string;
  onConfirm: (reason: string) => void;
  loading?: boolean;
}

export function DeactivateListingModal({
  open,
  onOpenChange,
  listingTitle,
  onConfirm,
  loading = false,
}: DeactivateListingModalProps) {
  const [typedConfirmation, setTypedConfirmation] = useState('');
  const [reason, setReason] = useState('');

  const canConfirm = typedConfirmation === 'CONFIRM' && reason.trim().length >= 20;

  const handleConfirm = () => {
    if (canConfirm) {
      onConfirm(reason.trim());
      setTypedConfirmation('');
      setReason('');
    }
  };

  const handleCancel = () => {
    setTypedConfirmation('');
    setReason('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-destructive" />
            Deactivate Listing
          </DialogTitle>
          <DialogDescription>
            This will hide the listing from search and prevent new bookings.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Listing Info */}
          <div className="p-3 rounded-lg bg-muted">
            <p className="text-sm m-0">
              <strong>Listing:</strong> {listingTitle}
            </p>
          </div>

          {/* Reason */}
          <div className="space-y-2">
            <Label htmlFor="reason">
              Reason for Deactivation <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Provide a detailed reason for deactivating this listing..."
              rows={4}
              maxLength={500}
            />
            <p className="text-xs text-muted-foreground">
              {reason.length}/500 characters • Minimum 20 characters required
            </p>
          </div>

          {/* Typed Confirmation */}
          <div className="space-y-2">
            <Label htmlFor="confirmation">
              Type <span className="font-mono font-bold">CONFIRM</span> to proceed
            </Label>
            <Input
              id="confirmation"
              value={typedConfirmation}
              onChange={(e) => setTypedConfirmation(e.target.value)}
              placeholder="CONFIRM"
              autoComplete="off"
            />
          </div>

          {/* Warning */}
          <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
            <p className="text-sm text-destructive m-0">
              <strong>Warning:</strong> This action will be logged and the listing owner may be
              notified. Active bookings will not be affected.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel} disabled={loading}>
            Cancel
          </Button>
          <Button variant="destructive" onClick={handleConfirm} disabled={!canConfirm || loading}>
            {loading ? 'Deactivating...' : 'Deactivate Listing'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
