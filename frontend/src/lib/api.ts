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

export interface LoginHistoryEntry {
  id: number;
  device: string;
  ip: string;
  location: string | null;
  date: string;
  is_new_device: boolean;
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

export interface ListingPhoto {
  id: number;
  listing: number;
  owner: number;
  key: string;
  url: string;
  filename: string;
  content_type: string;
  size: number | null;
  etag: string;
  status: string;
  av_status: string;
  width: number | null;
  height: number | null;
  created_at: string;
  updated_at: string;
}

export interface ListingCategory {
  id: number;
  name: string;
  slug: string;
  icon: string;
  accent: string;
  icon_color: string;
}

export interface Listing {
  id: number;
  slug: string;
  owner: number;
  owner_username: string;
  owner_first_name: string;
  owner_last_name: string;
  title: string;
  description: string;
  daily_price_cad: string;
  replacement_value_cad: string;
  damage_deposit_cad: string;
  city: string;
  postal_code: string;
  postalCode?: string;
  category: string | null;
  category_name: string | null;
  is_active: boolean;
  is_available: boolean;
  photos: ListingPhoto[];
  created_at: string;
}

export interface CreateListingPayload {
  title: string;
  description?: string;
  category?: string | null;
  daily_price_cad: number;
  replacement_value_cad?: number;
  damage_deposit_cad?: number;
  city: string;
  postal_code: string;
  is_available?: boolean;
}

export type UpdateListingPayload = Partial<{
  title: string;
  description: string;
  category: string | null;
  daily_price_cad: number;
  replacement_value_cad: number;
  damage_deposit_cad: number;
  city: string;
  postal_code: string;
  is_active: boolean;
  is_available: boolean;
}>;

export interface ListingListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: Listing[];
}

export interface ListingListParams {
  q?: string;
  category?: string;
  city?: string;
  price_min?: number;
  price_max?: number;
  page?: number;
}

export type BookingStatus = "requested" | "confirmed" | "canceled" | "completed";

export interface BookingTotals {
  days: string;
  daily_price_cad: string;
  rental_subtotal: string;
  service_fee: string;
  damage_deposit: string;
  total_charge: string;
}

export interface Booking {
  id: number;
  status: BookingStatus;
  start_date: string;
  end_date: string;
  listing: number;
  listing_title: string;
  owner: number;
  renter: number;
  totals: BookingTotals;
  deposit_hold_id: string;
  created_at: string;
  updated_at: string;
}

export interface CreateBookingPayload {
  listing: number;
  start_date: string;
  end_date: string;
}

export interface PhotoPresignRequest {
  filename: string;
  content_type?: string;
  size: number;
}

export interface PhotoPresignResponse {
  key: string;
  upload_url: string;
  headers: Record<string, string>;
  max_bytes: number;
  tagging: string;
}

export interface PhotoCompletePayload {
  key: string;
  etag: string;
  filename: string;
  content_type: string;
  size: number;
}

export interface PhotoCompleteResponse {
  status: string;
  key: string;
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
  loginHistory(limit: number = 5) {
    const params = new URLSearchParams({ limit: String(limit) }).toString();
    const query = params ? `?${params}` : "";
    return jsonFetch<LoginHistoryEntry[]>(`/users/login-events/${query}`, {
      method: "GET",
    });
  },
};

export const listingsAPI = {
  list(params: ListingListParams = {}) {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    if (params.category) search.set("category", params.category);
    if (params.city) search.set("city", params.city);
    if (params.price_min !== undefined) {
      search.set("price_min", String(params.price_min));
    }
    if (params.price_max !== undefined) {
      search.set("price_max", String(params.price_max));
    }
    if (params.page !== undefined) {
      search.set("page", String(params.page));
    }
    const query = search.toString();
    const path = `/listings/${query ? `?${query}` : ""}`;
    return jsonFetch<ListingListResponse>(path, { method: "GET" });
  },
  mine(params: ListingListParams = {}) {
    const search = new URLSearchParams();
    if (params.q) search.set("q", params.q);
    if (params.category) search.set("category", params.category);
    if (params.city) search.set("city", params.city);
    if (params.price_min !== undefined) {
      search.set("price_min", String(params.price_min));
    }
    if (params.price_max !== undefined) {
      search.set("price_max", String(params.price_max));
    }
    if (params.page !== undefined) {
      search.set("page", String(params.page));
    }
    const query = search.toString();
    const path = `/listings/mine/${query ? `?${query}` : ""}`;
    return jsonFetch<ListingListResponse>(path, { method: "GET" });
  },
  categories() {
    return jsonFetch<ListingCategory[]>("/listings/categories/", { method: "GET" });
  },
  retrieve(slug: string) {
    return jsonFetch<Listing>(`/listings/${slug}/`, { method: "GET" });
  },
  create(payload: CreateListingPayload) {
    return jsonFetch<Listing>("/listings/", { method: "POST", body: payload });
  },
  update(slug: string, payload: UpdateListingPayload) {
    return jsonFetch<Listing>(`/listings/${slug}/`, {
      method: "PATCH",
      body: payload,
    });
  },
  delete(slug: string) {
    return jsonFetch<void>(`/listings/${slug}/`, {
      method: "DELETE",
    });
  },
  presignPhoto(listingId: number, payload: PhotoPresignRequest) {
    return jsonFetch<PhotoPresignResponse>(
      `/listings/${listingId}/photos/presign/`,
      { method: "POST", body: payload },
    );
  },
  completePhoto(listingId: number, payload: PhotoCompletePayload) {
    return jsonFetch<PhotoCompleteResponse>(
      `/listings/${listingId}/photos/complete/`,
      { method: "POST", body: payload },
    );
  },
  photos(slug: string) {
    return jsonFetch<ListingPhoto[]>(`/listings/${slug}/photos/`, {
      method: "GET",
    });
  },
  deletePhoto(slug: string, photoId: number) {
    return jsonFetch<void>(`/listings/${slug}/photos/${photoId}/`, {
      method: "DELETE",
    });
  },
};

export const bookingsAPI = {
  create(payload: CreateBookingPayload) {
    return jsonFetch<Booking>("/bookings/", {
      method: "POST",
      body: payload,
    });
  },
  listMine() {
    return jsonFetch<Booking[]>("/bookings/my/", {
      method: "GET",
    });
  },
  confirm(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/confirm/`, {
      method: "POST",
    });
  },
  cancel(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/cancel/`, {
      method: "POST",
    });
  },
  complete(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/complete/`, {
      method: "POST",
    });
  },
};
