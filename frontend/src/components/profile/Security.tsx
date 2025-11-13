import { FormEvent, useState } from "react";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { Switch } from "../ui/switch";
import { Separator } from "../ui/separator";
import { Alert, AlertDescription } from "../ui/alert";
import { authAPI, type JsonError } from "@/lib/api";

type ChangePasswordForm = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};

type AlertState = { type: "success" | "error"; detail?: string } | null;

const fallbackErrorMessage = "Error occurred while updating.";

const initialForm: ChangePasswordForm = {
  current_password: "",
  new_password: "",
  confirm_password: "",
};

const passwordRequirements = [
  {
    id: "length",
    label: "At least 8 characters",
    test: (value: string) => value.length >= 8,
  },
  {
    id: "uppercase",
    label: "One uppercase letter",
    test: (value: string) => /[A-Z]/.test(value),
  },
  {
    id: "lowercase",
    label: "One lowercase letter",
    test: (value: string) => /[a-z]/.test(value),
  },
  {
    id: "number",
    label: "One number",
    test: (value: string) => /\d/.test(value),
  },
  {
    id: "special",
    label: "One special character",
    test: (value: string) => /[^A-Za-z0-9]/.test(value),
  },
] as const;

const serverFieldMap = {
  current_password: "current_password",
  new_password: "new_password",
  confirm_password: "confirm_password",
} as const;

const parseFieldErrors = (
  error: unknown,
): Partial<Record<keyof ChangePasswordForm, string>> => {
  if (!error || typeof error !== "object" || !("data" in error)) {
    return {};
  }
  const payload = (error as JsonError).data;
  if (!payload || typeof payload !== "object") {
    return {};
  }

  const result: Partial<Record<keyof ChangePasswordForm, string>> = {};
  for (const [key, value] of Object.entries(payload as Record<string, unknown>)) {
    const target = serverFieldMap[key as keyof typeof serverFieldMap];
    let message: string | null = null;
    if (typeof value === "string") {
      message = value;
    } else if (Array.isArray(value) && value.length) {
      message = String(value[0]);
    }

    if (message && target) {
      result[target] = message;
    } else if (message && key === "non_field_errors") {
      result.new_password = message;
    }
  }

  return result;
};

const extractDetailMessage = (error: unknown): string | null => {
  if (!error || typeof error !== "object" || !("data" in error)) {
    return null;
  }
  const payload = (error as JsonError).data;
  if (!payload) return null;
  if (typeof payload === "string") return payload;

  if (typeof payload === "object") {
    const detail = (payload as Record<string, unknown>).detail;
    if (typeof detail === "string" && detail.trim()) {
      return detail;
    }
    const nonField = (payload as Record<string, unknown>)["non_field_errors"];
    if (Array.isArray(nonField) && nonField.length) {
      return String(nonField[0]);
    }
  }
  return null;
};

