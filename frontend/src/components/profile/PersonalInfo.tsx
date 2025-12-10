import { FormEvent, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Loader2, AlertCircle } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { authAPI, type JsonError } from "@/lib/api";
import { AuthStore, type Profile } from "@/lib/auth";

type PersonalInfoForm = {
  first_name: string;
  last_name: string;
  phone: string;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  birth_date: string;
};

type ContactChannel = "email" | "phone";

type VerificationState = {
  active: boolean;
  sending: boolean;
  verifying: boolean;
  code: string;
  error: string | null;
  challengeId: number | null;
  resendAvailableAt: number | null;
};

const createVerificationState = (): VerificationState => ({
  active: false,
  sending: false,
  verifying: false,
  code: "",
  error: null,
  challengeId: null,
  resendAvailableAt: null,
});

interface PersonalInfoProps {
  onProfileUpdate?: (profile: Profile | null) => void;
}

const emptyForm: PersonalInfoForm = {
  first_name: "",
  last_name: "",
  phone: "",
  street_address: "",
  city: "",
  province: "",
  postal_code: "",
  birth_date: "",
};

const mapProfileToForm = (profile?: Profile | null): PersonalInfoForm => ({
  first_name: profile?.first_name ?? "",
  last_name: profile?.last_name ?? "",
  phone: profile?.phone ?? "",
  street_address: profile?.street_address ?? "",
  city: profile?.city ?? "",
  province: profile?.province ?? "",
  postal_code: profile?.postal_code ?? "",
  birth_date: profile?.birth_date ?? "",
});

const parseFieldErrors = (data: unknown): Record<string, string> => {
  if (!data || typeof data !== "object") return {};
  return Object.entries(data as Record<string, unknown>).reduce<Record<string, string>>(
    (acc, [key, value]) => {
      if (Array.isArray(value)) {
        acc[key] = value.join(" ");
      } else if (typeof value === "string") {
        acc[key] = value;
      }
      return acc;
    },
    {},
  );
};

const extractErrorMessage = (error: unknown, fallback: string): string => {
  if (!error || typeof error !== "object" || !("data" in error)) {
    return fallback;
  }
  const payload = (error as JsonError).data;
  if (!payload) return fallback;
  if (typeof payload === "string") return payload;
  if (typeof payload === "object") {
    const detail = (payload as Record<string, unknown>).detail;
    if (typeof detail === "string") return detail;
    const nonField = (payload as Record<string, unknown>)["non_field_errors"];
    if (Array.isArray(nonField) && nonField.length) {
      const first = nonField[0];
      if (first) return String(first);
    }
    for (const value of Object.values(payload as Record<string, unknown>)) {
      if (typeof value === "string" && value.trim()) {
        return value;
      }
      if (Array.isArray(value) && value.length) {
        return String(value[0]);
      }
    }
  }
  return fallback;
};

