import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { format, subDays } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Calendar as CalendarIcon,
  CheckCircle2,
  Clock,
  Copy,
  CreditCard,
  Package,
  User,
  ShieldX,
  Send,
  Check,
  XCircle,
  CalendarClock,
  Wallet,
} from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "../../components/ui/dialog";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { Label } from "../../components/ui/label";
import { Checkbox } from "../../components/ui/checkbox";
import {
  operatorAPI,
  type OperatorBookingEvent,
  type OperatorListingOwner,
} from "../api";
import { toast } from "sonner";
import type { OperatorBookingDetail as BookingDetailType } from "../api";
import { AdjustBookingDatesModal } from "../components/modals/AdjustBookingDatesModal";
import { cn } from "@/lib/utils";

export function BookingDetail() {
  const { bookingId } = useParams();
  const navigate = useNavigate();
  const [booking, setBooking] = useState<BookingDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState<string>("");
  const [forceCancelOpen, setForceCancelOpen] = useState(false);
  const [forceCompleteOpen, setForceCompleteOpen] = useState(false);
  const [adjustDatesOpen, setAdjustDatesOpen] = useState(false);
  const [resendOpen, setResendOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [forceCancelPayload, setForceCancelPayload] = useState<{ actor: "system" | "owner" | "renter" | "no_show"; reason: string }>({
    actor: "system",
    reason: "",
  });
  const [forceCompleteReason, setForceCompleteReason] = useState("");
  const [adjustDatesReason, setAdjustDatesReason] = useState("");
  const [resendSelections, setResendSelections] = useState<Record<string, boolean>>({});
  const [submittingAction, setSubmittingAction] = useState(false);

  const loadBooking = async () => {
    if (!bookingId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await operatorAPI.bookingDetail(Number(bookingId));
      setBooking(data);
    } catch (err) {
      console.error("Failed to load booking", err);
      setError("Unable to load booking.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadBooking();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);

  useEffect(() => {
    if (!booking?.dispute_window_expires_at) return;
    const calc = () => {
      if (!booking?.dispute_window_expires_at) return;
      const now = Date.now();
      const end = new Date(booking.dispute_window_expires_at).getTime();
      const diff = end - now;
      if (diff <= 0) {
        setTimeRemaining("Expired");
        return;
      }
      const hours = Math.floor(diff / (1000 * 60 * 60));
      const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
      if (hours > 24) {
        const days = Math.floor(hours / 24);
        setTimeRemaining(`${days}d ${hours % 24}h`);
      } else {
        setTimeRemaining(`${hours}h ${minutes}m`);
      }
    };
    calc();
    const handle = setInterval(calc, 60000);
    return () => clearInterval(handle);
  }, [booking?.dispute_window_expires_at]);

  const money = useMemo(() => breakdownFromTotals(booking?.totals), [booking]);
  const lastNotifications = useMemo(() => buildNotificationHistory(booking?.events || []), [booking]);
  const endDateDisplay = useMemo(() => {
    if (!booking?.end_date) return null;
    const end = new Date(`${booking.end_date}T12:00:00Z`);
    if (Number.isNaN(end.getTime())) return booking.end_date;
    return format(subDays(end, 1), "yyyy-MM-dd");
  }, [booking?.end_date]);

  useEffect(() => {
    if (!booking) return;
    setAdjustDatesReason("");
  }, [booking]);

  const handleCopyStripeIds = () => {
    if (!booking) return;
    const text = [
      `Payment Intent: ${booking.charge_payment_intent_id || "—"}`,
      `Deposit Hold: ${booking.deposit_hold_id || "—"}`,
    ].join("\n");
    navigator.clipboard.writeText(text);
    toast.success("Stripe IDs copied to clipboard");
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !booking) {
    return (
      <div className="space-y-6">
        <Button variant="ghost" onClick={() => navigate("/operator/bookings")}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Bookings
        </Button>
        <Card>
          <CardContent className="p-12 text-center">
            <h2 className="mb-2">Booking Not Found</h2>
            <p className="text-muted-foreground">{error || "The requested booking could not be found."}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate("/operator/bookings")}>
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Bookings
      </Button>

      <Card>
        <CardContent className="p-6">
          <div className="flex items-start justify-between flex-wrap gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2 flex-wrap">
                <h1 className="m-0">Booking {booking.id}</h1>
                <Badge variant={statusVariant(booking.status)}>{displayStatus(booking)}</Badge>
                {booking.is_disputed && (
                  <Badge variant="outline" className="border-orange-500 text-orange-700">
                    <AlertCircle className="w-3 h-3 mr-1" />
                    Disputed
                  </Badge>
                )}
              </div>
              <p className="text-sm text-muted-foreground m-0">{booking.listing_title}</p>
            </div>
            {booking.is_overdue && (
              <div className="p-3 rounded-lg bg-destructive/10 border border-destructive/20">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-destructive" />
                  <div>
                    <p className="text-sm font-medium text-destructive m-0">Overdue</p>
                    <p className="text-xs text-destructive/80 m-0">Past return date</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Booking Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <DetailRow icon={<Package className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Listing">
                  <button
                    onClick={() => navigate(`/operator/listings/${booking.listing_id}`)}
                    className="text-primary hover:underline"
                  >
                    {booking.listing_title}
                  </button>
                </DetailRow>

                <DetailRow icon={<User className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Owner">
                  <UserLink user={booking.owner} onClick={() => navigate(`/operator/users/${booking.owner?.id}`)} />
                </DetailRow>

                <DetailRow icon={<User className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Renter">
                  <UserLink user={booking.renter} onClick={() => navigate(`/operator/users/${booking.renter?.id}`)} />
                </DetailRow>

                <DetailRow icon={<CalendarIcon className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Rental Period">
                  <div>
                    {booking.start_date} to {endDateDisplay ?? booking.end_date}
                  </div>
                </DetailRow>
              </div>

              {booking.dispute_window_expires_at && (
                <div className="pt-4 border-t border-border">
                  <div className="flex items-center justify-between p-3 rounded-lg bg-primary/10 border border-primary/20">
                    <div className="flex items-center gap-2">
                      <Clock className="w-5 h-5 text-primary" />
                      <span className="font-medium">Dispute Window</span>
                    </div>
                    <Badge variant="outline" className="border-primary text-primary">
                      Ends in {timeRemaining || "—"}
                    </Badge>
                  </div>
                </div>
              )}

              {booking.is_disputed && booking.disputes?.length > 0 && (
                <div className="pt-4 border-t border-border">
                  <div className="p-4 rounded-lg bg-orange-500/10 border border-orange-500/20 space-y-2">
                    {booking.disputes.map((dispute) => (
                      <div key={dispute.id} className="flex items-start gap-3">
                        <AlertCircle className="w-5 h-5 text-orange-600 mt-0.5 shrink-0" />
                        <div className="flex-1">
                          <p className="font-medium text-orange-900 dark:text-orange-200 m-0 mb-1">
                            Dispute {dispute.id} ({dispute.category})
                          </p>
                          <p className="text-sm text-orange-900/80 dark:text-orange-200/80 m-0 mb-2">
                            Status: {dispute.status}
                          </p>
                          <p className="text-xs text-orange-900/60 dark:text-orange-200/60 m-0">
                            Opened: {dispute.created_at ? new Date(dispute.created_at).toLocaleString() : "—"}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Financial Breakdown</CardTitle>
                <div className="flex items-center gap-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => navigate(`/operator/finance/bookings/${booking.id}`)}
                  >
                    <Wallet className="w-4 h-4 mr-2" />
                    Open Finance
                  </Button>
                  <Button variant="outline" size="sm" onClick={handleCopyStripeIds}>
                    <Copy className="w-4 h-4 mr-2" />
                    Copy Stripe IDs
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <MoneyRow label="Subtotal (Rental)" value={money.subtotal} />
                <MoneyRow label="Renter Service Fee" value={money.renterFee} />
                <MoneyRow label="GST Paid" value={money.gstPaid} />
                <MoneyRow label="Security Deposit (Hold)" value={money.deposit} />
                <div className="pt-3 border-t border-border flex justify-between items-center">
                  <span className="font-medium">Total Charged to Renter</span>
                  <span className="font-medium text-lg">{money.total}</span>
                </div>
              </div>

              <div className="pt-4 border-t border-border space-y-3">
                <MoneyRow label="Owner Fee" value={money.ownerFee} negative />
                <MoneyRow label="Stripe Fee" value={money.stripeFee} negative />
                <MoneyRow label="Platform Profit (before taxes + commissions)" value={money.platformProfitBefore} bold />
                <MoneyRow label="Platform Profit (after GST + Stripe fee)" value={money.platformProfitAfter} bold />
                <MoneyRow label="Owner Payout" value={money.ownerPayout} bold />
              </div>

              <div className="pt-4 border-t border-border space-y-2">
                <StripeField label="Payment Intent" value={booking.charge_payment_intent_id} />
                <StripeField label="Deposit Hold" value={booking.deposit_hold_id} />
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <ActionsSidebar
            booking={booking}
            lastNotifications={lastNotifications}
            onForceCancel={() => {
              setConfirmText("");
              setForceCancelOpen(true);
            }}
            onForceComplete={() => {
              setConfirmText("");
              setForceCompleteOpen(true);
            }}
            onAdjustDates={() => setAdjustDatesOpen(true)}
            onResend={() => setResendOpen(true)}
          />
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {booking.events?.length ? (
                  booking.events.map((event, index) => (
                    <TimelineItem
                      key={event.id}
                      event={event}
                      isLast={index === booking.events.length - 1}
                    />
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">No timeline events yet.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <ForceCancelModal
        open={forceCancelOpen}
        onClose={() => setForceCancelOpen(false)}
        payload={forceCancelPayload}
        confirmText={confirmText}
        setConfirmText={setConfirmText}
        setPayload={setForceCancelPayload}
        onSubmit={async () => {
          if (!booking) return;
          setSubmittingAction(true);
          try {
            await operatorAPI.forceCancelBooking(booking.id, forceCancelPayload);
            toast.success("Booking force-canceled");
            setForceCancelOpen(false);
            loadBooking();
          } catch (err) {
            console.error(err);
            toast.error("Unable to force cancel booking");
          } finally {
            setSubmittingAction(false);
          }
        }}
        disabled={submittingAction}
      />
      <ForceCompleteModal
        open={forceCompleteOpen}
        onClose={() => setForceCompleteOpen(false)}
        reason={forceCompleteReason}
        confirmText={confirmText}
        setConfirmText={setConfirmText}
        setReason={setForceCompleteReason}
        onSubmit={async () => {
          if (!booking) return;
          setSubmittingAction(true);
          try {
            await operatorAPI.forceCompleteBooking(booking.id, { reason: forceCompleteReason || "operator" });
            toast.success("Booking marked complete");
            setForceCompleteOpen(false);
            loadBooking();
          } catch (err) {
            console.error(err);
            toast.error("Unable to force complete booking");
          } finally {
            setSubmittingAction(false);
          }
        }}
        disabled={submittingAction}
      />
      <AdjustBookingDatesModal
        open={adjustDatesOpen}
        onClose={() => {
          setAdjustDatesOpen(false);
          setAdjustDatesReason("");
        }}
        booking={booking}
        reason={adjustDatesReason}
        onReasonChange={setAdjustDatesReason}
        submitting={submittingAction}
        onConfirm={async ({ startDate, endDate, reason }) => {
          if (!booking) return;
          setSubmittingAction(true);
          try {
            const payload = {
              start_date: format(startDate, "yyyy-MM-dd"),
              end_date: format(endDate, "yyyy-MM-dd"),
              reason: reason || "Operator adjustment",
            };
            await operatorAPI.adjustBookingDates(booking.id, payload);
            toast.success("Booking dates adjusted");
            setAdjustDatesOpen(false);
            setAdjustDatesReason("");
            loadBooking();
          } catch (err) {
            console.error(err);
            toast.error("Unable to adjust dates");
          } finally {
            setSubmittingAction(false);
          }
        }}
      />
      <ResendNotificationsModal
        open={resendOpen}
        onClose={() => setResendOpen(false)}
        lastNotifications={lastNotifications}
        booking={booking}
        selections={resendSelections}
        onChangeSelection={(key, value) => setResendSelections((prev) => ({ ...prev, [key]: value }))}
        submitting={submittingAction}
        onSubmit={async () => {
          if (!booking) return;
          const types = Object.entries(resendSelections)
            .filter(([, checked]) => checked)
            .map(([key]) => key);
          if (!types.length) {
            toast("Select at least one notification");
            return;
          }
          setSubmittingAction(true);
          try {
            const resp = await operatorAPI.resendBookingNotifications(booking.id, { types });
            const sent = resp.queued || [];
            const failed = resp.failed || [];
            const sentLabel = sent.map(friendlyNotificationLabel).join(", ") || "none";
            const failedLabel = failed.map(friendlyNotificationLabel).join(", ");
            if (failed.length) {
              toast("Resend finished with issues", { description: `Sent: ${sentLabel} • Failed: ${failedLabel}` });
            } else {
              toast.success(`Sent ${sent.length} notification${sent.length === 1 ? "" : "s"}`);
            }
            setResendSelections({});
            setResendOpen(false);
            loadBooking();
          } catch (err) {
            console.error(err);
            toast.error("Unable to resend notifications");
          } finally {
            setSubmittingAction(false);
          }
        }}
      />
    </div>
  );
}

function DetailRow({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      {icon}
      <div className="flex-1">
        <div className="text-sm text-muted-foreground mb-1">{label}</div>
        <div>{children}</div>
      </div>
    </div>
  );
}

function UserLink({ user, onClick }: { user?: OperatorListingOwner | null; onClick: () => void }) {
  if (!user) return <span className="text-muted-foreground">Unknown</span>;
  return (
    <button onClick={onClick} className="text-primary hover:underline">
      {user.name || user.email || `User ${user.id}`}
    </button>
  );
}

function StripeField({ label, value }: { label: string; value?: string | null }) {
  return (
    <div className="flex items-start gap-2">
      <CreditCard className="w-4 h-4 text-muted-foreground mt-1" />
      <div className="flex-1 min-w-0">
        <p className="text-xs text-muted-foreground m-0 mb-1">{label}</p>
        <p className="text-sm font-mono break-all m-0">{value || "—"}</p>
      </div>
    </div>
  );
}

function MoneyRow({
  label,
  value,
  negative = false,
  bold = false,
}: {
  label: string;
  value: string;
  negative?: boolean;
  bold?: boolean;
}) {
  return (
    <div className="flex justify-between items-center">
      <span className="text-muted-foreground">{label}</span>
      <span className={`${bold ? "font-medium text-lg" : ""} ${negative ? "text-destructive" : ""}`}>{value}</span>
    </div>
  );
}

function TimelineItem({ event, isLast }: { event: OperatorBookingEvent; isLast: boolean }) {
  const icon = timelineIcon(event.type);
  const color = timelineColor(event.type);
  const description = timelineDescription(event);
  const actor = event.actor?.name || event.actor?.email || "";
  const timestamp = event.created_at ? new Date(event.created_at).toLocaleString() : "";
  const failureReason = notificationFailureReason(event);
  const showFailureReason =
    (event.type === "email_failed" || event.type === "sms_failed") && failureReason;
  const failureLabel = event.type === "sms_failed" ? "SMS failed" : "Email failed";

  return (
    <div className="relative">
      {!isLast && <div className="absolute left-2.5 top-8 bottom-0 w-0.5 bg-border" />}
      <div className="flex gap-3">
        <div className="relative">
          <div className={`w-5 h-5 flex items-center justify-center rounded-full bg-background border-2 ${color} border-current`}>
            {icon}
          </div>
        </div>
        <div className="flex-1 pb-4">
          <p className="text-sm font-medium m-0 mb-1">{description}</p>
          {showFailureReason ? (
            <p className="text-xs text-destructive m-0 mb-1">
              {failureLabel}: {failureReason}
            </p>
          ) : null}
          {actor ? <p className="text-xs text-muted-foreground m-0 mb-1">{actor}</p> : null}
          <p className="text-xs text-muted-foreground m-0">{timestamp}</p>
        </div>
      </div>
    </div>
  );
}

function timelineIcon(type: string) {
  switch (type) {
    case "status_change":
    case "booking_completed":
      return <CheckCircle2 className="w-5 h-5" />;
    case "email_sent":
      return <MailIcon />;
    case "email_failed":
    case "sms_failed":
      return <AlertTriangle className="w-5 h-5" />;
    case "sms_sent":
      return <Send className="w-5 h-5" />;
    case "dispute_opened":
      return <AlertCircle className="w-5 h-5" />;
    default:
      return <Clock className="w-5 h-5" />;
  }
}

function timelineColor(type: string) {
  switch (type) {
    case "booking_completed":
      return "text-[var(--success-solid)]";
    case "dispute_opened":
    case "email_failed":
    case "sms_failed":
      return "text-destructive";
    default:
      return "text-primary";
  }
}

function timelineDescription(event: OperatorBookingEvent) {
  const payload = event.payload || {};
  const notificationLabel = notificationContextLabel(payload);
  if (event.type === "status_change" && "from" in payload && "to" in payload) {
    return `Status ${payload.from} → ${payload.to}`;
  }
  if (event.type === "booking_created") {
    return "Booking created";
  }
  if (event.type === "payment_intent") {
    return "Payment intent created";
  }
  if (event.type === "deposit_authorized") {
    return "Deposit authorized";
  }
  if (event.type === "pickup_confirmed") {
    return "Pickup confirmed";
  }
  if (event.type === "renter_returned") {
    return "Renter marked returned";
  }
  if (event.type === "owner_return_confirmed") {
    return "Owner confirmed return";
  }
  if (event.type === "deposit_release_scheduled") {
    return "Deposit release scheduled";
  }
  if (event.type === "deposit_released") {
    return "Deposit released";
  }
  if (event.type === "email_sent") {
    return notificationLabel ? `Email sent: ${notificationLabel}` : "Email sent";
  }
  if (event.type === "email_failed") {
    return notificationLabel ? `Email failed: ${notificationLabel}` : "Email failed";
  }
  if (event.type === "sms_sent") {
    return notificationLabel ? `SMS sent: ${notificationLabel}` : "SMS sent";
  }
  if (event.type === "sms_failed") {
    return notificationLabel ? `SMS failed: ${notificationLabel}` : "SMS failed";
  }
  if (event.type === "dispute_opened") {
    const category = (payload as any).category || "dispute";
    return `Dispute opened (${category})`;
  }
  return event.type;
}

function notificationContextLabel(payload: Record<string, unknown> | null) {
  if (!payload) return "";
  const notificationType = (payload as { notification_type?: unknown }).notification_type;
  if (typeof notificationType === "string" && notificationType.trim()) {
    return friendlyNotificationLabel(notificationType.trim());
  }
  const template = (payload as { template?: unknown }).template;
  if (typeof template === "string" && template.trim()) {
    const raw = template.trim();
    const base = raw.split("/").pop() || raw;
    const withoutExt = base.replace(/\.[^.]+$/, "");
    return withoutExt.replace(/[_-]+/g, " ").replace(/\b\w/g, (match) => match.toUpperCase());
  }
  return "";
}

function notificationFailureReason(event: OperatorBookingEvent) {
  const payload = event.payload || {};
  const error = (payload as { error?: unknown }).error;
  return normalizeNotificationError(error);
}

function normalizeNotificationError(raw: unknown) {
  if (typeof raw !== "string") return "";
  const trimmed = raw.trim();
  if (!trimmed) return "";

  const messageMatch = trimmed.match(/["']message["']\s*:\s*["']([^"']+)["']/);
  if (messageMatch) {
    const message = messageMatch[1]?.trim();
    if (!message) return "";
    const jsonStart = trimmed.indexOf("{");
    if (jsonStart > 0) {
      const prefix = trimmed.slice(0, jsonStart).trim();
      if (prefix) {
        const separator = prefix.endsWith(":") ? " " : ": ";
        return `${prefix}${separator}${message}`;
      }
    }
    return message;
  }

  const jsonStart = trimmed.indexOf("{");
  if (jsonStart >= 0) {
    const prefix = trimmed.slice(0, jsonStart).trim();
    if (prefix) {
      return prefix.replace(/\s*:\s*$/, "");
    }
    return "Unknown error";
  }

  return trimmed;
}

function statusVariant(status: string) {
  const s = status?.toLowerCase?.() || "";
  if (s === "completed") return "secondary";
  if (s === "paid" || s === "confirmed") return "default";
  if (s === "canceled") return "outline";
  return "outline";
}

function displayStatus(booking: BookingDetailType) {
  if (!booking) return "Unknown";
  const status = booking.status?.toLowerCase?.() || "";
  const today = new Date().toISOString().slice(0, 10);
  if (status === "completed") return "Completed";
  if (status === "canceled") return "Canceled";
  if (booking.after_photos_uploaded_at) return "Completed";
  if (booking.returned_by_renter_at || booking.return_confirmed_at) return "Waiting After Photo";
  if (booking.end_date && booking.end_date === today) return "Waiting return";
  if (booking.pickup_confirmed_at) return "In progress";
  if (status === "paid") return "Waiting pick up";
  if (status === "confirmed") return "Approved by owner";
  return booking.status || "Unknown";
}

function breakdownFromTotals(totals?: Record<string, unknown> | null) {
  const asMoney = (value: unknown) => {
    const num = Number(value);
    if (Number.isFinite(num)) return `$${num.toFixed(2)}`;
    const str = typeof value === "string" ? value : "";
    return str ? `$${str}` : "—";
  };
  const toNumber = (value: unknown) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
  };
  const hasTotals = Boolean(totals && Object.keys(totals).length);
  const subtotalValue = toNumber(totals?.rental_subtotal ?? totals?.subtotal);
  const subtotal = asMoney(subtotalValue);
  const renterFeeBaseValue = toNumber(
    totals?.renter_fee_base ?? totals?.renter_fee ?? totals?.service_fee,
  );
  const gstEnabled = Boolean(totals?.gst_enabled);
  const renterFeeGstValue = gstEnabled ? toNumber(totals?.renter_fee_gst) : 0;
  const renterFeeTotalValue = (() => {
    const rawTotal = totals?.renter_fee_total;
    if (rawTotal !== undefined && rawTotal !== null && rawTotal !== "") {
      return toNumber(rawTotal);
    }
    return renterFeeBaseValue + renterFeeGstValue;
  })();
  const renterFee = asMoney(renterFeeBaseValue);
  const deposit = asMoney(totals?.damage_deposit);
  const totalChargeValue = hasTotals ? subtotalValue + renterFeeTotalValue : null;
  const total = totalChargeValue === null ? "—" : asMoney(totalChargeValue);
  const ownerFeeBaseValue = toNumber(
    totals?.owner_fee_base ?? totals?.owner_fee ?? totals?.platform_fee ?? totals?.platform_fee_cents
  );
  const ownerFee = asMoney(ownerFeeBaseValue);
  const ownerPayoutRaw = totals?.owner_payout ?? totals?.owner_payout_amount;
  const ownerPayoutValue =
    ownerPayoutRaw === undefined || ownerPayoutRaw === null || ownerPayoutRaw === ""
      ? null
      : toNumber(ownerPayoutRaw);
  const ownerPayout = ownerPayoutValue === null ? "—" : asMoney(ownerPayoutValue);
  const gstPaidAmount = gstEnabled
    ? toNumber(totals?.renter_fee_gst) + toNumber(totals?.owner_fee_gst)
    : 0;
  const gstPaid = gstEnabled ? `$${gstPaidAmount.toFixed(2)}` : "";
  const stripeFeeOverride = totals?.stripe_fee ?? totals?.stripe_fee_total;
  const stripeFeeCents = totals?.stripe_fee_cents;
  const stripeFeeAmount = hasTotals
    ? (() => {
      if (stripeFeeOverride !== undefined && stripeFeeOverride !== null && stripeFeeOverride !== "") {
        return toNumber(stripeFeeOverride);
      }
      if (stripeFeeCents !== undefined && stripeFeeCents !== null && stripeFeeCents !== "") {
        return toNumber(stripeFeeCents) / 100;
      }
      return null;
    })()
    : null;
  const stripeFee = stripeFeeAmount === null ? "—" : asMoney(stripeFeeAmount);
  const platformProfitBeforeAmount =
    totalChargeValue === null || ownerPayoutValue === null
      ? null
      : totalChargeValue - ownerPayoutValue;
  const platformProfitBefore = platformProfitBeforeAmount === null
    ? "—"
    : asMoney(platformProfitBeforeAmount);
  const platformProfitAfterAmount = (platformProfitBeforeAmount === null || stripeFeeAmount === null)
    ? null
    : platformProfitBeforeAmount - gstPaidAmount - stripeFeeAmount;
  const platformProfitAfter = platformProfitAfterAmount === null
    ? "—"
    : asMoney(platformProfitAfterAmount);
  return {
    subtotal,
    renterFee,
    deposit,
    total,
    ownerFee,
    ownerPayout,
    gstPaid,
    stripeFee,
    platformProfitBefore,
    platformProfitAfter,
  };
}

function buildNotificationHistory(events: OperatorBookingEvent[]) {
  const relevant = events.filter((ev) => ["email_sent", "email_failed", "sms_sent", "sms_failed"].includes(ev.type));
  const latest: Record<
    string,
    { status: "sent" | "failed"; at: string; channel: "email" | "sms"; error?: string }
  > = {};
  relevant.forEach((ev) => {
    const type = (ev.payload?.notification_type as string) || "";
    if (!type) return;
    const isFailed = ev.type.includes("failed");
    const channel = ev.type.startsWith("email") ? "email" : "sms";
    const existing = latest[type];
    if (!existing || new Date(ev.created_at).getTime() > new Date(existing.at).getTime()) {
      const error = isFailed ? normalizeNotificationError(ev.payload?.error) : "";
      latest[type] = { status: isFailed ? "failed" : "sent", at: ev.created_at, channel, error };
    }
  });
  return latest;
}

function MailIcon() {
  return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2Z" />
    <polyline points="22,6 12,13 2,6" />
  </svg>;
}

function ActionsSidebar({
  booking,
  lastNotifications,
  onForceCancel,
  onForceComplete,
  onAdjustDates,
  onResend,
}: {
  booking: BookingDetailType;
  lastNotifications: ReturnType<typeof buildNotificationHistory>;
  onForceCancel: () => void;
  onForceComplete: () => void;
  onAdjustDates: () => void;
  onResend: () => void;
}) {
  const disputedMissingEvidence = booking.disputes?.some((d) => d.status === "intake_missing_evidence");
  return (
    <Card className="border border-border/80 bg-card shadow-sm rounded-2xl">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg">
          <ShieldX className="w-4 h-4 text-primary" />
          Actions
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <Button
          variant="destructive"
          className="w-full justify-start gap-2 rounded-lg px-4 py-3 text-base font-normal"
          onClick={onForceCancel}
        >
          <XCircle className="w-4 h-4" />
          Force Cancel
        </Button>
        <Button
          variant="secondary"
          className="w-full justify-start gap-2 rounded-lg px-4 py-3 text-base font-normal bg-primary text-white hover:bg-sky-600"
          onClick={onForceComplete}
        >
          <Check className="w-4 h-4" />
          Force Complete
        </Button>
        <Button
          variant="outline"
          className="w-full justify-start gap-2 rounded-lg px-4 py-3 text-base font-normal bg-muted/70 hover:bg-muted"
          onClick={onAdjustDates}
        >
          <CalendarClock className="w-4 h-4" />
          Adjust Dates
        </Button>
        <Button
          variant="outline"
          className="w-full justify-start gap-2 rounded-lg px-4 py-3 text-base font-normal bg-muted/70 hover:bg-muted"
          onClick={onResend}
        >
          <MailIcon />
          Resend Notifications
        </Button>
        {disputedMissingEvidence && (
          <div className="rounded-lg border border-amber-400/60 bg-amber-50 text-amber-900 p-3 text-sm">
            Evidence reminder available — include it in Resend modal.
          </div>
        )}
        <div className="text-xs text-muted-foreground pt-3 border-t">
          Last notifications:
          <ul className="list-disc list-inside space-y-1 mt-2">
            {Object.entries(lastNotifications).map(([type, info]) => (
              <li key={type} className="flex flex-wrap items-center gap-2">
                {info.status === "sent" ? (
                  <Check className="w-3 h-3 text-green-600" />
                ) : (
                  <XCircle className="w-3 h-3 text-destructive" />
                )}
                <span className="font-medium">{friendlyNotificationLabel(type)}</span>
                <span className="text-muted-foreground">• {formatDateTime(info.at)}</span>
                {info.status === "failed" && info.error ? (
                  <span className="text-xs text-destructive">
                    {info.channel === "sms" ? "SMS failed" : "Email failed"}: {info.error}
                  </span>
                ) : null}
              </li>
            ))}
            {!Object.keys(lastNotifications).length && <li>No notifications logged yet.</li>}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function ForceCancelModal({
  open,
  onClose,
  payload,
  setPayload,
  onSubmit,
  confirmText,
  setConfirmText,
  disabled,
}: {
  open: boolean;
  onClose: () => void;
  payload: { actor: "system" | "owner" | "renter" | "no_show"; reason: string };
  setPayload: (p: { actor: "system" | "owner" | "renter" | "no_show"; reason: string }) => void;
  onSubmit: () => void;
  confirmText: string;
  setConfirmText: (v: string) => void;
  disabled?: boolean;
}) {
  const ready = confirmText.trim().toUpperCase() === "CONFIRM" && payload.reason.trim().length > 2;
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Force Cancel</DialogTitle>
          <p className="text-sm text-muted-foreground">
            Cancel regardless of participant. Refunds must be handled separately.
          </p>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label>Actor</Label>
            <select
              className="w-full border rounded-md p-2 bg-background"
              value={payload.actor}
              onChange={(e) =>
                setPayload({ ...payload, actor: e.target.value as typeof payload.actor })
              }
            >
              <option value="system">System</option>
              <option value="owner">Owner</option>
              <option value="renter">Renter</option>
              <option value="no_show">No show</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label>Reason</Label>
            <Textarea
              placeholder="Why are you canceling?"
              value={payload.reason}
              onChange={(e) => setPayload({ ...payload, reason: e.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label>Type CONFIRM to proceed</Label>
            <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button disabled={!ready || disabled} variant="destructive" onClick={onSubmit}>
            Force Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ForceCompleteModal({
  open,
  onClose,
  reason,
  setReason,
  confirmText,
  setConfirmText,
  onSubmit,
  disabled,
}: {
  open: boolean;
  onClose: () => void;
  reason: string;
  setReason: (v: string) => void;
  confirmText: string;
  setConfirmText: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}) {
  const ready = reason.trim().length > 2 && confirmText.trim().toUpperCase() === "CONFIRM";
  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Force Complete</DialogTitle>
          <p className="text-sm text-muted-foreground">
            Mark booking completed and trigger deposit release countdown.
          </p>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-2">
            <Label>Reason</Label>
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Type CONFIRM to proceed</Label>
            <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
          <Button disabled={!ready || disabled} onClick={onSubmit}>
            Force Complete
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ResendNotificationsModal({
  open,
  onClose,
  lastNotifications,
  booking,
  selections,
  onChangeSelection,
  onSubmit,
  submitting,
}: {
  open: boolean;
  onClose: () => void;
  lastNotifications: ReturnType<typeof buildNotificationHistory>;
  booking: BookingDetailType | null;
  selections: Record<string, boolean>;
  onChangeSelection: (key: string, value: boolean) => void;
  onSubmit: () => void;
  submitting: boolean;
}) {
  const rows: { key: string; label: string; description: string }[] = [
    { key: "booking_request", label: "Booking Request Email", description: "Owner notification of request" },
    { key: "status_update", label: "Status Update Email", description: "Renter booking status update" },
    { key: "receipt", label: "Payment Receipt", description: "Receipt to renter after payment" },
    { key: "completed", label: "Completed Email", description: "Completion notice to renter" },
  ];
  const hasDisputeReminder = booking?.disputes?.some((d) => d.status === "intake_missing_evidence");
  if (hasDisputeReminder) {
    rows.push({
      key: "dispute_missing_evidence",
      label: "Dispute Evidence Reminder",
      description: "Nudge filer to upload evidence within 24h",
    });
  }

  const renderStatus = (key: string) => {
    const info = lastNotifications[key];
    if (!info) return <span className="text-muted-foreground">Missing</span>;
    return (
      <span className="flex items-center gap-1 text-xs">
        {info.status === "sent" ? <Check className="w-3 h-3 text-green-600" /> : <XCircle className="w-3 h-3 text-destructive" />}
        {info.status === "sent" ? "Sent" : "Failed"} • {formatDateTime(info.at)}
      </span>
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        if (!nextOpen) onClose();
      }}
    >
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Resend Notifications</DialogTitle>
          <p className="text-sm text-muted-foreground">Select which messages to resend.</p>
        </DialogHeader>
        <div className="space-y-3">
          {rows.map((row) => (
            <div key={row.key} className="flex items-start gap-3 p-3 border rounded-lg">
              <Checkbox
                id={`notify-${row.key}`}
                checked={!!selections[row.key]}
                onCheckedChange={(val) => onChangeSelection(row.key, Boolean(val))}
              />
              <div className="flex-1 space-y-1">
                <div className="flex items-center justify-between">
                  <Label htmlFor={`notify-${row.key}`} className="font-medium">
                    {row.label}
                  </Label>
                  {renderStatus(row.key)}
                </div>
                <p className="m-0 text-sm text-muted-foreground">{row.description}</p>
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={onSubmit} disabled={submitting}>
            <Send className="w-4 h-4 mr-2" />
            Resend
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function friendlyNotificationLabel(key: string) {
  switch (key) {
    case "booking_request":
      return "Booking Request";
    case "booking_status_update":
      return "Status Update";
    case "status_update":
      return "Status Update";
    case "booking_expired":
      return "Booking Expired";
    case "receipt":
      return "Payment Receipt";
    case "owner_earnings_statement":
      return "Owner Earnings Statement";
    case "completed":
      return "Booking Completed";
    case "dispute_missing_evidence":
      return "Dispute Evidence Reminder";
    case "dispute_rebuttal_started":
      return "Dispute Rebuttal Started";
    case "dispute_rebuttal_ended":
      return "Dispute Rebuttal Ended";
    case "dispute_rebuttal_reminder":
      return "Dispute Rebuttal Reminder";
    case "deposit_failed_renter":
      return "Deposit Failed (Renter)";
    case "deposit_failed_owner":
      return "Deposit Failed (Owner)";
    default:
      return key;
  }
}

function formatMoney(value: number) {
  if (!Number.isFinite(value)) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

function formatDateTime(value: string | number | Date) {
  try {
    return format(new Date(value), "PP p");
  } catch {
    return String(value);
  }
}
