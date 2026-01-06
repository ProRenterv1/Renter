import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { AlertCircle } from "lucide-react";
import { operatorAPI, type OperatorTransaction, type OperatorUserListItem } from "../api";

export function OwnerEarningsPage() {
  const { ownerId: ownerParam } = useParams();
  const navigate = useNavigate();
  const [ownerId, setOwnerId] = useState<string>(ownerParam || "");
  const [from, setFrom] = useState<string>("");
  const [to, setTo] = useState<string>("");
  const [rows, setRows] = useState<OperatorTransaction[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [owners, setOwners] = useState<OperatorUserListItem[]>([]);
  const [ownersQuery, setOwnersQuery] = useState<string>("");
  const [ownersLoading, setOwnersLoading] = useState(false);
  const [ownersError, setOwnersError] = useState<string | null>(null);

  useEffect(() => {
    setOwnerId(ownerParam || "");
  }, [ownerParam]);

  useEffect(() => {
    let cancelled = false;
    const loadOwners = async () => {
      setOwnersLoading(true);
      setOwnersError(null);
      try {
        const data = await operatorAPI.users({
          name: ownersQuery.trim() || undefined,
          ordering: "newest",
          page_size: 25,
        });
        if (cancelled) return;
        const list = Array.isArray((data as any)?.results) ? (data as any).results : (data as any);
        setOwners(Array.isArray(list) ? list : []);
      } catch (err) {
        console.error(err);
        if (!cancelled) setOwnersError("Unable to load owners.");
      } finally {
        if (!cancelled) setOwnersLoading(false);
      }
    };
    loadOwners();
    return () => {
      cancelled = true;
    };
  }, [ownersQuery]);

  useEffect(() => {
    if (!ownerId.trim()) return;
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await operatorAPI.financeTransactions({
          user: ownerId.trim(),
          created_at_after: from ? new Date(`${from}T00:00:00`).toISOString() : undefined,
          created_at_before: to ? new Date(`${to}T23:59:59`).toISOString() : undefined,
        });
        if (cancelled) return;
        const list = Array.isArray((data as any)?.results) ? (data as any).results : (data as any);
        setRows(Array.isArray(list) ? list : []);
      } catch (err) {
        if (!cancelled) setError("Unable to load owner ledger.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [ownerId, from, to]);

  const totals = useMemo(() => {
    return rows.reduce(
      (acc, tx) => {
        const amount = Number(tx.amount) || 0;
        acc.count += 1;
        acc.sum += amount;
        return acc;
      },
      { count: 0, sum: 0 },
    );
  }, [rows]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-1">Owner Earnings</h1>
        <p className="text-muted-foreground">Ledger view for a specific owner account.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Owners</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="owners-search">Search</Label>
                  <Input
                    id="owners-search"
                    value={ownersQuery}
                    onChange={(e) => setOwnersQuery(e.target.value)}
                    placeholder="Name or email"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="owner-id">Selected Owner ID</Label>
                  <Input
                    id="owner-id"
                    value={ownerId}
                    onChange={(e) => setOwnerId(e.target.value)}
                    placeholder="Pick from list or type an id"
                  />
                </div>
              </div>

              {ownersLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-9 w-full" />
                  <Skeleton className="h-9 w-full" />
                </div>
              ) : ownersError ? (
                <div className="flex items-center gap-2 text-red-600 text-sm">
                  <AlertCircle className="w-4 h-4" />
                  {ownersError}
                </div>
              ) : (
                <div className="overflow-x-auto rounded-md border">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>ID</TableHead>
                        <TableHead>Name</TableHead>
                        <TableHead>Email</TableHead>
                        <TableHead>City</TableHead>
                        <TableHead className="text-right">Action</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {owners.map((owner) => (
                        <TableRow key={owner.id}>
                          <TableCell>{owner.id}</TableCell>
                          <TableCell>{`${owner.first_name || ""} ${owner.last_name || ""}`.trim() || owner.username}</TableCell>
                          <TableCell className="text-xs text-muted-foreground">{owner.email || "—"}</TableCell>
                          <TableCell>{owner.city || "—"}</TableCell>
                          <TableCell className="text-right">
                            <button
                              className="text-primary hover:underline text-sm"
                              onClick={() => navigate(`/operator/finance/owners/${owner.id}`)}
                            >
                              View ledger
                            </button>
                          </TableCell>
                        </TableRow>
                      ))}
                      {!owners.length && (
                        <TableRow>
                          <TableCell colSpan={5} className="text-center text-muted-foreground">
                            No owners found.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Ledger Filters</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="owner-from">From</Label>
                <Input id="owner-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="owner-to">To</Label>
                <Input id="owner-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
              </div>
            </CardContent>
          </Card>

          {loading ? (
            <div className="space-y-3">
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
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Ledger</CardTitle>
                  <div className="text-sm text-muted-foreground">
                    {totals.count} rows · Total {totals.sum.toFixed(2)} CAD
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Date</TableHead>
                        <TableHead>Kind</TableHead>
                        <TableHead>Booking</TableHead>
                        <TableHead>Amount</TableHead>
                        <TableHead>Stripe Ref</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {rows.map((tx) => (
                        <TableRow key={tx.id}>
                          <TableCell className="whitespace-nowrap">
                            {new Date(tx.created_at).toLocaleString()}
                          </TableCell>
                          <TableCell>{tx.kind}</TableCell>
                          <TableCell>{tx.booking_id ?? "—"}</TableCell>
                          <TableCell className="font-semibold">
                            {tx.amount} {tx.currency?.toUpperCase?.() || "CAD"}
                          </TableCell>
                          <TableCell className="text-xs">{tx.stripe_id || "—"}</TableCell>
                        </TableRow>
                      ))}
                      {!rows.length && (
                        <TableRow>
                          <TableCell colSpan={5} className="text-center text-muted-foreground">
                            Select an owner to load ledger entries.
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
      </div>
    </div>
  );
}
