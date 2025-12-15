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
import { Textarea } from '../../../components/ui/textarea';
import { Label } from '../../../components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../../components/ui/select';
import { AlertCircle } from 'lucide-react';

interface MarkNeedsReviewModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  listingTitle: string;
  onConfirm: (data: { reason: string; tag?: string }) => void;
  loading?: boolean;
}

const reviewTags = [
  { value: 'safety_concern', label: 'Safety Concern' },
  { value: 'quality_issue', label: 'Quality Issue' },
  { value: 'missing_info', label: 'Missing Information' },
  { value: 'policy_violation', label: 'Policy Violation' },
  { value: 'user_report', label: 'User Report' },
  { value: 'other', label: 'Other' },
];

export function MarkNeedsReviewModal({
  open,
  onOpenChange,
  listingTitle,
  onConfirm,
  loading = false,
}: MarkNeedsReviewModalProps) {
  const [reason, setReason] = useState('');
  const [tag, setTag] = useState<string>('');

  const canSubmit = reason.trim().length >= 20;

  const handleSubmit = () => {
    if (canSubmit) {
      onConfirm({ reason: reason.trim(), tag: tag || undefined });
      setReason('');
      setTag('');
    }
  };

  const handleCancel = () => {
    setReason('');
    setTag('');
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-orange-600" />
            Mark Listing for Review
          </DialogTitle>
          <DialogDescription>
            Flag this listing for manual review by the moderation team.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Listing Info */}
          <div className="p-3 rounded-lg bg-muted">
            <p className="text-sm m-0">
              <strong>Listing:</strong> {listingTitle}
            </p>
          </div>

          {/* Tag (Optional) */}
          <div className="space-y-2">
            <Label htmlFor="tag">Internal Tag (Optional)</Label>
            <Select value={tag} onValueChange={setTag}>
              <SelectTrigger id="tag">
                <SelectValue placeholder="Select a tag..." />
              </SelectTrigger>
              <SelectContent>
                {reviewTags.map((t) => (
                  <SelectItem key={t.value} value={t.value}>
                    {t.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Reason */}
          <div className="space-y-2">
            <Label htmlFor="reason">
              Reason <span className="text-destructive">*</span>
            </Label>
            <Textarea
              id="reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Describe why this listing needs review..."
              rows={4}
              maxLength={500}
            />
            <p className="text-xs text-muted-foreground">
              {reason.length}/500 characters • Minimum 20 characters required
            </p>
          </div>

          {/* Info */}
          <div className="p-3 rounded-lg bg-primary/10 border border-primary/20">
            <p className="text-sm text-primary m-0">
              <strong>Note:</strong> This will add the listing to the review queue and notify the
              moderation team. The listing will remain active until reviewed.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleCancel} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || loading}>
            {loading ? 'Submitting...' : 'Mark for Review'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
