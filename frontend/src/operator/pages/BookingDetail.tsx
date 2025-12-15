import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Calendar,
  CheckCircle2,
  Clock,
  Copy,
  CreditCard,
  DollarSign,
  Package,
  User,
} from "lucide-react";
import { Skeleton } from "../../components/ui/skeleton";
import {
  operatorAPI,
  type OperatorBookingDetail,
  type OperatorBookingEvent,
  type OperatorListingOwner,
} from "../api";
import { toast } from "sonner";
import type { OperatorBookingDetail as BookingDetailType } from "../api";

export function BookingDetail() {
  const { bookingId } = useParams();
  const navigate = useNavigate();
  const [booking, setBooking] = useState<OperatorBookingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRemaining, setTimeRemaining] = useState<string>("");

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

                <DetailRow icon={<Calendar className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Rental Period">
                  <div>
                    {booking.start_date} to {booking.end_date}
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
                <Button variant="outline" size="sm" onClick={handleCopyStripeIds}>
                  <Copy className="w-4 h-4 mr-2" />
                  Copy Stripe IDs
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-3">
                <MoneyRow label="Subtotal (Rental)" value={money.subtotal} />
                <MoneyRow label="Renter Service Fee" value={money.renterFee} />
                <MoneyRow label="Security Deposit (Hold)" value={money.deposit} />
                <div className="pt-3 border-t border-border flex justify-between items-center">
                  <span className="font-medium">Total Charged to Renter</span>
                  <span className="font-medium text-lg">{money.total}</span>
                </div>
              </div>

              <div className="pt-4 border-t border-border space-y-3">
                <MoneyRow label="Platform Fee" value={money.platformFee} negative />
                <MoneyRow label="Owner Payout" value={money.ownerPayout} bold />
              </div>

              <div className="pt-4 border-t border-border space-y-2">
                <StripeField label="Payment Intent" value={booking.charge_payment_intent_id} />
                <StripeField label="Deposit Hold" value={booking.deposit_hold_id} />
              </div>
            </CardContent>
          </Card>
        </div>

        <div>
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
      return <AlertTriangle className="w-5 h-5" />;
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
      return "text-destructive";
    default:
      return "text-primary";
  }
}

function timelineDescription(event: OperatorBookingEvent) {
  const payload = event.payload || {};
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
  if (event.type === "email_sent" && "template" in payload) {
    return `Email sent: ${payload.template}`;
  }
  if (event.type === "email_failed") {
    return "Email failed";
  }
  if (event.type === "dispute_opened") {
    const category = (payload as any).category || "dispute";
    return `Dispute opened (${category})`;
  }
  return event.type;
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
  const today = new Date().toISOString().slice(0, 10);
  if (booking.status?.toLowerCase() === "canceled") return "Canceled";
  if (booking.after_photos_uploaded_at) return "Completed";
  if (booking.returned_by_renter_at || booking.return_confirmed_at) return "Waiting After Photo";
  if (booking.end_date && booking.end_date === today) return "Waiting return";
  if (booking.pickup_confirmed_at) return "In progress";
  if (booking.status?.toLowerCase() === "paid") return "Waiting pick up";
  return booking.status || "Unknown";
}

function breakdownFromTotals(totals?: Record<string, unknown> | null) {
  const asMoney = (value: unknown) => {
    const num = Number(value);
    if (Number.isFinite(num)) return `$${num.toFixed(2)}`;
    const str = typeof value === "string" ? value : "";
    return str ? `$${str}` : "—";
  };
  const subtotal = asMoney(totals?.rental_subtotal ?? totals?.subtotal);
  const renterFee = asMoney(totals?.renter_fee);
  const deposit = asMoney(totals?.damage_deposit);
  const total = asMoney(totals?.total_charge ?? totals?.total);
  const platformFee = asMoney(totals?.owner_fee ?? totals?.platform_fee ?? totals?.platform_fee_cents);
  const ownerPayout = asMoney(totals?.owner_payout ?? totals?.owner_payout_amount);
  return { subtotal, renterFee, deposit, total, platformFee, ownerPayout };
}

function MailIcon() {
  return <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2Z" />
    <polyline points="22,6 12,13 2,6" />
  </svg>;
}
