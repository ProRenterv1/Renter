import { AuthStore, type AuthTokens, type Profile } from "./auth";

export const API_BASE = "/api";

export type JsonError = {
  status: number;
  data: unknown;
};

export interface LoginRequest {
  identifier: string;
  password: string;
}

export type TwoFactorChannel = "email" | "sms";

export interface TwoFactorLoginStartResponse {
  requires_2fa: true;
  challenge_id: number;
  channel: TwoFactorChannel;
  contact_hint: string;
  resend_available_at: string;
}

export interface TwoFactorSettings {
  two_factor_email_enabled: boolean;
  two_factor_sms_enabled: boolean;
  email_verified: boolean;
  phone_verified: boolean;
}

export interface TwoFactorVerifyLoginPayload {
  challenge_id: number;
  code: string;
}

export interface TwoFactorResendPayload {
  challenge_id: number;
}

export interface TwoFactorResendResponse {
  ok: boolean;
  resend_available_at: string;
}

export type TokenResponse = AuthTokens | TwoFactorLoginStartResponse;

export interface SignupPayload {
  username?: string;
  email?: string;
  phone?: string;
  password: string;
  first_name?: string;
  last_name?: string;
  can_rent?: boolean;
  can_list?: boolean;
}

export interface PasswordResetRequestPayload {
  contact: string;
}

export interface PasswordResetVerifyPayload {
  challenge_id?: number;
  contact?: string;
  code: string;
}

export interface PasswordResetCompletePayload extends PasswordResetVerifyPayload {
  new_password: string;
}

export interface PasswordResetRequestResponse {
  ok: boolean;
  challenge_id?: number;
}

export interface PasswordResetVerifyResponse {
  verified: boolean;
  challenge_id: number;
}

export interface PasswordResetCompleteResponse {
  ok: boolean;
}

export interface ChangePasswordPayload {
  current_password: string;
  new_password: string;
}

export interface ChangePasswordResponse {
  ok: boolean;
}

export type ContactVerificationChannel = "email" | "phone";

export interface ContactVerificationRequestPayload {
  channel: ContactVerificationChannel;
}

export interface ContactVerificationRequestResponse {
  challenge_id: number;
  channel: ContactVerificationChannel;
  expires_at: string;
  resend_available_at: string;
}

export interface ContactVerificationVerifyPayload {
  channel: ContactVerificationChannel;
  code: string;
  challenge_id?: number;
}

export interface ContactVerificationVerifyResponse {
  verified: boolean;
  channel: ContactVerificationChannel;
  profile: Profile;
}

export type UpdateProfilePayload = Partial<
  Pick<
    Profile,
    | "first_name"
    | "last_name"
    | "street_address"
    | "city"
    | "province"
    | "postal_code"
    | "can_rent"
    | "can_list"
  >
> & { phone?: string | null };

/**
 * Wrapper around fetch that automatically attaches JSON headers + auth token.
 * Throws a structured error containing HTTP status and parsed body.
 */
export async function jsonFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const headers = new Headers(init.headers ?? {});
  headers.set("Content-Type", "application/json");

  const token = AuthStore.getAccess();
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let body = init.body;
  if (body && typeof body !== "string") {
    body = JSON.stringify(body);
  }

  const response = await fetch(url, {
    ...init,
    headers,
    body,
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const error: JsonError = { status: response.status, data };
    throw error;
  }

  return data as T;
}

export const authAPI = {
  login(payload: LoginRequest) {
    return jsonFetch<TokenResponse>("/users/token/", {
      method: "POST",
      body: payload,
    });
  },
  signup(payload: SignupPayload) {
    return jsonFetch<Profile>("/users/signup/", {
      method: "POST",
      body: payload,
    });
  },
  me() {
    return jsonFetch<Profile>("/users/me/", { method: "GET" });
  },
  updateProfile(payload: UpdateProfilePayload) {
    return jsonFetch<Profile>("/users/me/", { method: "PATCH", body: payload });
  },
  changePassword(payload: ChangePasswordPayload) {
    return jsonFetch<ChangePasswordResponse>("/users/change-password/", {
      method: "POST",
      body: payload,
    });
  },
  passwordReset: {
    request(payload: PasswordResetRequestPayload) {
      return jsonFetch<PasswordResetRequestResponse>(
        "/users/password-reset/request/",
        { method: "POST", body: payload },
      );
    },
    verify(payload: PasswordResetVerifyPayload) {
      return jsonFetch<PasswordResetVerifyResponse>(
        "/users/password-reset/verify/",
        { method: "POST", body: payload },
      );
    },
    complete(payload: PasswordResetCompletePayload) {
      return jsonFetch<PasswordResetCompleteResponse>(
        "/users/password-reset/complete/",
        { method: "POST", body: payload },
      );
    },
  },
  contactVerification: {
    request(payload: ContactVerificationRequestPayload) {
      return jsonFetch<ContactVerificationRequestResponse>(
        "/users/contact-verification/request/",
        { method: "POST", body: payload },
      );
    },
    verify(payload: ContactVerificationVerifyPayload) {
      return jsonFetch<ContactVerificationVerifyResponse>(
        "/users/contact-verification/verify/",
        { method: "POST", body: payload },
      );
    },
  },
  twoFactor: {
    getSettings() {
      return jsonFetch<TwoFactorSettings>("/users/two-factor/settings/", {
        method: "GET",
      });
    },
    updateSettings(
      payload: Partial<
        Pick<TwoFactorSettings, "two_factor_email_enabled" | "two_factor_sms_enabled">
      >,
    ) {
      return jsonFetch<TwoFactorSettings>("/users/two-factor/settings/", {
        method: "PATCH",
        body: payload,
      });
    },
    verifyLogin(payload: TwoFactorVerifyLoginPayload) {
      return jsonFetch<AuthTokens>("/users/two-factor/verify-login/", {
        method: "POST",
        body: payload,
      });
    },
    resendLogin(payload: TwoFactorResendPayload) {
      return jsonFetch<TwoFactorResendResponse>("/users/two-factor/resend-login/", {
        method: "POST",
        body: payload,
      });
    },
  },
};
