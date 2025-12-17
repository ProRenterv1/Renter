import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import { operatorAPI, type OperatorFeatureFlag } from "@/operator/api";
import { useIsOperatorAdmin } from "@/operator/session";
import { RefreshCw, Plus } from "lucide-react";

const FLAG_DESCRIPTIONS: Record<string, string> = {
  BOOKINGS_ENABLED: "Enables bookings flow across the platform.",
};

export function FeatureFlagsPage() {
  const isAdmin = useIsOperatorAdmin();
  const [flags, setFlags] = useState<OperatorFeatureFlag[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const [toggleOpen, setToggleOpen] = useState(false);
  const [toggleReason, setToggleReason] = useState("");
  const [toggleTarget, setToggleTarget] = useState<{ key: string; enabled: boolean } | null>(null);
  const [toggleSubmitting, setToggleSubmitting] = useState(false);

  const [newKey, setNewKey] = useState("");
  const [newEnabled, setNewEnabled] = useState(false);
  const [newReason, setNewReason] = useState("");
  const [creating, setCreating] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await operatorAPI.featureFlags();
      setFlags(data);
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to load feature flags.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    const sorted = [...flags].sort((a, b) => a.key.localeCompare(b.key));
    if (!query) return sorted;
    return sorted.filter((flag) => flag.key.toLowerCase().includes(query));
  }, [flags, search]);

  const openToggle = (flag: OperatorFeatureFlag, enabled: boolean) => {
    setToggleTarget({ key: flag.key, enabled });
    setToggleReason("");
    setToggleOpen(true);
  };

  const closeToggle = () => {
    setToggleOpen(false);
    setToggleTarget(null);
    setToggleReason("");
  };

  const submitToggle = async () => {
    if (!toggleTarget) return;
    const reason = toggleReason.trim();
    if (!reason) return;
    setToggleSubmitting(true);
    try {
      const updated = await operatorAPI.putFeatureFlag({
        key: toggleTarget.key,
        enabled: toggleTarget.enabled,
        reason,
      });
      setFlags((prev) => {
        const next = prev.filter((f) => f.key !== updated.key);
        next.push(updated);
        return next;
      });
      toast.success("Feature flag updated");
      closeToggle();
    } catch (err: any) {
      toast.error(err?.data?.detail || "Unable to update feature flag.");
    } finally {
      setToggleSubmitting(false);
    }
  };

  const submitNew = async () => {
    const key = newKey.trim();
    const reason = newReason.trim();
    if (!key || !reason) return;
    setCreating(true);
    try {
      const updated = await operatorAPI.putFeatureFlag({ key, enabled: newEnabled, reason });
      setFlags((prev) => {
        const next = prev.filter((f) => f.key !== updated.key);
        next.push(updated);
        return next;
      });
      setNewKey("");
      setNewReason("");
      setNewEnabled(false);
      toast.success("Feature flag saved");
    } catch (err: any) {
      toast.error(err?.data?.detail || "Unable to save feature flag.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="mb-1">Feature Flags</h2>
          <p className="text-muted-foreground m-0">
            Toggle platform features on and off. Changes take effect immediately.
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className="w-4 h-4" />
          {loading ? "Refreshing..." : "Refresh"}
        </Button>
      </div>

      {error ? (
        <Card>
          <CardContent className="p-6 text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Flags</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div className="space-y-2">
              <Label htmlFor="flag-search">Search</Label>
              <Input
                id="flag-search"
                placeholder="Filter by key..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="text-sm text-muted-foreground">
              {filtered.length} flag{filtered.length === 1 ? "" : "s"}
            </div>
          </div>

          <div className="space-y-3">
            {filtered.length === 0 ? (
              <div className="rounded-md border border-border p-4 text-sm text-muted-foreground">
                No feature flags found.
              </div>
            ) : null}

            {filtered.map((flag) => {
              const updatedAt = flag.updated_at ? new Date(flag.updated_at) : null;
              const desc = FLAG_DESCRIPTIONS[flag.key] || "";
              return (
                <div
                  key={flag.key}
                  className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <div className="font-semibold">{flag.key}</div>
                      <Badge variant={flag.enabled ? "secondary" : "outline"}>
                        {flag.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </div>
                    {desc ? <div className="mt-1 text-sm text-muted-foreground">{desc}</div> : null}
                    <div className="mt-1 text-xs text-muted-foreground">
                      Updated {updatedAt ? updatedAt.toLocaleString() : flag.updated_at}
                      {flag.updated_by_id ? ` • by #${flag.updated_by_id}` : ""}
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3">
                    <Switch
                      checked={flag.enabled}
                      disabled={!isAdmin}
                      onCheckedChange={(checked) => openToggle(flag, Boolean(checked))}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {!isAdmin ? (
            <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
              Admin access required to edit flags.
            </div>
          ) : null}
        </CardContent>
      </Card>

      {isAdmin ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Add / update flag</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="new-flag-key">Key</Label>
                <Input
                  id="new-flag-key"
                  placeholder="EXAMPLE_FLAG"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label>Enabled</Label>
                <div className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2">
                  <span className="text-sm text-muted-foreground">
                    {newEnabled ? "Enabled" : "Disabled"}
                  </span>
                  <Switch checked={newEnabled} onCheckedChange={(v) => setNewEnabled(Boolean(v))} />
                </div>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="new-flag-reason">Reason</Label>
              <Textarea
                id="new-flag-reason"
                rows={3}
                value={newReason}
                onChange={(e) => setNewReason(e.target.value)}
                placeholder="Required. Why are you changing this flag?"
              />
            </div>

            <div className="flex items-center justify-end">
              <Button onClick={submitNew} disabled={creating || !newKey.trim() || !newReason.trim()}>
                <Plus className="w-4 h-4" />
                {creating ? "Saving..." : "Save flag"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Dialog open={toggleOpen} onOpenChange={closeToggle}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Confirm change</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="rounded-md border border-border bg-muted/40 p-3">
              <div className="text-sm font-semibold">{toggleTarget?.key || "—"}</div>
              <div className="text-sm text-muted-foreground">
                Set to <span className="font-medium">{toggleTarget?.enabled ? "Enabled" : "Disabled"}</span>
              </div>
            </div>

            <div className="space-y-2">
              <Label>Reason</Label>
              <Textarea
                rows={3}
                value={toggleReason}
                onChange={(e) => setToggleReason(e.target.value)}
                placeholder="Required. Why are you making this change?"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeToggle} disabled={toggleSubmitting}>
              Cancel
            </Button>
            <Button onClick={submitToggle} disabled={toggleSubmitting || !toggleReason.trim()}>
              {toggleSubmitting ? "Saving..." : "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

