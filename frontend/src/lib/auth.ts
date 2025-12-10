/**
 * Minimal auth storage helpers for keeping JWTs and cached user data.
 * LocalStorage is acceptable for now; upgrade to HTTP-only cookies later.
 */

export type AuthTokens = {
  access: string;
  refresh: string;
};

export type UserProfile = {
  id: number;
  username: string;
  email: string | null;
  phone: string | null;
  first_name: string;
  last_name: string;
  street_address: string;
  city: string;
  province: string;
  postal_code: string;
  can_rent: boolean;
  can_list: boolean;
  email_verified: boolean;
  phone_verified: boolean;
  two_factor_email_enabled: boolean;
  two_factor_sms_enabled: boolean;
  identity_verified?: boolean;
  avatar_url?: string | null;
  avatar_uploaded?: boolean;
  date_joined?: string;
  stripe_customer_id?: string | null;
  birth_date?: string | null;
};

const TOKENS_KEY = "renter.auth.tokens";
const USER_KEY = "renter.auth.user";
const AUTH_CHANGE_EVENT = "renter:auth-change";

function read<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write<T>(key: string, value: T | null) {
  try {
    if (value === null) {
      window.localStorage.removeItem(key);
    } else {
      window.localStorage.setItem(key, JSON.stringify(value));
    }
  } catch {
    // LocalStorage can fail (Safari private mode). Fail silently; API calls will re-auth.
  }
}

function emitAuthChange() {
  if (typeof window === "undefined" || typeof window.dispatchEvent !== "function") {
    return;
  }
  window.dispatchEvent(new Event(AUTH_CHANGE_EVENT));
}

/** Lightweight auth store for tokens + cached profile. */
export const AuthStore = {
  getTokens(): AuthTokens | null {
    return read<AuthTokens>(TOKENS_KEY);
  },
  setTokens(tokens: AuthTokens) {
    write(TOKENS_KEY, tokens);
    emitAuthChange();
  },
  clearTokens() {
    write<AuthTokens>(TOKENS_KEY, null);
    write<UserProfile>(USER_KEY, null);
    emitAuthChange();
  },
  getAccess(): string | null {
    return this.getTokens()?.access ?? null;
  },
  setCurrentUser(user: UserProfile | null) {
    write(USER_KEY, user);
    emitAuthChange();
  },
  getCurrentUser(): UserProfile | null {
    return read<UserProfile>(USER_KEY);
  },
  subscribe(listener: () => void) {
    if (typeof window === "undefined" || typeof window.addEventListener !== "function") {
      return () => {};
    }
    const handler = () => listener();
    window.addEventListener(AUTH_CHANGE_EVENT, handler);
    return () => window.removeEventListener(AUTH_CHANGE_EVENT, handler);
  },
};

export type { UserProfile as Profile };
