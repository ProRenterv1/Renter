import { useEffect, useMemo, useState } from "react";
import { DollarSign, TrendingUp, Package, Users } from "lucide-react";
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

import {
  listingsAPI,
  paymentsAPI,
  type OwnerPayoutHistoryRow,
  type OwnerPayoutSummary,
} from "@/lib/api";
import { formatCurrency, parseMoney } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Alert, AlertDescription } from "../ui/alert";
import { Skeleton } from "../ui/skeleton";

export function Statistics() {
  const [summary, setSummary] = useState<OwnerPayoutSummary | null>(null);
  const [history, setHistory] = useState<OwnerPayoutHistoryRow[]>([]);
  const [activeListings, setActiveListings] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const completedStatusLabels = useMemo(() => ["completed", "disputed"], []);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [summaryRes, historyRes, listingsRes] = await Promise.all([
          paymentsAPI.ownerPayoutsSummary(),
          paymentsAPI.ownerPayoutsHistory({ limit: 500 }),
          listingsAPI.mine(),
        ]);

        if (cancelled) return;

        setSummary(summaryRes);
        setHistory(historyRes.results ?? []);

        const listingsArray = Array.isArray((listingsRes as any)?.results)
          ? (listingsRes as any).results
          : Array.isArray(listingsRes)
            ? (listingsRes as any)
            : [];

        const activeCount = listingsArray.filter(
          (l: any) => l?.is_active && !(l as any).is_deleted,
        ).length;
        setActiveListings(activeCount);
      } catch (err) {
        if (!cancelled) {
          setError("Unable to load statistics right now.");
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

  const unpaidSinceLastPayout = useMemo(() => {
    if (!summary) return 0;
    const connectBalance = summary.balances.connect_available_earnings;
    if (connectBalance !== undefined && connectBalance !== null) {
      return parseMoney(connectBalance || "0");
    }
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
      .filter(
        (row) =>
          row.kind !== "DAMAGE_DEPOSIT_CAPTURE" &&
          row.kind !== "DAMAGE_DEPOSIT_RELEASE" &&
          row.kind !== "OWNER_PAYOUT",
      )
      .map((row) => {
        const amount = parseMoney(row.amount || "0");
        const signed =
          row.kind === "PROMOTION_CHARGE" && row.stripe_id
            ? 0
            : (row.direction === "debit" ? -1 : 1) * amount;
        return {
          ...row,
          signedAmount: signed,
          createdDate: new Date(row.created_at),
        };
      })
      .sort((a, b) => a.createdDate.getTime() - b.createdDate.getTime());
  }, [history]);

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
              {loading ? <Skeleton className="h-6 w-20" /> : formatCurrency(unpaidSinceLastPayout)}
            </div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Balance currently available in your Stripe Connect account
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
            <CardTitle className="text-sm">Active Listings</CardTitle>
            <Package className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">{loading ? <Skeleton className="h-6 w-10" /> : activeListings}</div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              Currently active
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
