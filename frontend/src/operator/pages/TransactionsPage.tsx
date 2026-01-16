import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { operatorAPI, type OperatorTransaction } from "../api";

const KIND_OPTIONS = [
  "BOOKING_CHARGE",
  "REFUND",
  "OWNER_EARNING",
  "OWNER_PAYOUT",
  "PLATFORM_FEE",
  "DAMAGE_DEPOSIT_HOLD",
  "DAMAGE_DEPOSIT_CAPTURE",
  "DAMAGE_DEPOSIT_RELEASE",
  "PROMOTION_CHARGE",
];

export function TransactionsPage() {
  const [transactions, setTransactions] = useState<OperatorTransaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [kind, setKind] = useState<string>("all");
  const [bookingId, setBookingId] = useState<string>("");
  const [userSearch, setUserSearch] = useState<string>("");
  const [createdAfter, setCreatedAfter] = useState<string>("");
  const [createdBefore, setCreatedBefore] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await operatorAPI.financeTransactions({
          kind: kind === "all" ? undefined : kind,
          booking: bookingId || undefined,
          user: userSearch || undefined,
          created_at_after: createdAfter ? new Date(`${createdAfter}T00:00:00`).toISOString() : undefined,
          created_at_before: createdBefore ? new Date(`${createdBefore}T23:59:59`).toISOString() : undefined,
        });
        if (cancelled) return;
        const rows = Array.isArray((data as any)?.results) ? (data as any).results : (data as any);
        setTransactions(Array.isArray(rows) ? rows : []);
      } catch (err) {
        console.error(err);
        if (!cancelled) setError("Unable to load transactions.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [kind, bookingId, userSearch, createdAfter, createdBefore]);

  const displayDate = (value: string) => {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return format(parsed, "yyyy-MM-dd HH:mm");
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="mb-1">Finance Ledger</h1>
          <p className="text-muted-foreground">Track all payment transactions across bookings.</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-2">
            <Label>Kind</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger>
                <SelectValue placeholder="All kinds" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All kinds</SelectItem>
                {KIND_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Booking ID</Label>
            <Input value={bookingId} onChange={(e) => setBookingId(e.target.value)} placeholder="123" />
          </div>
          <div className="space-y-2">
            <Label>User (name or email)</Label>
            <Input
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              placeholder="Search by user name or email"
            />
          </div>
          <div className="space-y-2">
            <Label>Created after</Label>
            <Input type="date" value={createdAfter} onChange={(e) => setCreatedAfter(e.target.value)} />
          </div>
          <div className="space-y-2">
            <Label>Created before</Label>
            <Input type="date" value={createdBefore} onChange={(e) => setCreatedBefore(e.target.value)} />
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : error ? (
        <div className="flex items-center gap-2 text-red-600 text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
      ) : (
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
                    <TableHead>User</TableHead>
                    <TableHead>Booking</TableHead>
                    <TableHead>Kind</TableHead>
                    <TableHead>Amount</TableHead>
                    <TableHead>Stripe Ref</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {transactions.map((tx) => (
                    <TableRow key={tx.id}>
                      <TableCell className="whitespace-nowrap">{displayDate(tx.created_at)}</TableCell>
                      <TableCell>
                        <div className="text-sm font-medium">{tx.user?.name || "Unknown"}</div>
                        <div className="text-xs text-muted-foreground">{tx.user?.email || "—"}</div>
                      </TableCell>
                      <TableCell>{tx.booking_id ?? "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className="uppercase tracking-wide">
                          {tx.kind}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="font-semibold">
                          {tx.amount} {tx.currency?.toUpperCase?.() || "CAD"}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs">{tx.stripe_id || "—"}</TableCell>
                    </TableRow>
                  ))}
                  {!transactions.length && (
                    <TableRow>
                      <TableCell colSpan={6} className="text-center text-muted-foreground">
                        No transactions found for this filter.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
