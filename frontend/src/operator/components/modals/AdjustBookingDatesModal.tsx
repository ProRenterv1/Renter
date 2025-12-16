import { useEffect, useMemo, useState } from "react";
import { addDays, differenceInCalendarDays, format, parse, subDays } from "date-fns";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../../components/ui/dialog";
import { Button } from "../../../components/ui/button";
import { Label } from "../../../components/ui/label";
import { Calendar } from "../../../components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "../../../components/ui/popover";
import { Textarea } from "../../../components/ui/textarea";
import { CalendarIcon, AlertTriangle } from "lucide-react";
import type { OperatorBookingDetail as BookingDetailType } from "../../api";

const DATE_ONLY_REGEX = /^\d{4}-\d{2}-\d{2}$/;

// Parse booking dates without shifting a pure YYYY-MM-DD string by timezone.
function parseBookingDate(value?: string | null) {
  if (!value) return undefined;
  if (DATE_ONLY_REGEX.test(value)) {
    const parsed = parse(value, "yyyy-MM-dd", new Date());
    return Number.isNaN(parsed.getTime()) ? undefined : parsed;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
}

interface AdjustBookingDatesModalProps {
  open: boolean;
  onClose: () => void;
  booking: BookingDetailType | null;
  reason: string;
  onReasonChange: (value: string) => void;
  submitting?: boolean;
  onConfirm: (payload: { startDate: Date; endDate: Date; reason: string }) => void;
}

export function AdjustBookingDatesModal({
  open,
  onClose,
  booking,
  reason,
  onReasonChange,
  submitting = false,
  onConfirm,
}: AdjustBookingDatesModalProps) {
  const currentStartDate = useMemo(
    () => parseBookingDate(booking?.start_date),
    [booking?.start_date],
  );
  const currentEndDate = useMemo(
    () => {
      const parsed = parseBookingDate(booking?.end_date);
      return parsed ? subDays(parsed, 1) : undefined; // DB stores end date as last day + 1; show actual last day
    },
    [booking?.end_date],
  );

  const [startDate, setStartDate] = useState<Date | undefined>(currentStartDate);
  const [endDate, setEndDate] = useState<Date | undefined>(currentEndDate);

  useEffect(() => {
    if (!open) return;
    setStartDate(currentStartDate);
    setEndDate(currentEndDate);
  }, [open, currentStartDate, currentEndDate]);

  const asNumber = (value: unknown) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  };

  const computeDuration = (start?: Date, end?: Date) => {
    if (!start || !end || Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return 0;
    if (end < start) return 0;
    return Math.max(1, differenceInCalendarDays(end, start) + 1);
  };

  const durationCurrent = computeDuration(currentStartDate, currentEndDate);
  const currentSubtotal = asNumber((booking?.totals as any)?.rental_subtotal ?? (booking?.totals as any)?.subtotal);
  const currentServiceFee = asNumber((booking?.totals as any)?.renter_fee);
  const currentDeposit = asNumber((booking?.totals as any)?.damage_deposit);

  const dailyRate = durationCurrent ? currentSubtotal / durationCurrent : 0;
  const dailyFee = durationCurrent ? currentServiceFee / durationCurrent : 0;

  const calculateDetails = (start?: Date, end?: Date) => {
    const duration = computeDuration(start, end);
    if (!duration) {
      return { days: 0, subtotal: 0, serviceFee: 0, total: currentDeposit };
    }
    const subtotal = Math.round(dailyRate * duration * 100) / 100;
    const serviceFee = Math.round(dailyFee * duration * 100) / 100;
    const total = Math.round((subtotal + serviceFee + currentDeposit) * 100) / 100;
    return { days: duration, subtotal, serviceFee, total };
  };

  const currentDetails = calculateDetails(currentStartDate, currentEndDate);
  const newDetails = calculateDetails(startDate, endDate);

  const hasChanges =
    !!startDate &&
    !!endDate &&
    (startDate.toDateString() !== currentStartDate?.toDateString() ||
      endDate.toDateString() !== currentEndDate?.toDateString());

  const isValid = !!(startDate && endDate && endDate >= startDate);

  const delta = Math.round((newDetails.total - currentDetails.total) * 100) / 100;
  const deltaLabel =
    delta === 0 ? "No change" : delta > 0 ? `Charge ${formatCurrency(delta)}` : `Refund ${formatCurrency(Math.abs(delta))}`;

  const handleClose = () => {
    setStartDate(currentStartDate);
    setEndDate(currentEndDate);
    onReasonChange("");
    onClose();
  };

  const handleConfirm = () => {
    if (!startDate || !endDate || !isValid) return;
    // API expects end date as last day + 1
    onConfirm({ startDate, endDate: addDays(endDate, 1), reason: reason.trim() });
  };

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => (nextOpen ? undefined : handleClose())}>
      <DialogContent className="sm:max-w-[600px]">
        <DialogHeader>
          <DialogTitle>Adjust Booking Dates</DialogTitle>
          <DialogDescription>
            {`Modify the rental period${booking?.id ? ` for booking BK-${booking.id}` : ""}. This will recalculate all charges and update the booking.`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <DateInput label="Start Date" date={startDate} onSelect={setStartDate} />
            <DateInput label="End Date" date={endDate} onSelect={setEndDate} />
          </div>

          <div className="space-y-2">
            <Label>Reason</Label>
            <Textarea
              placeholder="Short note for audit trail"
              value={reason}
              onChange={(e) => onReasonChange(e.target.value)}
              rows={3}
            />
          </div>

          {hasChanges && (
            <div className="p-3 rounded-lg bg-orange-500/10 border border-orange-500/20">
              <div className="flex gap-2">
                <AlertTriangle className="w-5 h-5 text-orange-600 shrink-0 mt-0.5" />
                <div className="text-sm">
                  <p className="font-medium text-orange-900 dark:text-orange-200 m-0 mb-1">Important</p>
                  <ul className="text-orange-900/80 dark:text-orange-200/80 ml-4 space-y-1">
                    <li>This will trigger a payment adjustment (charge or refund)</li>
                    <li>Check for calendar conflicts before confirming</li>
                    <li>Both owner and renter will be notified</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          <div className="rounded-lg border border-border overflow-hidden">
            <div className="bg-muted/50 px-4 py-2 border-b border-border">
              <h4 className="text-sm font-medium m-0">Recalculated Totals</h4>
            </div>
            <div className="p-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <TotalsColumn
                  title="Current"
                  accentClass="text-muted-foreground"
                  details={currentDetails}
                  highlightChanges={false}
                />
                <TotalsColumn
                  title="New"
                  accentClass="text-primary"
                  details={newDetails}
                  highlightChanges={true}
                  compareTo={currentDetails}
                />
              </div>

              {hasChanges && isValid && (
                <div className="mt-4 pt-4 border-t border-border">
                  <div className="flex justify-between items-center">
                    <span className="text-sm font-medium">Adjustment Required:</span>
                    <span
                      className={`text-sm font-medium ${
                        delta > 0 ? "text-destructive" : delta < 0 ? "text-[var(--success-solid)]" : "text-muted-foreground"
                      }`}
                    >
                      {delta > 0 ? "+" : ""}
                      {formatCurrency(delta)}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1 m-0">
                    {delta > 0 ? "Additional charge will be processed" : delta < 0 ? "Refund will be processed" : "No payment change"}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={handleClose}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!isValid || !hasChanges || submitting || !booking}
          >
            Confirm Adjustment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DateInput({
  label,
  date,
  onSelect,
}: {
  label: string;
  date: Date | undefined;
  onSelect: (date: Date | undefined) => void;
}) {
  const [open, setOpen] = useState(false);

  const formatDate = (value: Date) => format(value, "PP");

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className="w-full justify-start text-left font-normal inline-flex items-center gap-2 rounded-md border border-input bg-white px-3 py-2.5 text-sm text-foreground shadow-sm hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
            aria-expanded={open}
          >
            <CalendarIcon className="mr-1.5 h-4 w-4 text-muted-foreground" />
            <span className="truncate">{date ? formatDate(date) : "Pick a date"}</span>
          </button>
        </PopoverTrigger>
        <PopoverContent className="z-[9999] w-auto p-0" align="start" sideOffset={4}>
          <Calendar
            mode="single"
            selected={date}
            onSelect={(nextDate) => {
              onSelect(nextDate);
              setOpen(false);
            }}
            initialFocus
          />
        </PopoverContent>
      </Popover>
    </div>
  );
}

function TotalsColumn({
  title,
  accentClass,
  details,
  highlightChanges,
  compareTo,
}: {
  title: string;
  accentClass: string;
  details: { days: number; subtotal: number; serviceFee: number; total: number };
  highlightChanges?: boolean;
  compareTo?: { days: number; subtotal: number; serviceFee: number; total: number };
}) {
  return (
    <div className="space-y-2">
      <p className={`text-xs font-medium uppercase tracking-wide m-0 ${accentClass}`}>{title}</p>
      <div className="space-y-1.5 text-sm">
        <PreviewRow
          label="Duration:"
          value={`${details.days || "—"} day${details.days === 1 ? "" : "s"}`}
          highlight={highlightChanges && compareTo ? details.days !== compareTo.days : false}
        />
        <PreviewRow
          label="Subtotal:"
          value={formatCurrency(details.subtotal)}
          highlight={highlightChanges && compareTo ? details.subtotal !== compareTo.subtotal : false}
        />
        <PreviewRow
          label="Service Fee:"
          value={formatCurrency(details.serviceFee)}
          highlight={highlightChanges && compareTo ? details.serviceFee !== compareTo.serviceFee : false}
        />
        <PreviewRow
          label="Total:"
          value={formatCurrency(details.total)}
          bold
          highlight={highlightChanges && compareTo ? details.total !== compareTo.total : false}
        />
      </div>
    </div>
  );
}

function PreviewRow({
  label,
  value,
  highlight,
  bold,
}: {
  label: string;
  value: string;
  highlight?: boolean;
  bold?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-muted-foreground">{label}</span>
      <span className={`${bold ? "font-semibold" : ""} ${highlight ? "text-primary" : ""}`}>{value}</span>
    </div>
  );
}

function formatCurrency(value: number) {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}
