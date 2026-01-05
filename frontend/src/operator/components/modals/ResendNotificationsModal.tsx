import { useEffect, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Checkbox } from '../../../components/ui/checkbox';
import { Badge } from '../../../components/ui/badge';
import { Mail, CheckCircle2, XCircle, AlertCircle } from 'lucide-react';

interface NotificationLog {
  id: string;
  name: string;
  lastSent?: string;
  status: 'sent' | 'failed' | 'missing';
}

interface ResendNotificationsModalProps {
  isOpen: boolean;
  onClose: () => void;
  bookingId: string | number;
  notificationLogs: NotificationLog[];
  initialSelected?: string[];
  onResend: (notificationIds: string[]) => Promise<void>;
}

export function ResendNotificationsModal({
  isOpen,
  onClose,
  bookingId,
  notificationLogs,
  initialSelected,
  onResend,
}: ResendNotificationsModalProps) {
  const [selectedNotifications, setSelectedNotifications] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isOpen) return;
    if (!initialSelected || initialSelected.length === 0) {
      setSelectedNotifications([]);
      return;
    }
    const available = new Set(notificationLogs.map((log) => log.id));
    setSelectedNotifications(initialSelected.filter((id) => available.has(id)));
  }, [initialSelected, isOpen, notificationLogs]);

  const handleClose = () => {
    setSelectedNotifications([]);
    setIsSubmitting(false);
    onClose();
  };

  const handleToggle = (notificationId: string) => {
    setSelectedNotifications((prev) =>
      prev.includes(notificationId)
        ? prev.filter((id) => id !== notificationId)
        : [...prev, notificationId]
    );
  };

  const handleSelectAll = () => {
    if (selectedNotifications.length === notificationLogs.length) {
      setSelectedNotifications([]);
    } else {
      setSelectedNotifications(notificationLogs.map((log) => log.id));
    }
  };

  const handleResend = async () => {
    if (selectedNotifications.length === 0) return;

    setIsSubmitting(true);
    try {
      await onResend(selectedNotifications);
      handleClose();
    } catch (error) {
      console.error('Failed to resend notifications:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const getStatusIcon = (status: NotificationLog['status']) => {
    switch (status) {
      case 'sent':
        return <CheckCircle2 className="w-4 h-4 text-[var(--success-solid)]" />;
      case 'failed':
        return <XCircle className="w-4 h-4 text-destructive" />;
      case 'missing':
        return <AlertCircle className="w-4 h-4 text-muted-foreground" />;
    }
  };

  const getStatusBadge = (status: NotificationLog['status']) => {
    switch (status) {
      case 'sent':
        return (
          <Badge variant="outline" className="border-[var(--success-solid)] text-[var(--success-solid)]">
            Sent
          </Badge>
        );
      case 'failed':
        return (
          <Badge variant="outline" className="border-destructive text-destructive">
            Failed
          </Badge>
        );
      case 'missing':
        return <Badge variant="outline">Not Sent</Badge>;
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[550px]">
        <DialogHeader>
          <DialogTitle>Resend Notifications</DialogTitle>
          <DialogDescription>
            Select which notifications to resend for booking {bookingId}. Recipients will receive
            updated emails.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <div className="space-y-3">
            {/* Select All */}
            <div className="flex items-center justify-between pb-3 border-b border-border">
              <div className="flex items-center space-x-2">
                <Checkbox
                  id="select-all"
                  checked={
                    selectedNotifications.length === notificationLogs.length &&
                    notificationLogs.length > 0
                  }
                  onCheckedChange={handleSelectAll}
                />
                <label htmlFor="select-all" className="text-sm font-medium cursor-pointer">
                  Select All ({notificationLogs.length})
                </label>
              </div>
            </div>

            {/* Notification List */}
            <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2">
              {notificationLogs.map((log) => (
                <div
                  key={log.id}
                  className="flex items-start gap-3 p-3 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                >
                  <Checkbox
                    id={log.id}
                    checked={selectedNotifications.includes(log.id)}
                    onCheckedChange={() => handleToggle(log.id)}
                    className="mt-0.5"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Mail className="w-4 h-4 text-muted-foreground shrink-0" />
                      <label htmlFor={log.id} className="text-sm font-medium cursor-pointer">
                        {log.name}
                      </label>
                    </div>
                    <div className="flex items-center gap-2 flex-wrap">
                      {getStatusBadge(log.status)}
                      {log.lastSent && (
                        <span className="text-xs text-muted-foreground">
                          Last sent: {log.lastSent}
                        </span>
                      )}
                      {!log.lastSent && (
                        <span className="text-xs text-muted-foreground">Never sent</span>
                      )}
                    </div>
                  </div>
                  {getStatusIcon(log.status)}
                </div>
              ))}
            </div>
          </div>

          {selectedNotifications.length > 0 && (
            <div className="mt-4 p-3 rounded-lg bg-primary/10 border border-primary/20">
              <p className="text-sm m-0">
                <strong>{selectedNotifications.length}</strong> notification
                {selectedNotifications.length > 1 ? 's' : ''} will be resent to the relevant parties
                (owner, renter, or both).
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose} disabled={isSubmitting}>
            Cancel
          </Button>
          <Button
            onClick={handleResend}
            disabled={selectedNotifications.length === 0 || isSubmitting}
          >
            {isSubmitting ? 'Sending...' : `Resend ${selectedNotifications.length || ''} Notification${selectedNotifications.length !== 1 ? 's' : ''}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