export function Security() {
  const [form, setForm] = useState<ChangePasswordForm>(initialForm);
  const [errors, setErrors] = useState<Partial<Record<keyof ChangePasswordForm, string>>>(
    {},
  );
  const [alert, setAlert] = useState<AlertState>(null);
  const [submitting, setSubmitting] = useState(false);

  const loginHistory = [
    {
      device: "Chrome on Windows",
      ip: "192.168.1.1",
      location: "Edmonton, AB",
      date: "Today at 2:30 PM",
    },
    {
      device: "Safari on iPhone",
      ip: "192.168.1.25",
      location: "Edmonton, AB",
      date: "Yesterday at 9:15 AM",
    },
    {
      device: "Firefox on Mac",
      ip: "10.0.0.5",
      location: "Calgary, AB",
      date: "Jan 10, 2025 at 4:22 PM",
    },
  ];

  const requirementStates = passwordRequirements.map((requirement) => ({
    ...requirement,
    passed: requirement.test(form.new_password),
  }));

  const handleFieldChange = (field: keyof ChangePasswordForm, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const validateForm = () => {
    const nextErrors: Partial<Record<keyof ChangePasswordForm, string>> = {};
    if (!form.current_password.trim()) {
      nextErrors.current_password = "Enter your current password.";
    }

    const trimmedNewPassword = form.new_password.trim();
    if (!trimmedNewPassword) {
      nextErrors.new_password = "Enter a new password.";
    } else if (passwordRequirements.some((req) => !req.test(trimmedNewPassword))) {
      nextErrors.new_password =
        "Use at least 8 characters with upper/lower case letters, a number, and a symbol.";
    }

    if (!form.confirm_password.trim()) {
      nextErrors.confirm_password = "Confirm your new password.";
    } else if (form.confirm_password !== form.new_password) {
      nextErrors.confirm_password = "Passwords do not match.";
    }

    setErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAlert(null);

    if (!validateForm()) {
      return;
    }

    setSubmitting(true);
    try {
      await authAPI.changePassword({
        current_password: form.current_password,
        new_password: form.new_password,
      });
      setForm(initialForm);
      setErrors({});
      setAlert({ type: "success" });
    } catch (error) {
      const fieldErrors = parseFieldErrors(error);
      if (Object.keys(fieldErrors).length) {
        setErrors((prev) => ({ ...prev, ...fieldErrors }));
      }
      const detail = extractDetailMessage(error);
      setAlert({ type: "error", detail: detail ?? undefined });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Security Settings</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Manage your password and security preferences
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Change Password</CardTitle>
          <CardDescription>Update your password to keep your account secure</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleSubmit} noValidate>
            {alert && (
              <Alert
                variant={alert.type === "error" ? "destructive" : "default"}
                className={
                  alert.type === "success"
                    ? "border-green-200 bg-green-50 text-green-800"
                    : undefined
                }
              >
                {alert.type === "success" ? (
                  <CheckCircle2 className="h-4 w-4" />
                ) : (
                  <AlertCircle className="h-4 w-4" />
                )}
                <AlertDescription
                  className={
                    alert.type === "success" ? "text-green-800" : undefined
                  }
                >
                  {alert.type === "success"
                    ? "Password changed successfully."
                    : fallbackErrorMessage}
                  {alert.type === "error" && alert.detail && (
                    <span className="block text-xs opacity-90">{alert.detail}</span>
                  )}
                </AlertDescription>
              </Alert>
            )}

            <div className="space-y-2">
              <Label htmlFor="current-password">Current Password</Label>
              <Input
                id="current-password"
                type="password"
                autoComplete="current-password"
                value={form.current_password}
                onChange={(event) => handleFieldChange("current_password", event.target.value)}
                placeholder="********"
              />
              {errors.current_password && (
                <p className="text-xs text-red-500">{errors.current_password}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <Input
                id="new-password"
                type="password"
                autoComplete="new-password"
                value={form.new_password}
                onChange={(event) => handleFieldChange("new_password", event.target.value)}
                placeholder="********"
              />
              {errors.new_password && (
                <p className="text-xs text-red-500">{errors.new_password}</p>
              )}
              <div className="rounded-lg bg-muted/40 p-3">
                <p className="text-xs font-medium" style={{ color: "var(--text-muted)" }}>
                  Password must include:
                </p>
                <ul className="mt-2 space-y-1 text-xs">
                  {requirementStates.map((requirement) => {
                    const Icon = requirement.passed ? CheckCircle2 : AlertCircle;
                    return (
                      <li
                        key={requirement.id}
                        className={`flex items-center gap-2 ${
                          requirement.passed ? "text-green-700" : "text-muted-foreground"
                        }`}
                      >
                        <Icon
                          className={`h-3.5 w-3.5 ${
                            requirement.passed ? "text-green-600" : "text-muted-foreground"
                          }`}
                        />
                        <span>{requirement.label}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirm-password">Confirm New Password</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                value={form.confirm_password}
                onChange={(event) =>
                  handleFieldChange("confirm_password", event.target.value)
                }
                placeholder="********"
              />
              {errors.confirm_password && (
                <p className="text-xs text-red-500">{errors.confirm_password}</p>
              )}
            </div>

            <div>
              <Button
                type="submit"
                disabled={submitting}
                className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                style={{ color: "var(--primary-foreground)" }}
              >
                {submitting ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Updating...
                  </span>
                ) : (
                  "Update Password"
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Two-Factor Authentication</CardTitle>
          <CardDescription>Add an extra layer of security to your account</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <p>SMS Authentication</p>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Receive verification codes via text message
              </p>
            </div>
            <Switch />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p>Email Authentication</p>
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Receive verification codes via email
              </p>
            </div>
            <Switch />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent Login History</CardTitle>
          <CardDescription>Monitor your account activity</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {loginHistory.map((login, index) => (
              <div key={`${login.device}-${login.date}`}>
                {index > 0 && <Separator className="my-4" />}
                <div className="flex justify-between items-start">
                  <div>
                    <p>{login.device}</p>
                    <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                      {login.ip} - {login.location}
                    </p>
                  </div>
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    {login.date}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