const toTimestamp = (value?: string | null): number => {
  if (!value) {
    return Date.now() + 60000;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() + 60000 : parsed;
};

export function PersonalInfo({ onProfileUpdate }: PersonalInfoProps = {}) {
  const cachedProfile = AuthStore.getCurrentUser();
  const hasAuth = Boolean(AuthStore.getTokens());

  const [profile, setProfile] = useState<Profile | null>(cachedProfile);
  const [form, setForm] = useState<PersonalInfoForm>(() => mapProfileToForm(cachedProfile));
  const [loading, setLoading] = useState(hasAuth && !cachedProfile);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [verification, setVerification] = useState<Record<ContactChannel, VerificationState>>({
    email: createVerificationState(),
    phone: createVerificationState(),
  });
  const [, setVerificationTick] = useState(0);

  useEffect(() => {
    setForm(mapProfileToForm(profile));
  }, [profile]);

  useEffect(() => {
    if (!profile) {
      setVerification({
        email: createVerificationState(),
        phone: createVerificationState(),
      });
      return;
    }
    setVerification((prev) => {
      let changed = false;
      const next = { ...prev };
      if (profile.email_verified && prev.email.active) {
        next.email = createVerificationState();
        changed = true;
      }
      if (profile.phone_verified && prev.phone.active) {
        next.phone = createVerificationState();
        changed = true;
      }
      return changed ? next : prev;
    });
  }, [profile]);

  useEffect(() => {
    const channels: ContactChannel[] = ["email", "phone"];
    const now = Date.now();
    const hasPending = channels.some((channel) => {
      const state = verification[channel];
      return (
        state.active &&
        state.resendAvailableAt !== null &&
        state.resendAvailableAt > now
      );
    });
    if (!hasPending) {
      return;
    }
    const id = window.setInterval(() => {
      setVerificationTick((prev) => prev + 1);
    }, 1000);
    return () => window.clearInterval(id);
  }, [
    verification.email.active,
    verification.email.resendAvailableAt,
    verification.phone.active,
    verification.phone.resendAvailableAt,
  ]);

  useEffect(() => {
    let cancelled = false;

    if (!hasAuth) {
      setProfile(null);
      onProfileUpdate?.(null);
      setLoading(false);
      setFetchError("Log in to manage your personal information.");
      return () => {
        cancelled = true;
      };
    }

    async function loadProfile() {
      setFetchError(null);
      setLoading(true);
      try {
        const data = await authAPI.me();
        if (cancelled) return;
        setProfile(data);
        AuthStore.setCurrentUser(data);
        onProfileUpdate?.(data);
      } catch (error) {
        if (cancelled) return;
        const status =
          error && typeof error === "object" && "status" in error
            ? (error as JsonError).status
            : null;
        if (status === 401) {
          setFetchError("Your session expired. Please log in again.");
          AuthStore.clearTokens();
          setProfile(null);
          onProfileUpdate?.(null);
        } else {
          setFetchError("Unable to load your profile. Please try again.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadProfile();
    return () => {
      cancelled = true;
    };
  }, [hasAuth]);

  const updateVerification = (
    channel: ContactChannel,
    updater: (state: VerificationState) => VerificationState,
  ) => {
    setVerification((prev) => ({
      ...prev,
      [channel]: updater(prev[channel]),
    }));
  };

  const ensureContactReady = (channel: ContactChannel): boolean => {
    if (!profile) {
      toast.info("Log in to verify your contact information.");
      return false;
    }
    if (channel === "email") {
      if (!profile.email) {
        toast.error("Add an email address before verifying.");
        return false;
      }
      return true;
    }
    const savedPhone = profile.phone?.trim();
    const currentPhone = form.phone.trim();
    if (!currentPhone) {
      toast.error("Enter a phone number first.");
      return false;
    }
    if (!savedPhone || currentPhone !== savedPhone) {
      toast.info("Save your phone number before verifying it.");
      return false;
    }
    return true;
  };

  const handleVerificationRequest = async (channel: ContactChannel) => {
    if (verification[channel].sending) {
      return;
    }
    if (!ensureContactReady(channel)) {
      return;
    }
    updateVerification(channel, () => ({
      ...createVerificationState(),
      active: true,
      sending: true,
    }));
    try {
      const response = await authAPI.contactVerification.request({ channel });
      updateVerification(channel, (state) => ({
        ...state,
        active: true,
        sending: false,
        challengeId: response.challenge_id,
        resendAvailableAt: toTimestamp(response.resend_available_at),
      }));
      toast.success(
        `Verification code sent to your ${channel === "email" ? "email" : "phone"}.`,
      );
    } catch (error) {
      const message = extractErrorMessage(
        error,
        "Unable to send a verification code right now.",
      );
      updateVerification(channel, (state) => ({
        ...state,
        sending: false,
        error: message,
      }));
      toast.error(message);
    }
  };

  const handleCodeChange = (channel: ContactChannel, value: string) => {
    updateVerification(channel, (state) => ({
      ...state,
      code: value,
      error: null,
    }));
  };

  const handleVerificationSubmit = async (channel: ContactChannel) => {
    const state = verification[channel];
    const code = state.code.trim();
    if (!code || state.verifying) {
      return;
    }
    updateVerification(channel, (prevState) => ({
      ...prevState,
      verifying: true,
      error: null,
    }));
    let verified = false;
    try {
      const response = await authAPI.contactVerification.verify({
        channel,
        code,
        challenge_id: state.challengeId ?? undefined,
      });
      verified = true;
      setProfile(response.profile);
      AuthStore.setCurrentUser(response.profile);
      onProfileUpdate?.(response.profile);
      toast.success(
        `${channel === "email" ? "Email" : "Phone"} verified successfully.`,
      );
    } catch (error) {
      const message = extractErrorMessage(error, "Unable to verify the code.");
      updateVerification(channel, (prevState) => ({
        ...prevState,
        error: message,
      }));
      toast.error(message);
    } finally {
      if (verified) {
        setVerification((prev) => ({
          ...prev,
          [channel]: createVerificationState(),
        }));
      } else {
        updateVerification(channel, (prevState) => ({
          ...prevState,
          verifying: false,
        }));
      }
    }
  };

  const handleFieldChange = <K extends keyof PersonalInfoForm>(field: K, value: string) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving || !profile) return;

    setSaving(true);
    setErrors({});
    try {
      const payload = {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        phone: form.phone.trim() || null,
        street_address: form.street_address.trim(),
        city: form.city.trim(),
        province: form.province.trim(),
        postal_code: form.postal_code.trim(),
        birth_date: form.birth_date || null,
      };
      const updated = await authAPI.updateProfile(payload);
      setProfile(updated);
      AuthStore.setCurrentUser(updated);
      onProfileUpdate?.(updated);
      toast.success("Profile updated.");
    } catch (error) {
      const fieldErrors =
        error && typeof error === "object" && "data" in error
          ? parseFieldErrors((error as JsonError).data)
          : {};
      setErrors(fieldErrors);
      toast.error("Unable to save your changes.");
    } finally {
      setSaving(false);
    }
  };

  const emailVerified = Boolean(profile?.email_verified);
  const phoneVerified = Boolean(profile?.phone_verified);
  const inputsDisabled = loading || saving || !profile;
  const emailInputPadding = emailVerified
    ? "pl-10"
    : verification.email.active
      ? "pr-32"
      : "pr-24";
  const phoneInputPadding = phoneVerified
    ? "pl-10"
    : verification.phone.active
      ? "pr-32"
      : "pr-24";
  const renderVerificationControls = (channel: ContactChannel) => {
    const isVerified = channel === "email" ? emailVerified : phoneVerified;
    const state = verification[channel];
    if (isVerified || !state.active) {
      return null;
    }
    const now = Date.now();
    const canResend =
      !state.sending && (!state.resendAvailableAt || state.resendAvailableAt <= now);
    const remainingSeconds =
      !canResend && state.resendAvailableAt
        ? Math.max(0, Math.ceil((state.resendAvailableAt - now) / 1000))
        : 0;
    const resendLabel = state.sending
      ? "Sending..."
      : canResend
        ? "Resend Code"
        : `Resend in ${remainingSeconds}s`;
    const inputId = channel === "email" ? "email-code" : "phone-code";
    return (
      <div className="space-y-2">
        <Label htmlFor={inputId}>Verification Code</Label>
        <div className="relative">
          <Input
            id={inputId}
            value={state.code}
            onChange={(event) => handleCodeChange(channel, event.target.value)}
            className="h-11 pr-32"
            autoComplete="one-time-code"
          />
          <button
            type="button"
            className="absolute right-2 top-1/2 -translate-y-1/2 text-xs font-medium text-[var(--primary)] px-2 py-1 bg-transparent border-none disabled:opacity-50"
            onClick={() => handleVerificationRequest(channel)}
            disabled={!canResend}
          >
            {resendLabel}
          </button>
        </div>
        {state.error && <p className="text-xs text-red-500">{state.error}</p>}
        <Button
          type="button"
          disabled={state.verifying || !state.code.trim()}
          className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
          style={{ color: "var(--primary-foreground)" }}
          onClick={() => handleVerificationSubmit(channel)}
        >
          {state.verifying ? "Verifying..." : "Verify Code"}
        </Button>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Personal Information</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Manage your personal details and contact information
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Profile Details</CardTitle>
          <CardDescription>Update your personal information</CardDescription>
        </CardHeader>

        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-6">
            {fetchError && !loading && (
              <div className="flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
                <AlertCircle className="mt-0.5 h-4 w-4" />
                <span>{fetchError}</span>
              </div>
            )}

            {loading ? (
              <div className="space-y-4">
                {[...Array(5)].map((_, index) => (
                  <div key={index} className="h-12 rounded-md bg-muted animate-pulse" />
                ))}
              </div>
            ) : !profile ? (
              <p style={{ color: "var(--text-muted)" }}>
                {fetchError ?? "No profile data is available yet."}
              </p>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="firstName">First Name</Label>
                    <Input
                      id="firstName"
                      value={form.first_name}
                      disabled={inputsDisabled}
                      className="h-11"
                      onChange={(event) => handleFieldChange("first_name", event.target.value)}
                    />
                    {errors.first_name && (
                      <p className="text-xs text-red-500">{errors.first_name}</p>
                    )}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="lastName">Last Name</Label>
                    <Input
                      id="lastName"
                      value={form.last_name}
                      disabled={inputsDisabled}
                      className="h-11"
                      onChange={(event) => handleFieldChange("last_name", event.target.value)}
                    />
                    {errors.last_name && (
                      <p className="text-xs text-red-500">{errors.last_name}</p>
                    )}
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="birthDate">Birth date</Label>
                  <Input
                    id="birthDate"
                    type="date"
                    value={form.birth_date}
                    disabled={inputsDisabled}
                    className="h-11"
                    onChange={(event) => handleFieldChange("birth_date", event.target.value)}
                  />
                  {errors.birth_date && (
                    <p className="text-xs text-red-500">{errors.birth_date}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="email">Email Address</Label>
                  <div className="relative">
                    <Input
                      id="email"
                      type="email"
                      value={profile.email ?? ""}
                      disabled
                      className={`h-11 ${emailInputPadding}`}
                    />
                    {emailVerified ? (
                      <CheckCircle2 className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-green-600" />
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        className="absolute right-2 top-1/2 -translate-y-1/2 h-8 px-3 text-xs font-normal"
                        onClick={() => handleVerificationRequest("email")}
                        disabled={verification.email.sending}
                      >
                        {verification.email.sending ? "Sending..." : "Verify"}
                      </Button>
                    )}
                  </div>
                  <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                    {emailVerified
                      ? "Email is verified and cannot be changed."
                      : "Email is not verified yet."}
                  </p>
                  {!emailVerified && (
                    <div className="pt-2">{renderVerificationControls("email")}</div>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="phone">Phone Number</Label>
                  <div className="relative">
                    <Input
                      id="phone"
                      type="tel"
                      value={form.phone}
                      disabled={inputsDisabled}
                      onChange={(event) => handleFieldChange("phone", event.target.value)}
                      className={`h-11 ${phoneInputPadding}`}
                    />
                    {phoneVerified ? (
                      <CheckCircle2 className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-green-600" />
                    ) : (
                      <Button
                        type="button"
                        variant="outline"
                        className="absolute right-2 top-1/2 -translate-y-1/2 h-8 px-3 text-xs font-normal"
                        onClick={() => handleVerificationRequest("phone")}
                        disabled={verification.phone.sending}
                      >
                        {verification.phone.sending ? "Sending..." : "Verify"}
                      </Button>
                    )}
                  </div>
                  {errors.phone && <p className="text-xs text-red-500">{errors.phone}</p>}
                  {!phoneVerified && (
                    <div className="pt-2">{renderVerificationControls("phone")}</div>
                  )}
                </div>

                <div className="space-y-4">
                  <h4>Address</h4>
                  <div className="space-y-2">
                    <Label htmlFor="street">Street Address</Label>
                    <Input
                      id="street"
                      value={form.street_address}
                      disabled={inputsDisabled}
                      className="h-11"
                      onChange={(event) => handleFieldChange("street_address", event.target.value)}
                    />
                    {errors.street_address && (
                      <p className="text-xs text-red-500">{errors.street_address}</p>
                    )}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="city">City</Label>
                      <Input
                        id="city"
                        value={form.city}
                        disabled={inputsDisabled}
                        className="h-11"
                        onChange={(event) => handleFieldChange("city", event.target.value)}
                      />
                      {errors.city && <p className="text-xs text-red-500">{errors.city}</p>}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="province">Province</Label>
                      <Input
                        id="province"
                        value={form.province}
                        disabled={inputsDisabled}
                        className="h-11"
                        onChange={(event) => handleFieldChange("province", event.target.value)}
                      />
                      {errors.province && (
                        <p className="text-xs text-red-500">{errors.province}</p>
                      )}
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="postal">Postal Code</Label>
                      <Input
                        id="postal"
                        value={form.postal_code}
                        disabled={inputsDisabled}
                        className="h-11"
                        onChange={(event) => handleFieldChange("postal_code", event.target.value)}
                      />
                      {errors.postal_code && (
                        <p className="text-xs text-red-500">{errors.postal_code}</p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="pt-4">
                  <Button
                    type="submit"
                    disabled={inputsDisabled || saving}
                    className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                    style={{ color: "var(--primary-foreground)" }}
                  >
                    {saving ? (
                      <span className="flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Saving...
                      </span>
                    ) : (
                      "Save Changes"
                    )}
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </form>
      </Card>
    </div>
  );
}
