import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { toast } from "sonner";
import { operatorAPI, type MaintenanceSeverity, type OperatorMaintenanceBanner } from "@/operator/api";
import { useIsOperatorAdmin } from "@/operator/session";
import { RefreshCw, Save } from "lucide-react";

export function MaintenanceModePage() {
  const isAdmin = useIsOperatorAdmin();
  const [banner, setBanner] = useState<OperatorMaintenanceBanner | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await operatorAPI.maintenance();
      setBanner(data);
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to load maintenance banner.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const canEdit = isAdmin;

  const updatedAt = useMemo(() => {
    if (!banner?.updated_at) return null;
    const dt = new Date(banner.updated_at);
    return Number.isNaN(dt.getTime()) ? banner.updated_at : dt.toLocaleString();
  }, [banner?.updated_at]);

  const preview = useMemo(() => {
    const enabled = Boolean(banner?.enabled);
    const severity = (banner?.severity || "info") as MaintenanceSeverity;
    const message = (banner?.message || "").trim();
    return { enabled, severity, message };
  }, [banner]);

  const save = async () => {
    if (!banner) return;
    const trimmedReason = reason.trim();
    if (!trimmedReason) return;
    setSaving(true);
    setError(null);
    try {
      const resp = await operatorAPI.putMaintenance({
        enabled: Boolean(banner.enabled),
        severity: banner.severity,
        message: banner.message || "",
        reason: trimmedReason,
      });
      setBanner(resp);
      setReason("");
      toast.success("Maintenance settings saved");
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to save maintenance banner.");
      toast.error("Unable to save maintenance banner");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="mb-1">Maintenance Mode</h2>
          <p className="text-muted-foreground m-0">
            Display a maintenance banner and optionally disable platform functionality.
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Banner</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2">
              <div>
                <div className="font-medium">Enabled</div>
                <div className="text-xs text-muted-foreground">
                  {banner?.enabled ? "Banner is shown to users" : "Banner is hidden"}
                </div>
              </div>
              <Switch
                checked={Boolean(banner?.enabled)}
                disabled={!canEdit || !banner}
                onCheckedChange={(checked) =>
                  setBanner((prev) => (prev ? { ...prev, enabled: Boolean(checked) } : prev))
                }
              />
            </div>

            <div className="space-y-2">
              <Label>Severity</Label>
              <Select
                value={(banner?.severity as MaintenanceSeverity) || "info"}
                onValueChange={(value) =>
                  setBanner((prev) => (prev ? { ...prev, severity: value as MaintenanceSeverity } : prev))
                }
                disabled={!canEdit || !banner}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select severity" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="info">Info</SelectItem>
                  <SelectItem value="warning">Warning</SelectItem>
                  <SelectItem value="error">Error</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Message</Label>
              <Textarea
                rows={5}
                value={banner?.message || ""}
                disabled={!canEdit || !banner}
                onChange={(e) =>
                  setBanner((prev) => (prev ? { ...prev, message: e.target.value } : prev))
                }
                placeholder="Optional message shown to users"
              />
            </div>

            <div className="space-y-2">
              <Label>Reason</Label>
              <Textarea
                rows={3}
                value={reason}
                disabled={!canEdit}
                onChange={(e) => setReason(e.target.value)}
                placeholder={canEdit ? "Required. Why are you changing maintenance mode?" : "Admin access required to edit."}
              />
            </div>

            <div className="flex items-center justify-between">
              <div className="text-xs text-muted-foreground">
                {updatedAt ? `Last updated: ${updatedAt}` : "Not updated yet"}
                {banner?.updated_by_id ? ` • by #${banner.updated_by_id}` : ""}
              </div>
              <Button onClick={save} disabled={!canEdit || saving || !reason.trim() || !banner}>
                <Save className="w-4 h-4" />
                {saving ? "Saving..." : "Save"}
              </Button>
            </div>

            {!isAdmin ? (
              <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                Admin access required to edit maintenance mode.
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Preview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className={bannerPreviewClasses(preview.severity)}>
              <div className="flex items-center justify-between gap-3">
                <div className="font-semibold">
                  {preview.enabled ? "Maintenance mode is enabled" : "Maintenance mode is disabled"}
                </div>
                <div className="text-xs uppercase tracking-wide opacity-80">{preview.severity}</div>
              </div>
              <div className="mt-2 text-sm">
                {preview.message ? preview.message : <span className="opacity-80">No message</span>}
              </div>
            </div>

            <div className="text-sm text-muted-foreground">
              Tip: keep messages short and actionable. For outages, include an ETA if known.
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function bannerPreviewClasses(severity: MaintenanceSeverity) {
  if (severity === "warning") {
    return "rounded-lg border border-[var(--warning-border)] bg-[var(--warning-bg)] p-4 text-[var(--warning-text)]";
  }
  if (severity === "error") {
    return "rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] p-4 text-[var(--error-text)]";
  }
  return "rounded-lg border border-[var(--info-border)] bg-[var(--info-bg)] p-4 text-[var(--info-text)]";
}

