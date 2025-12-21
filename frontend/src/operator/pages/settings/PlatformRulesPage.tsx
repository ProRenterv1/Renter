import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { operatorAPI, type DbSettingValueType, type OperatorEffectiveSetting } from "@/operator/api";
import { EditPlatformSettingModal } from "@/operator/components/modals/EditPlatformSettingModal";
import { PermissionGate } from "@/operator/components/PermissionGate";
import { OPERATOR_ADMIN_ROLE } from "@/operator/lib/permissions";
import { useIsOperatorAdmin } from "@/operator/session";
import { formatCurrency, parseMoney, pluralize } from "@/lib/utils";
import { RefreshCw } from "lucide-react";

type SettingRow = {
  key: string;
  label: string;
  valueType: DbSettingValueType;
  valueLabel?: string;
  valueHelpText?: string;
  formatValue?: (valueJson: unknown) => string;
};

const PLATFORM_RULE_ROWS: SettingRow[] = [
  {
    key: "UNVERIFIED_MAX_BOOKING_DAYS",
    label: "Unverified max booking days",
    valueType: "int",
    valueLabel: "Days",
    formatValue: (v) => formatIntWithUnit(v, "day"),
  },
  {
    key: "VERIFIED_MAX_BOOKING_DAYS",
    label: "Verified max booking days",
    valueType: "int",
    valueLabel: "Days",
    formatValue: (v) => formatIntWithUnit(v, "day"),
  },
  {
    key: "UNVERIFIED_MAX_DEPOSIT_CAD",
    label: "Unverified max damage deposit (CAD)",
    valueType: "decimal",
    valueLabel: "CAD",
    valueHelpText: "Store as a decimal string (example: 700 or 700.00).",
    formatValue: (v) => formatCurrency(parseMoney(v), "CAD"),
  },
  {
    key: "UNVERIFIED_MAX_REPLACEMENT_CAD",
    label: "Unverified max replacement value (CAD)",
    valueType: "decimal",
    valueLabel: "CAD",
    valueHelpText: "Store as a decimal string (example: 1000 or 1000.00).",
    formatValue: (v) => formatCurrency(parseMoney(v), "CAD"),
  },
];

const DISPUTES_POLICY_ROWS: SettingRow[] = [
  {
    key: "DISPUTE_FILING_WINDOW_HOURS",
    label: "Dispute filing window (hours)",
    valueType: "int",
    valueLabel: "Hours",
    formatValue: (v) => formatIntWithUnit(v, "hour"),
  },
  {
    key: "DISPUTE_REBUTTAL_WINDOW_HOURS",
    label: "Dispute rebuttal window (hours)",
    valueType: "int",
    valueLabel: "Hours",
    formatValue: (v) => formatIntWithUnit(v, "hour"),
  },
  {
    key: "DISPUTE_APPEAL_WINDOW_DAYS",
    label: "Dispute appeal window (days)",
    valueType: "int",
    valueLabel: "Days",
    formatValue: (v) => formatIntWithUnit(v, "day"),
  },
  {
    key: "DISPUTE_ALLOW_LATE_SAFETY_FRAUD",
    label: "Allow late safety/fraud disputes",
    valueType: "bool",
    valueLabel: "Enabled",
    formatValue: (v) => (v === true ? "Enabled" : v === false ? "Disabled" : "—"),
  },
];

