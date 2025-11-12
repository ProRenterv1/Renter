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

export type TokenResponse = AuthTokens;

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
};
