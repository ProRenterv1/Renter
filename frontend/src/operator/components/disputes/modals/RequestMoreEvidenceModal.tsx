import type React from "react";
import { useEffect, useMemo, useState } from "react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/components/ui/utils";
import type { OperatorDisputeEvidenceRequestPayload } from "@/operator/api";

const TARGET_OPTIONS = [
  { value: "owner", label: "Owner" },
  { value: "renter", label: "Renter" },
  { value: "both", label: "Both" },
] as const;

const TEMPLATE_OPTIONS = [
  {
    value: "missing_photos",
    label: "Missing photos",
    body: "Please upload clear photos of the tool condition (all sides, close-ups of any damage).",
  },
  {
    value: "pickup_clarification",
    label: "Pickup clarification",
    body: "Please share pickup photos that show the tool condition at handoff.",
  },
  {
    value: "return_clarification",
    label: "Return clarification",
    body: "Please upload return photos showing the tool condition at drop-off.",
  },
  {
    value: "damage_detail",
    label: "Damage detail",
    body: "Please provide close-up photos and a short description of the damage.",
  },
  { value: "custom", label: "Custom", body: "" },
] as const;

const DEFAULT_TEMPLATE = TEMPLATE_OPTIONS[0].value;

type RequestMoreEvidenceModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: OperatorDisputeEvidenceRequestPayload) => Promise<boolean>;
};

export function RequestMoreEvidenceModal({
  open,
  onOpenChange,
  onSubmit,
}: RequestMoreEvidenceModalProps) {
  const [target, setTarget] = useState<OperatorDisputeEvidenceRequestPayload["target"]>("both");
  const [template, setTemplate] = useState(DEFAULT_TEMPLATE);
  const [message, setMessage] = useState("");
  const [dueAt, setDueAt] = useState("");
  const [notifyEmail, setNotifyEmail] = useState(true);
  const [notifySms, setNotifySms] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  const templateBody = useMemo(() => {
    return TEMPLATE_OPTIONS.find((option) => option.value === template)?.body ?? "";
  }, [template]);

  useEffect(() => {
    if (!open) return;
    setTarget("both");
    setTemplate(DEFAULT_TEMPLATE);
    setMessage(TEMPLATE_OPTIONS[0].body);
    setDueAt(getDefaultDueAt(24));
    setNotifyEmail(true);
    setNotifySms(false);
    setErrors({});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (template === "custom") {
      setMessage("");
      return;
    }
    setMessage(templateBody);
  }, [templateBody, template, open]);

  const handleSubmit = async () => {
    const validation = validateForm({ target, message, dueAt });
    setErrors(validation.errors);
    if (!validation.valid) return;

    const payload: OperatorDisputeEvidenceRequestPayload = {
      target,
      template_key: template === "custom" ? undefined : template,
      message: message.trim(),
      due_at: validation.dueAtIso,
      notify_email: notifyEmail,
      notify_sms: notifySms,
    };

    setSubmitting(true);
    const ok = await onSubmit(payload);
    setSubmitting(false);
    if (ok) {
      onOpenChange(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Request more evidence</DialogTitle>
          <DialogDescription>
            Send a targeted request for additional evidence and set a due date.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Target</Label>
              <Select
                value={target}
                onValueChange={(value) => {
                  setTarget(value as OperatorDisputeEvidenceRequestPayload["target"]);
                  clearError("target", setErrors);
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select target" />
                </SelectTrigger>
                <SelectContent>
                  {TARGET_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.target ? <ErrorText>{errors.target}</ErrorText> : null}
            </div>
            <div className="space-y-2">
              <Label>Template</Label>
              <Select value={template} onValueChange={setTemplate}>
                <SelectTrigger>
                  <SelectValue placeholder="Select template" />
                </SelectTrigger>
                <SelectContent>
                  {TEMPLATE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Request message</Label>
            <Textarea
              rows={4}
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                clearError("message", setErrors);
              }}
            />
            {errors.message ? <ErrorText>{errors.message}</ErrorText> : null}
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>Due date</Label>
              <Input
                type="datetime-local"
                value={dueAt}
                onChange={(e) => {
                  setDueAt(e.target.value);
                  clearError("dueAt", setErrors);
                }}
              />
              {errors.dueAt ? <ErrorText>{errors.dueAt}</ErrorText> : null}
            </div>
            <div className="space-y-3">
              <Label>Notify via</Label>
              <div className="space-y-2">
                <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <span className="text-sm">Email</span>
                  <Switch checked={notifyEmail} onCheckedChange={setNotifyEmail} />
                </div>
                <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                  <span className="text-sm">SMS</span>
                  <Switch checked={notifySms} onCheckedChange={setNotifySms} />
                </div>
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Sending..." : "Send request"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function validateForm({
  target,
  message,
  dueAt,
}: {
  target: string;
  message: string;
  dueAt: string;
}) {
  const errors: Record<string, string> = {};
  if (!target) errors.target = "Select a target.";
  if (!message.trim()) errors.message = "Enter a request message.";
  if (!dueAt) {
    errors.dueAt = "Select a due date.";
  }

  const dueAtIso = toIsoString(dueAt);
  if (dueAt && !dueAtIso) {
    errors.dueAt = "Enter a valid due date.";
  }

  return { valid: Object.keys(errors).length === 0, errors, dueAtIso: dueAtIso ?? "" };
}

function toIsoString(value: string) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function getDefaultDueAt(hoursAhead: number) {
  const now = new Date();
  now.setHours(now.getHours() + hoursAhead);
  return toInputDateTime(now);
}

function toInputDateTime(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function clearError(key: string, setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>) {
  setErrors((prev) => {
    if (!prev[key]) return prev;
    const next = { ...prev };
    delete next[key];
    return next;
  });
}

function ErrorText({ children }: { children: string }) {
  return <p className={cn("text-xs text-destructive", "mt-1")}>{children}</p>;
}
