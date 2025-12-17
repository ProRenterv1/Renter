import { useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertTriangle, ShieldAlert, Wallet } from "lucide-react";
import { operatorAPI, type OperatorBookingFinance, type OperatorBookingDetail } from "../api";
import { RefundModal } from "../components/modals/RefundModal";
import { DepositActionModal } from "../components/modals/DepositActionModal";
import { toast } from "sonner";

export function BookingFinancePage() {
  const { bookingId } = useParams();
  const [finance, setFinance] = useState<OperatorBookingFinance | null>(null);
  const [booking, setBooking] = useState<OperatorBookingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refundOpen, setRefundOpen] = useState(false);
  const [captureOpen, setCaptureOpen] = useState(false);
  const [releaseOpen, setReleaseOpen] = useState(false);

  const load = async () => {
    if (!bookingId) return;
    setLoading(true);
    setError(null);
    try {
      const [financeData, bookingData] = await Promise.all([
        operatorAPI.bookingFinance(Number(bookingId)),
        operatorAPI.bookingDetail(Number(bookingId)),
      ]);
      setFinance(financeData);
      setBooking(bookingData);
    } catch (err) {
      console.error(err);
      setError("Unable to load booking finance.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);

  const handleRefund = async (payload: { amount?: string; reason: string; notify_user: boolean }) => {
    if (!bookingId) return;
    await operatorAPI.refundBooking(Number(bookingId), payload);
    toast.success("Refund submitted");
    await load();
  };

  const handleCapture = async (payload: { amount?: string; reason: string }) => {
    if (!bookingId || !payload.amount) return;
    await operatorAPI.captureDeposit(Number(bookingId), { amount: payload.amount, reason: payload.reason });
    toast.success("Deposit captured");
    await load();
  };

  const handleRelease = async (payload: { reason: string }) => {
    if (!bookingId) return;
    await operatorAPI.releaseDeposit(Number(bookingId), { reason: payload.reason });
    toast.success("Deposit released");
    await load();
  };

  const depositLocked = booking?.deposit_locked;
  const disputeMessage =
    booking?.is_disputed || depositLocked
      ? "Deposit actions may be restricted while disputed."
      : "Deposit release follows dispute window timing.";

  const depositWarning = useMemo(() => {
    if (!booking?.dispute_window_expires_at) return null;
    return new Date(booking.dispute_window_expires_at).toLocaleString();
  }, [booking?.dispute_window_expires_at]);

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-40" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !finance) {
    return <p className="text-red-600 text-sm">{error || "No finance data"}</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="mb-1">Booking Finance</h1>
          <p className="text-muted-foreground">
            Payment and deposit details for booking #{finance.booking_id}
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            className="border border-[#F1C2C6] bg-[#FDEEEF] text-[#8C2A2F] hover:bg-[#F1C2C6] dark:border-[#4A252A] dark:bg-[#241517] dark:text-[#F2B4B9] dark:hover:bg-[#4A252A]"
            onClick={() => setRefundOpen(true)}
          >
            Refund
          </Button>
          <Button
            className="border border-[#F3D2A8] bg-[#FFF3E3] text-[#7F5A23] hover:bg-[#FFE0BC] dark:border-[#3E3426] dark:bg-[#1F1A13] dark:text-[#F2D2A6] dark:hover:bg-[#3E3426]"
            onClick={() => setCaptureOpen(true)}
          >
            Capture deposit
          </Button>
          <Button
            className="border border-[#B9E7D1] bg-[#EAF7F1] text-[#256C46] hover:bg-[#B9E7D1] dark:border-[#1E3B2E] dark:bg-[#0F231B] dark:text-[#AEE8CF] dark:hover:bg-[#1E3B2E]"
            onClick={() => setReleaseOpen(true)}
          >
            Release deposit
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Payment Intent</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <div className="font-mono break-all">{finance.stripe.charge_payment_intent_id || "—"}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Deposit Hold</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <div className="font-mono break-all">{finance.stripe.deposit_hold_id || "—"}</div>
            {depositLocked && (
              <Badge variant="outline" className="mt-2 bg-amber-50 text-amber-700">
                Dispute lock
              </Badge>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Dispute lock status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              {depositLocked ? (
                <ShieldAlert className="w-4 h-4 text-amber-500" />
              ) : (
                <Wallet className="w-4 h-4 text-emerald-500" />
              )}
              <span>{disputeMessage}</span>
            </div>
            {depositWarning && (
              <div className="text-xs text-muted-foreground">
                Deposit held until dispute window expiry: {depositWarning}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Ledger</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Date</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Amount</TableHead>
                  <TableHead>Stripe Ref</TableHead>
                  <TableHead>User</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {finance.ledger.map((tx) => (
                  <TableRow key={tx.id}>
                    <TableCell className="whitespace-nowrap">
                      {new Date(tx.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell>{tx.kind}</TableCell>
                    <TableCell className="font-semibold">
                      {tx.amount} {tx.currency?.toUpperCase?.() || "CAD"}
                    </TableCell>
                    <TableCell className="text-xs">{tx.stripe_id || "—"}</TableCell>
                    <TableCell className="text-sm">
                      <div>{tx.user?.name || "—"}</div>
                      <div className="text-xs text-muted-foreground">{tx.user?.email || ""}</div>
                    </TableCell>
                  </TableRow>
                ))}
                {!finance.ledger.length && (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                      No ledger entries yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800 flex items-start gap-2">
        <AlertTriangle className="w-4 h-4 mt-0.5" />
        <div>
          <div className="font-medium">Deposit actions may be restricted while disputed</div>
          <p className="text-muted-foreground">
            Coordinate with disputes before capturing or releasing deposits.
          </p>
        </div>
      </div>

      <RefundModal open={refundOpen} onClose={() => setRefundOpen(false)} onSubmit={handleRefund} />
      <DepositActionModal
        open={captureOpen}
        mode="capture"
        onClose={() => setCaptureOpen(false)}
        onSubmit={handleCapture}
      />
      <DepositActionModal
        open={releaseOpen}
        mode="release"
        onClose={() => setReleaseOpen(false)}
        onSubmit={handleRelease}
      />
    </div>
  );
}
