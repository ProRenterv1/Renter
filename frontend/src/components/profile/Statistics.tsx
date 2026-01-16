import { useEffect, useMemo, useState } from "react";
import { DollarSign, TrendingUp, Users, Wallet } from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

import { paymentsAPI, type OwnerFeeInvoice, type OwnerPayoutHistoryRow, type OwnerPayoutSummary } from "@/lib/api";
import { AuthStore } from "@/lib/auth";
import { formatCurrency, parseMoney } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Alert, AlertDescription } from "../ui/alert";
import { Skeleton } from "../ui/skeleton";
import { Button } from "../ui/button";

export function Statistics() {
  const [summary, setSummary] = useState<OwnerPayoutSummary | null>(null);
  const [history, setHistory] = useState<OwnerPayoutHistoryRow[]>([]);
  const [invoices, setInvoices] = useState<OwnerFeeInvoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const completedStatusLabels = useMemo(() => ["completed", "disputed"], []);
  const currentUserId = AuthStore.getCurrentUser()?.id ?? null;

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [summaryRes, historyRes, invoicesRes] = await Promise.all([
          paymentsAPI.ownerPayoutsSummary(),
          paymentsAPI.ownerPayoutsHistory({ limit: 500 }),
          paymentsAPI.listOwnerFeeInvoices(),
        ]);

        if (cancelled) return;

        setSummary(summaryRes);
        setHistory(historyRes.results ?? []);
        setInvoices(invoicesRes.results ?? []);

      } catch (err) {
        if (!cancelled) {
          setError("Unable to load statistics right now.");
          setInvoices([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleInvoiceDownload = async (invoice: OwnerFeeInvoice) => {
    try {
      const res = await paymentsAPI.downloadOwnerFeeInvoice(invoice.id);
      if (res?.url) {
        window.open(res.url, "_blank", "noopener,noreferrer");
      }
    } catch {
      // noop, surface via toast once added
    }
  };

  const formatInvoiceMonth = (invoice: OwnerFeeInvoice) => {
    const dt = new Date(invoice.period_start);
    if (Number.isNaN(dt.getTime())) return invoice.period_start;
    return dt.toLocaleString(undefined, { month: "short", year: "numeric" });
  };

  const totalProfitBalance = useMemo(() => {
    if (!summary) return 0;
    const connectTotal = summary.balances.connect_total_balance;
    if (connectTotal !== undefined && connectTotal !== null) {
      return parseMoney(connectTotal || "0");
    }
    const ledgerTotal = summary.balances.total_balance;
    if (ledgerTotal !== undefined && ledgerTotal !== null) {
      return parseMoney(ledgerTotal || "0");
    }
    return parseMoney(summary.balances.available_earnings || "0");
  }, [summary]);

  const availableFundsBalance = useMemo(() => {
    if (!summary) return 0;
    return parseMoney(summary.balances.available_earnings || "0");
  }, [summary]);

  const totalPayoutsAllTime = useMemo(() => {
    if (summary?.connect?.lifetime_instant_payouts !== undefined) {
      return parseMoney(summary.connect.lifetime_instant_payouts);
    }
    return 0;
  }, [history, summary]);

  const totalCompletedRentals = useMemo(() => {
    const seen = new Set<number>();
    history.forEach((row) => {
      if (
        row.booking_id &&
        row.booking_status &&
        completedStatusLabels.some((label) =>
          row.booking_status?.toLowerCase().includes(label),
        )
      ) {
        seen.add(row.booking_id);
      }
    });
    return seen.size;
  }, [history, completedStatusLabels]);

  const normalizedHistory = useMemo(() => {
    return history
      .map((row) => {
        const amount = Math.abs(parseMoney(row.amount || "0"));
        const isOwnerBooking =
          row.booking_id === null ||
          currentUserId === null ||
          row.booking_owner_id === currentUserId;
        let signed: number | null = null;

        if (row.kind === "OWNER_EARNING") {
          if (!isOwnerBooking) return null;
          signed = row.direction === "debit" ? -amount : amount;
        } else if (row.kind === "DAMAGE_DEPOSIT_CAPTURE") {
          if (!isOwnerBooking) return null;
          signed = amount;
        } else if (row.kind === "REFUND") {
          if (!isOwnerBooking) return null;
          signed = -amount;
        } else if (row.kind === "PROMOTION_CHARGE") {
          const stripeId = (row.stripe_id || "").toLowerCase();
          const paidWithEarnings =
            stripeId.startsWith("tr_") || stripeId.startsWith("earnings:");
          if (!paidWithEarnings) return null;
          signed = -amount;
        }

        if (signed === null) return null;
        return {
          ...row,
          signedAmount: signed,
          createdDate: new Date(row.created_at),
        };
      })
      .filter((row): row is OwnerPayoutHistoryRow & { signedAmount: number; createdDate: Date } =>
        Boolean(row),
      )
      .sort((a, b) => a.createdDate.getTime() - b.createdDate.getTime());
  }, [history, currentUserId]);

  const { monthlyData, rentalData } = useMemo(() => {
    const now = new Date();
    const months: { key: string; label: string }[] = [];

    for (let i = 6; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      const key = `${d.getFullYear()}-${d.getMonth()}`;
      const label = d.toLocaleString(undefined, { month: "short" });
      months.push({ key, label });
    }

    const endBalanceByMonth = new Map<string, number>();
    months.forEach((m) => endBalanceByMonth.set(m.key, 0));

    const bookingCountByMonth = new Map<string, Set<number>>();
    months.forEach((m) => bookingCountByMonth.set(m.key, new Set<number>()));

    let runningBalance = 0;
    let idx = 0;

    for (const m of months) {
      while (idx < normalizedHistory.length) {
        const row = normalizedHistory[idx];
        const dt = row.createdDate;
        const key = `${dt.getFullYear()}-${dt.getMonth()}`;
        if (key !== m.key) break;
        runningBalance += row.signedAmount;

        if (
          row.booking_id &&
          row.booking_status &&
          completedStatusLabels.some((label) =>
            row.booking_status?.toLowerCase().includes(label),
          ) &&
          row.kind === "OWNER_EARNING"
        ) {
          const set = bookingCountByMonth.get(m.key);
          if (set) {
            set.add(row.booking_id);
          }
        }
        idx += 1;
      }
      endBalanceByMonth.set(m.key, Math.round(runningBalance * 100) / 100);
    }

    while (idx < normalizedHistory.length) {
      const row = normalizedHistory[idx];
      const dt = row.createdDate;
      const key = `${dt.getFullYear()}-${dt.getMonth()}`;
      runningBalance += row.signedAmount;
      const set = bookingCountByMonth.get(key);
      if (
        set &&
        row.booking_id &&
        row.booking_status &&
        completedStatusLabels.some((label) =>
          row.booking_status?.toLowerCase().includes(label),
        ) &&
        row.kind === "OWNER_EARNING"
      ) {
        set.add(row.booking_id);
      }
      idx += 1;
    }

    const latestKey = months[months.length - 1]?.key;
    if (latestKey && endBalanceByMonth.has(latestKey)) {
      endBalanceByMonth.set(latestKey, Math.round(runningBalance * 100) / 100);
    }

    return {
      monthlyData: months.map((m) => ({
        month: m.label,
        profit: endBalanceByMonth.get(m.key) ?? 0,
      })),
      rentalData: months.map((m) => ({
        month: m.label,
        count: bookingCountByMonth.get(m.key)?.size || 0,
      })),
    };
  }, [normalizedHistory, completedStatusLabels]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Statistics</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Track your earnings and performance
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Total Profit</CardTitle>
            <DollarSign className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">
              {loading ? <Skeleton className="h-6 w-20" /> : formatCurrency(totalProfitBalance)}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Total balance (available + pending)
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Total Payouts</CardTitle>
            <TrendingUp className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">
              {loading ? <Skeleton className="h-6 w-20" /> : formatCurrency(totalPayoutsAllTime)}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Paid out to your bank account
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Available Funds</CardTitle>
            <Wallet className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">
              {loading ? <Skeleton className="h-6 w-20" /> : formatCurrency(availableFundsBalance)}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Ready to withdraw to your bank account
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Rental Count</CardTitle>
            <Users className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">
              {loading ? <Skeleton className="h-6 w-10" /> : totalCompletedRentals}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Total completed rentals
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Tax invoices</CardTitle>
          <CardDescription>Monthly owner fee invoices (GST on platform fees)</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-20 w-full" />
          ) : invoices.length === 0 ? (
            <p className="text-sm text-muted-foreground">No invoices yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-muted-foreground">
                    <th className="py-2 pr-4">Month</th>
                    <th className="py-2 pr-4">Subtotal</th>
                    <th className="py-2 pr-4">GST</th>
                    <th className="py-2 pr-4">Total</th>
                    <th className="py-2 text-right">Download</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr key={invoice.id} className="border-t border-border">
                      <td className="py-2 pr-4">{formatInvoiceMonth(invoice)}</td>
                      <td className="py-2 pr-4">{formatCurrency(parseMoney(invoice.fee_subtotal))}</td>
                      <td className="py-2 pr-4">{formatCurrency(parseMoney(invoice.gst))}</td>
                      <td className="py-2 pr-4">{formatCurrency(parseMoney(invoice.total))}</td>
                      <td className="py-2 text-right">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => handleInvoiceDownload(invoice)}
                        >
                          Download
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Monthly Profit</CardTitle>
            <CardDescription>Your earnings over the last 7 months</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-[300px] w-full" />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={monthlyData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="month" stroke="#6b7280" fontSize={12} />
                  <YAxis stroke="#6b7280" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "white",
                      border: "1px solid #e5e7eb",
                      borderRadius: "8px",
                    }}
                  />
                  <Bar dataKey="profit" fill="#60B1E0" radius={[8, 8, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Rental Activity</CardTitle>
            <CardDescription>Number of rentals per month</CardDescription>
          </CardHeader>
          <CardContent>
            {loading ? (
              <Skeleton className="h-[300px] w-full" />
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={rentalData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis dataKey="month" stroke="#6b7280" fontSize={12} />
                  <YAxis stroke="#6b7280" fontSize={12} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "white",
                      border: "1px solid #e5e7eb",
                      borderRadius: "8px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    stroke="#5B8CA6"
                    strokeWidth={2}
                    dot={{ fill: "#5B8CA6", r: 4 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
