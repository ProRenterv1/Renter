import { useEffect, useMemo, useState } from "react";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import type { DbSettingValueType } from "@/operator/api";

type EditPlatformSettingModalProps = {
  open: boolean;
  onClose: () => void;
  title?: string;
  settingKey: string;
  valueType: DbSettingValueType;
  currentValueJson?: unknown;
  currentDescription?: string;
  valueLabel?: string;
  valueHelpText?: string;
  inputType?: "text" | "number";
  inputStep?: string;
  formatValueForInput?: (valueJson: unknown) => string;
  parseValueFromInput?: (input: string) => unknown;
  onSubmit: (payload: {
    key: string;
    value_type: DbSettingValueType;
    value: unknown;
    description?: string;
    effective_at?: string | null;
    reason: string;
  }) => Promise<void>;
};

function _stringifyJson(value: unknown) {
  if (value === undefined) return "";
  if (value === null) return "null";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function EditPlatformSettingModal({
  open,
  onClose,
  title,
  settingKey,
  valueType,
  currentValueJson,
  currentDescription,
  valueLabel,
  valueHelpText,
  inputType,
  inputStep,
  formatValueForInput,
  parseValueFromInput,
  onSubmit,
}: EditPlatformSettingModalProps) {
  const initialDescription = currentDescription || "";
  const initialValueJson = currentValueJson;

  const [reason, setReason] = useState("");
  const [description, setDescription] = useState(initialDescription);
  const [effectiveAtLocal, setEffectiveAtLocal] = useState("");
  const [boolValue, setBoolValue] = useState(false);
  const [textValue, setTextValue] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setReason("");
    setDescription(initialDescription);
    setEffectiveAtLocal("");
    setError(null);
    if (valueType === "bool") {
      setBoolValue(typeIsBool(initialValueJson) ? initialValueJson : false);
      setTextValue("");
      return;
    }
    const formatted =
      typeof formatValueForInput === "function"
        ? formatValueForInput(initialValueJson)
        : defaultFormatValue(valueType, initialValueJson);
    setTextValue(formatted);
    setBoolValue(false);
  }, [open, initialDescription, valueType, initialValueJson, formatValueForInput]);

  const parsedValue = useMemo(() => {
    if (valueType === "bool") return { ok: true as const, value: boolValue };

    const raw = textValue;
    try {
      if (parseValueFromInput) {
        return { ok: true as const, value: parseValueFromInput(raw) };
      }

      if (valueType === "int") {
        const parsed = Number.parseInt(raw, 10);
        if (!Number.isFinite(parsed)) return { ok: false as const, value: null };
        return { ok: true as const, value: parsed };
      }

      if (valueType === "decimal" || valueType === "str") {
        const trimmed = raw.trim();
        if (!trimmed) return { ok: false as const, value: null };
        return { ok: true as const, value: trimmed };
      }

      if (valueType === "json") {
        const trimmed = raw.trim();
        if (!trimmed) return { ok: false as const, value: null };
        return { ok: true as const, value: JSON.parse(trimmed) };
      }
    } catch {
      return { ok: false as const, value: null };
    }

    return { ok: false as const, value: null };
  }, [valueType, boolValue, textValue, parseValueFromInput]);

  const effectiveAtIso = useMemo(() => {
    const trimmed = effectiveAtLocal.trim();
    if (!trimmed) return null;
    const dt = new Date(trimmed);
    if (Number.isNaN(dt.getTime())) return null;
    return dt.toISOString();
  }, [effectiveAtLocal]);

  const canSubmit = useMemo(() => {
    if (!reason.trim()) return false;
    if (!parsedValue.ok) return false;
    if (effectiveAtLocal.trim() && !effectiveAtIso) return false;
    return true;
  }, [reason, parsedValue, effectiveAtLocal, effectiveAtIso]);

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      await onSubmit({
        key: settingKey,
        value_type: valueType,
        value: parsedValue.value,
        description: description.trim(),
        effective_at: effectiveAtIso,
        reason: reason.trim(),
      });
      onClose();
    } catch (err: any) {
      setError(err?.data?.detail || "Unable to save setting.");
    } finally {
      setSubmitting(false);
    }
  };

  const valueFieldLabel = valueLabel || "Value";

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{title || "Edit setting"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1">
            <Label>Key</Label>
            <div className="rounded-md border border-border bg-muted/40 px-3 py-2 font-mono text-sm">
              {settingKey}
            </div>
          </div>

          <div className="space-y-2">
            <Label>{valueFieldLabel}</Label>
            {valueType === "bool" ? (
              <div className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2">
                <div className="text-sm text-muted-foreground">
                  {boolValue ? "Enabled" : "Disabled"}
                </div>
                <Switch checked={boolValue} onCheckedChange={setBoolValue} />
              </div>
            ) : valueType === "json" ? (
              <Textarea
                rows={7}
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                placeholder='{"example": true}'
                className="font-mono text-sm"
              />
            ) : (
              <Input
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                type={inputType || (valueType === "int" ? "number" : "text")}
                step={inputStep || (valueType === "int" ? "1" : undefined)}
              />
            )}
            {valueHelpText ? <p className="text-xs text-muted-foreground m-0">{valueHelpText}</p> : null}
            {!parsedValue.ok ? (
              <p className="text-xs text-destructive m-0">Invalid value for type {valueType}.</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label>Description (optional)</Label>
            <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What does this setting control?" />
          </div>

          <div className="space-y-2">
            <Label>Effective at (optional)</Label>
            <Input
              type="datetime-local"
              value={effectiveAtLocal}
              onChange={(e) => setEffectiveAtLocal(e.target.value)}
            />
            <p className="text-xs text-muted-foreground m-0">
              Leave blank to apply immediately. Scheduled changes won&apos;t show in the “effective settings” list until they take effect.
            </p>
            {effectiveAtLocal.trim() && !effectiveAtIso ? (
              <p className="text-xs text-destructive m-0">Invalid date/time.</p>
            ) : null}
          </div>

          <div className="space-y-2">
            <Label>Reason</Label>
            <Textarea
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Required. Why are you making this change?"
            />
          </div>

          {error ? <p className="text-sm text-destructive m-0">{error}</p> : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
            {submitting ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function typeIsBool(value: unknown): value is boolean {
  return typeof value === "boolean";
}

function defaultFormatValue(valueType: DbSettingValueType, value: unknown) {
  if (valueType === "json") return _stringifyJson(value ?? {});
  if (valueType === "decimal") return typeof value === "string" ? value : value != null ? String(value) : "";
  if (valueType === "str") return typeof value === "string" ? value : value != null ? String(value) : "";
  if (valueType === "int") {
    if (typeof value === "number" && Number.isFinite(value)) return String(Math.trunc(value));
    if (typeof value === "string") return value;
    return "";
  }
  return "";
}
