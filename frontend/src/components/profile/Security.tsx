import { FormEvent, useCallback, useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, Eye, EyeOff, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { Switch } from "../ui/switch";
import { Separator } from "../ui/separator";
import { Alert, AlertDescription } from "../ui/alert";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { AuthStore, type Profile } from "@/lib/auth";
import {
  authAPI,
  type JsonError,
  type TwoFactorChannel,
  type TwoFactorSettings,
} from "@/lib/api";

type ChangePasswordForm = {
  current_password: string;
  new_password: string;
  confirm_password: string;
};

type AlertState = { type: "success" | "error"; detail?: string } | null;

type LoginHistoryEntry = {
  id: number;
  device: string;
  ip: string;
  date: string;
  is_new_device: boolean;
};

const fallbackErrorMessage = "Error occurred while updating.";

const initialForm: ChangePasswordForm = {
  current_password: "",
  new_password: "",
  confirm_password: "",
};

const initialPasswordVisibility: Record<keyof ChangePasswordForm, boolean> = {
  current_password: false,
  new_password: false,
  confirm_password: false,
};

const passwordRequirements = [
  {
    id: "length",
    label: "At least 8 characters",
    test: (value: string) => value.length >= 8,
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

const mergeTwoFactorSettings = (
  profile: Profile,
  settings: TwoFactorSettings,
): Profile => ({
  ...profile,
  email_verified: settings.email_verified,
  phone_verified: settings.phone_verified,
  two_factor_email_enabled: settings.two_factor_email_enabled,
  two_factor_sms_enabled: settings.two_factor_sms_enabled,
});

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
  const [passwordVisibility, setPasswordVisibility] = useState(
    initialPasswordVisibility,
  );
  const [submitting, setSubmitting] = useState(false);
  const cachedProfile = AuthStore.getCurrentUser();
  const [profile, setProfile] = useState<Profile | null>(cachedProfile);
  const [twoFactorLoading, setTwoFactorLoading] = useState(true);
  const [twoFactorSaving, setTwoFactorSaving] = useState(false);
  const [smsEnabled, setSmsEnabled] = useState<boolean>(
    () => cachedProfile?.two_factor_sms_enabled ?? false,
  );
  const [emailEnabled, setEmailEnabled] = useState<boolean>(
    () => cachedProfile?.two_factor_email_enabled ?? false,
  );
  const [pendingChannel, setPendingChannel] = useState<TwoFactorChannel | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmSubmitting, setConfirmSubmitting] = useState(false);
  const [loginHistory, setLoginHistory] = useState<LoginHistoryEntry[]>([]);
  const [loginHistoryLoading, setLoginHistoryLoading] = useState(true);
  const [loginHistoryError, setLoginHistoryError] = useState<string | null>(null);
  const phoneVerified = profile?.phone_verified ?? false;
  const emailVerified = profile?.email_verified ?? false;
  const switchesDisabled = twoFactorLoading || twoFactorSaving;
  const verificationMessages: Record<TwoFactorChannel, string> = {
    sms: "Verify your phone before enabling SMS 2FA.",
    email: "Verify your email before enabling email 2FA.",
  };

  const setSwitchValue = (channel: TwoFactorChannel, value: boolean) => {
    if (channel === "sms") {
      setSmsEnabled(value);
    } else {
      setEmailEnabled(value);
    }
  };

  const applySettings = useCallback(
    (settings: TwoFactorSettings, baseOverride?: Profile | null) => {
      setProfile((prev) => {
        const source = baseOverride ?? prev ?? AuthStore.getCurrentUser();
        if (!source) {
          return prev;
        }
        const merged = mergeTwoFactorSettings(source, settings);
        AuthStore.setCurrentUser(merged);
        return merged;
      });
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadTwoFactorSettings() {
      setTwoFactorLoading(true);
      try {
        let baseProfile = AuthStore.getCurrentUser();
        if (!baseProfile) {
          baseProfile = await authAPI.me();
        }
        const settings = await authAPI.twoFactor.getSettings();
        if (cancelled) return;
        applySettings(settings, baseProfile);
        setSmsEnabled(settings.two_factor_sms_enabled);
        setEmailEnabled(settings.two_factor_email_enabled);
      } catch (error) {
        if (!cancelled) {
          toast.error("Unable to load two-factor settings.");
        }
      } finally {
        if (!cancelled) {
          setTwoFactorLoading(false);
        }
      }
    }

    loadTwoFactorSettings();

    return () => {
      cancelled = true;
    };
  }, [applySettings]);

  useEffect(() => {
    let cancelled = false;

    async function loadLoginHistory() {
      setLoginHistoryLoading(true);
      setLoginHistoryError(null);
      try {
        const items = await authAPI.loginHistory(5);
        if (cancelled) {
          return;
        }
        setLoginHistory(items);
      } catch (error) {
        if (!cancelled) {
          setLoginHistoryError("Unable to load recent login history.");
        }
      } finally {
        if (!cancelled) {
          setLoginHistoryLoading(false);
        }
      }
    }

    void loadLoginHistory();

    return () => {
      cancelled = true;
    };
  }, []);

  const persistTwoFactorSetting = async (
    channel: TwoFactorChannel,
    desiredState: boolean,
  ): Promise<boolean> => {
    const payload =
      channel === "sms"
        ? { two_factor_sms_enabled: desiredState }
        : { two_factor_email_enabled: desiredState };

    setTwoFactorSaving(true);
    try {
      const response = await authAPI.twoFactor.updateSettings(payload);
      applySettings(response);
      setSmsEnabled(response.two_factor_sms_enabled);
      setEmailEnabled(response.two_factor_email_enabled);
      toast.success(
        desiredState
          ? "Two-factor authentication enabled."
          : "Two-factor authentication disabled.",
      );
      return true;
    } catch (error) {
      const message =
        extractDetailMessage(error) ?? "Unable to update two-factor settings.";
      toast.error(message);
      setSwitchValue(channel, !desiredState);
      return false;
    } finally {
      setTwoFactorSaving(false);
    }
  };

  const handleTwoFactorToggle = (channel: TwoFactorChannel, checked: boolean) => {
    if (switchesDisabled) {
      return;
    }

    setSwitchValue(channel, checked);

    if (checked) {
      const isVerified = channel === "sms" ? phoneVerified : emailVerified;
      if (!isVerified) {
        toast.error(verificationMessages[channel]);
        setSwitchValue(channel, false);
        return;
      }
      setPendingChannel(channel);
      setConfirmOpen(true);
      return;
    }

    void persistTwoFactorSetting(channel, false);
  };

  const handleConfirmEnable = async () => {
    if (!pendingChannel) return;
    setConfirmSubmitting(true);
    const success = await persistTwoFactorSetting(pendingChannel, true);
    setConfirmSubmitting(false);
    setPendingChannel(null);
    setConfirmOpen(false);
    if (!success) {
      // State already reverted inside persistTwoFactorSetting on failure.
    }
  };

  const handleConfirmCancel = () => {
    if (pendingChannel) {
      setSwitchValue(pendingChannel, false);
    }
    setPendingChannel(null);
    setConfirmOpen(false);
  };

  const handleConfirmDialogChange = (nextOpen: boolean) => {
    if (!nextOpen) {
      if (confirmSubmitting) {
        return;
      }
      if (pendingChannel) {
        setSwitchValue(pendingChannel, false);
        setPendingChannel(null);
      }
    }
    setConfirmOpen(nextOpen);
  };

  const togglePasswordVisibility = (field: keyof ChangePasswordForm) => {
    setPasswordVisibility((prev) => ({ ...prev, [field]: !prev[field] }));
  };

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
        "Use at least 8 characters, including a number and a special character.";
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
      setPasswordVisibility(initialPasswordVisibility);
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
    <>
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
              <div className="relative">
                <Input
                  id="current-password"
                  type={passwordVisibility.current_password ? "text" : "password"}
                  autoComplete="current-password"
                  value={form.current_password}
                  onChange={(event) =>
                    handleFieldChange("current_password", event.target.value)
                  }
                  placeholder="********"
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => togglePasswordVisibility("current_password")}
                  className="absolute inset-y-0 right-3 flex items-center text-muted-foreground transition-colors hover:text-foreground"
                  aria-label={`${
                    passwordVisibility.current_password ? "Hide" : "Show"
                  } current password`}
                >
                  {passwordVisibility.current_password ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
              {errors.current_password && (
                <p className="text-xs text-red-500">{errors.current_password}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="new-password">New Password</Label>
              <div className="relative">
                <Input
                  id="new-password"
                  type={passwordVisibility.new_password ? "text" : "password"}
                  autoComplete="new-password"
                  value={form.new_password}
                  onChange={(event) => handleFieldChange("new_password", event.target.value)}
                  placeholder="********"
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => togglePasswordVisibility("new_password")}
                  className="absolute inset-y-0 right-3 flex items-center text-muted-foreground transition-colors hover:text-foreground"
                  aria-label={`${
                    passwordVisibility.new_password ? "Hide" : "Show"
                  } new password`}
                >
                  {passwordVisibility.new_password ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
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
              <div className="relative">
                <Input
                  id="confirm-password"
                  type={passwordVisibility.confirm_password ? "text" : "password"}
                  autoComplete="new-password"
                  value={form.confirm_password}
                  onChange={(event) =>
                    handleFieldChange("confirm_password", event.target.value)
                  }
                  placeholder="********"
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => togglePasswordVisibility("confirm_password")}
                  className="absolute inset-y-0 right-3 flex items-center text-muted-foreground transition-colors hover:text-foreground"
                  aria-label={`${
                    passwordVisibility.confirm_password ? "Hide" : "Show"
                  } confirm password`}
                >
                  {passwordVisibility.confirm_password ? (
                    <EyeOff className="h-4 w-4" aria-hidden="true" />
                  ) : (
                    <Eye className="h-4 w-4" aria-hidden="true" />
                  )}
                </button>
              </div>
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
          {twoFactorLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              Loading settings...
            </div>
          )}
          <div className="flex items-center justify-between">
            <div>
              <p>SMS Authentication</p>
              <p className="text-sm text-muted-foreground">
                Receive verification codes via text message
              </p>
              <p className="text-xs text-muted-foreground">
                Phone must be verified first.
              </p>
            </div>
            <Switch
              checked={smsEnabled}
              disabled={switchesDisabled}
              onCheckedChange={(checked) => handleTwoFactorToggle("sms", checked)}
              aria-label="Toggle SMS two-factor authentication"
              className="border border-border data-[state=unchecked]:bg-muted"
            />
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <div>
              <p>Email Authentication</p>
              <p className="text-sm text-muted-foreground">
                Receive verification codes via email
              </p>
              <p className="text-xs text-muted-foreground">Email must be verified first.</p>
            </div>
            <Switch
              checked={emailEnabled}
              disabled={switchesDisabled}
              onCheckedChange={(checked) => handleTwoFactorToggle("email", checked)}
              aria-label="Toggle email two-factor authentication"
              className="border border-border data-[state=unchecked]:bg-muted"
            />
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
            {loginHistoryLoading && (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Loading recent logins...
              </p>
            )}
            {loginHistoryError && (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                {loginHistoryError}
              </p>
            )}
            {!loginHistoryLoading && !loginHistoryError && loginHistory.length === 0 && (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                No recent logins yet.
              </p>
            )}
            {loginHistory.map((login, index) => (
              <div key={login.id}>
                {index > 0 && <Separator className="my-4" />}
                <div className="flex justify-between items-start">
                  <div>
                    <p>{login.device}</p>
                    <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                      {login.ip}
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

      <Dialog open={confirmOpen} onOpenChange={handleConfirmDialogChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Enable two-factor authentication?</DialogTitle>
            <DialogDescription>
              Are you sure you want to turn on two-factor authentication? You'll need a
              verification code every time you log in.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:justify-end">
            <Button
              type="button"
              variant="outline"
              onClick={handleConfirmCancel}
              disabled={confirmSubmitting || twoFactorSaving}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleConfirmEnable}
              disabled={confirmSubmitting || twoFactorSaving}
              className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
              style={{ color: "var(--primary-foreground)" }}
            >
              {confirmSubmitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Enabling...
                </>
              ) : (
                "Yes, turn on 2FA"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