export function PlatformRulesPage() {
  const isAdmin = useIsOperatorAdmin();
  const [settings, setSettings] = useState<OperatorEffectiveSetting[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [selectedRow, setSelectedRow] = useState<SettingRow | null>(null);

  const settingsByKey = useMemo(() => {
    const map = new Map<string, OperatorEffectiveSetting>();
    for (const row of settings) {
      map.set(row.key, row);
    }
    return map;
  }, [settings]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await operatorAPI.settingsCurrent();
      setSettings(data);
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to load settings.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleOpenEdit = (row: SettingRow) => {
    setSelectedRow(row);
    setEditOpen(true);
  };

  const handleCloseEdit = () => {
    setEditOpen(false);
    setSelectedRow(null);
  };

  const selectedSetting = selectedRow ? settingsByKey.get(selectedRow.key) ?? null : null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="mb-1">Platform Rules</h2>
          <p className="text-muted-foreground m-0">
            Manage booking limits and dispute policy settings. These values override environment defaults when present.
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
          <CardTitle>Platform rules</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {PLATFORM_RULE_ROWS.map((row) => (
            <SettingRowItem
              key={row.key}
              row={row}
              setting={settingsByKey.get(row.key) ?? null}
              canEdit={isAdmin}
              onEdit={() => handleOpenEdit(row)}
            />
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Disputes policy</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <PermissionGate
            roles={[OPERATOR_ADMIN_ROLE]}
            fallback={
              <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                Admin access required to view and edit disputes policy settings.
              </div>
            }
          >
            {DISPUTES_POLICY_ROWS.map((row) => (
              <SettingRowItem
                key={row.key}
                row={row}
                setting={settingsByKey.get(row.key) ?? null}
                canEdit={isAdmin}
                onEdit={() => handleOpenEdit(row)}
              />
            ))}
          </PermissionGate>
        </CardContent>
      </Card>

      {selectedRow ? (
        <EditPlatformSettingModal
          open={editOpen}
          onClose={handleCloseEdit}
          title={`Edit: ${selectedRow.label}`}
          settingKey={selectedRow.key}
          valueType={selectedRow.valueType}
          currentValueJson={selectedSetting?.value_json}
          currentDescription={selectedSetting?.description}
          valueLabel={selectedRow.valueLabel}
          valueHelpText={selectedRow.valueHelpText}
          onSubmit={async (payload) => {
            await operatorAPI.putSetting(payload);
            toast.success("Setting saved");
            setEditOpen(false);
            setSelectedRow(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

function SettingRowItem({
  row,
  setting,
  canEdit,
  onEdit,
}: {
  row: SettingRow;
  setting: OperatorEffectiveSetting | null;
  canEdit: boolean;
  onEdit: () => void;
}) {
  const isOverridden = setting?.source === "db";
  const value = setting ? row.formatValue?.(setting.value_json) ?? formatRawValue(setting.value_json) : "—";
  const updatedAt = setting?.updated_at ? new Date(setting.updated_at) : null;

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <div className="font-semibold">{row.label}</div>
          <Badge variant={isOverridden ? "secondary" : "outline"}>{isOverridden ? "Overridden" : "Default"}</Badge>
        </div>
        <div className="mt-1 text-xs text-muted-foreground font-mono break-all">{row.key}</div>
        <div className="mt-2 text-sm">
          <span className={isOverridden ? "font-medium" : "text-muted-foreground"}>
            {value}
          </span>
        </div>
        {isOverridden ? (
          <div className="mt-1 text-xs text-muted-foreground">
            Updated {updatedAt ? updatedAt.toLocaleString() : setting.updated_at}
            {setting.updated_by_id ? ` • by #${setting.updated_by_id}` : ""}
            {setting.effective_at ? ` • effective ${new Date(setting.effective_at).toLocaleString()}` : ""}
          </div>
        ) : (
          <div className="mt-1 text-xs text-muted-foreground">Default (env / code)</div>
        )}
      </div>

      <div className="flex shrink-0 items-center justify-end gap-2">
        <Button variant="outline" onClick={onEdit} disabled={!canEdit}>
          {isOverridden ? "Edit" : "Override"}
        </Button>
      </div>
    </div>
  );
}

function formatRawValue(value: unknown) {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value.toLocaleString();
  if (typeof value === "boolean") return value ? "true" : "false";
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function formatIntWithUnit(value: unknown, unit: string) {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string"
        ? Number.parseInt(value, 10)
        : NaN;
  if (!Number.isFinite(parsed)) return "—";
  return pluralize(parsed, unit);
}
