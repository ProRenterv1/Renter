import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import { operatorAPI, type OperatorEffectiveSetting } from "@/operator/api";
import { useIsOperatorAdmin } from "@/operator/session";
import { EditPlatformSettingModal } from "@/operator/components/modals/EditPlatformSettingModal";
import { formatCurrency } from "@/lib/utils";
import { RefreshCw } from "lucide-react";

type FeeRow = {
  key: string;
  label: string;
  valueType: "int";
  kind: "bps_percent" | "cents";
  helpText?: string;
};

const FEE_ROWS: FeeRow[] = [
  {
    key: "BOOKING_PLATFORM_FEE_BPS",
    label: "Renter service fee (%)",
    valueType: "int",
    kind: "bps_percent",
    helpText: "Stored as integer bps (basis points). Enter percent (e.g. 10 = 10%).",
  },
  {
    key: "BOOKING_OWNER_FEE_BPS",
    label: "Owner fee (%)",
    valueType: "int",
    kind: "bps_percent",
    helpText: "Stored as integer bps (basis points). Enter percent (e.g. 5 = 5%).",
  },
  {
    key: "PROMOTION_PRICE_CENTS",
    label: "Promotion price (cents)",
    valueType: "int",
    kind: "cents",
    helpText: "Integer cents (e.g. 500 = $5.00).",
  },
];

export function FeesPage() {
  const isAdmin = useIsOperatorAdmin();
  const [settings, setSettings] = useState<OperatorEffectiveSetting[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [selectedRow, setSelectedRow] = useState<FeeRow | null>(null);

  const settingsByKey = useMemo(() => {
    const map = new Map<string, OperatorEffectiveSetting>();
    for (const row of settings) map.set(row.key, row);
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

  const selectedSetting = selectedRow ? settingsByKey.get(selectedRow.key) ?? null : null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="mb-1">Fees</h2>
          <p className="text-muted-foreground m-0">
            Adjust booking fee rates and promotion pricing. Changes apply to new calculations only.
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
          <CardTitle>Fees & pricing</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {FEE_ROWS.map((row) => (
            <FeeRowItem
              key={row.key}
              row={row}
              setting={settingsByKey.get(row.key) ?? null}
              canEdit={isAdmin}
              onEdit={() => {
                setSelectedRow(row);
                setEditOpen(true);
              }}
            />
          ))}
        </CardContent>
      </Card>

      {selectedRow ? (
        <EditPlatformSettingModal
          open={editOpen}
          onClose={() => {
            setEditOpen(false);
            setSelectedRow(null);
          }}
          title={`Edit: ${selectedRow.label}`}
          settingKey={selectedRow.key}
          valueType={selectedRow.valueType}
          currentValueJson={selectedSetting?.value_json}
          currentDescription={selectedSetting?.description}
          valueLabel={selectedRow.kind === "bps_percent" ? "Percent" : "Cents"}
          valueHelpText={selectedRow.helpText}
          inputType="number"
          inputStep={selectedRow.kind === "bps_percent" ? "0.01" : "1"}
          formatValueForInput={(valueJson) => {
            if (selectedRow.kind === "bps_percent") return formatBpsToPercentInput(valueJson);
            return formatIntInput(valueJson);
          }}
          parseValueFromInput={(raw) => {
            if (selectedRow.kind === "bps_percent") return parsePercentToBps(raw);
            return parseIntOrThrow(raw);
          }}
          onSubmit={async (payload) => {
            await operatorAPI.putSetting(payload);
            toast.success("Fee setting saved");
            setEditOpen(false);
            setSelectedRow(null);
            await load();
          }}
        />
      ) : null}
    </div>
  );
}

function FeeRowItem({
  row,
  setting,
  canEdit,
  onEdit,
}: {
  row: FeeRow;
  setting: OperatorEffectiveSetting | null;
  canEdit: boolean;
  onEdit: () => void;
}) {
  const isOverridden = setting?.source === "db";
  const valueLabel = setting ? formatFeeValue(row.kind, setting.value_json) : "—";
  const updatedAt = setting?.updated_at ? new Date(setting.updated_at) : null;
  const updatedBy =
    setting?.updated_by_name || (setting?.updated_by_id ? `User #${setting.updated_by_id}` : null);

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <div className="font-semibold">{row.label}</div>
          <Badge variant={isOverridden ? "secondary" : "outline"}>{isOverridden ? "Overridden" : "Default"}</Badge>
        </div>
        <div className="mt-1 text-xs text-muted-foreground font-mono break-all">{row.key}</div>
        <div className="mt-2 text-sm">
          <span className={isOverridden ? "font-medium" : "text-muted-foreground"}>{valueLabel}</span>
        </div>
        {isOverridden ? (
          <div className="mt-1 text-xs text-muted-foreground">
            Updated {updatedAt ? updatedAt.toLocaleString() : setting.updated_at}
            {updatedBy ? ` • by ${updatedBy}` : ""}
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

function parsePercentToBps(raw: string) {
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error("Invalid percent");
  if (value < 0) throw new Error("Percent must be >= 0");
  return Math.round(value * 100);
}

function formatBpsToPercentInput(valueJson: unknown) {
  const bps = coerceInt(valueJson);
  if (bps === null) return "";
  const pct = bps / 100;
  return pct % 1 === 0 ? String(pct) : pct.toFixed(2);
}

function formatIntInput(valueJson: unknown) {
  const value = coerceInt(valueJson);
  return value === null ? "" : String(value);
}

function parseIntOrThrow(raw: string) {
  const parsed = Number.parseInt(raw, 10);
  if (!Number.isFinite(parsed)) throw new Error("Invalid int");
  return parsed;
}

function formatFeeValue(kind: FeeRow["kind"], valueJson: unknown) {
  if (kind === "bps_percent") {
    const bps = coerceInt(valueJson);
    if (bps === null) return "—";
    const pct = bps / 100;
    return `${pct % 1 === 0 ? pct.toFixed(0) : pct.toFixed(2)}% (${bps} bps)`;
  }

  const cents = coerceInt(valueJson);
  if (cents === null) return "—";
  const dollars = cents / 100;
  return `${cents.toLocaleString()} cents (${formatCurrency(dollars, "CAD")})`;
}

function coerceInt(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) return Math.trunc(value);
  if (typeof value === "string") {
    const parsed = Number.parseInt(value, 10);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}
