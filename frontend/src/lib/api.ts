import { AuthStore, type AuthTokens, type Profile } from "./auth";
import { parseMoney } from "./utils";

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

export interface PublicProfile {
  id: number;
  username: string;
  first_name: string;
  last_name: string;
  city: string | null;
  avatar_url?: string | null;
  avatar_uploaded?: boolean;
  date_joined?: string;
  rating?: number | null;
  review_count?: number | null;
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
  owner_id?: number;
}

export interface ListingGeocodeParams {
  postalCode: string;
  city?: string;
  region?: string;
}

export interface ListingGeocodeResponse {
  location: {
    lat: number;
    lng: number;
  };
  formatted_address: string;
  address: {
    postal_code: string;
    city?: string | null;
    region?: string | null;
  };
  cache_hit: boolean;
}

export type BookingStatus = "requested" | "confirmed" | "paid" | "canceled" | "completed";

export interface BookingTotals {
  days?: string;
  daily_price_cad?: string;
  rental_subtotal?: string;
  renter_fee?: string;
  owner_fee?: string;
  platform_fee_total?: string;
  owner_payout?: string;
  damage_deposit?: string;
  total_charge?: string;
  service_fee?: string; // deprecated alias, keep for backwards compatibility
}

export interface Booking {
  id: number;
  status: BookingStatus;
  status_label?: string | null;
  start_date: string;
  end_date: string;
  listing: number;
  listing_title: string;
  listing_slug?: string | null;
  listing_owner_first_name?: string | null;
  listing_owner_last_name?: string | null;
  listing_owner_username?: string | null;
  listing_primary_photo_url?: string | null;
  owner: number;
  renter: number;
  renter_first_name?: string | null;
  renter_last_name?: string | null;
  renter_username?: string;
  renter_avatar_url?: string | null;
  renter_rating?: number | null;
  totals: BookingTotals | null;
  charge_payment_intent_id?: string;
  deposit_hold_id: string;
  pickup_confirmed_at?: string | null;
  before_photos_required?: boolean | null;
  before_photos_uploaded_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BookingAvailabilityRange {
  start_date: string;
  end_date: string;
}

export interface PendingRequestsCountResponse {
  pending_requests: number;
  unpaid_bookings: number;
}

export type RentalDirection = "earned" | "spent";

export function deriveRentalDirection(currentUserId: number, booking: Booking): RentalDirection {
  return booking.owner === currentUserId ? "earned" : "spent";
}

type BookingTotalsSource = Pick<Booking, "totals"> | BookingTotals | null | undefined;

function resolveTotals(source: BookingTotalsSource): BookingTotals | null {
  if (!source) {
    return null;
  }
  if (typeof source === "object" && source !== null && "totals" in source) {
    return (source as Pick<Booking, "totals">).totals ?? null;
  }
  return source as BookingTotals;
}

const toAmount = (value: unknown): number => parseMoney(value ?? 0);

export function getBookingChargeAmount(source: BookingTotalsSource): number {
  const totals = resolveTotals(source);
  if (!totals) {
    return 0;
  }
  const rentalSubtotal = toAmount(totals.rental_subtotal ?? totals.daily_price_cad ?? 0);
  const serviceFee = toAmount(totals.service_fee ?? totals.renter_fee ?? 0);
  if (rentalSubtotal || serviceFee) {
    return rentalSubtotal + serviceFee;
  }
  const totalCharge = toAmount(totals.total_charge ?? 0);
  const damageDeposit = toAmount(totals.damage_deposit ?? 0);
  if (totalCharge) {
    return Math.max(totalCharge - damageDeposit, 0);
  }
  return 0;
}

export function getBookingDamageDeposit(source: BookingTotalsSource): number {
  const totals = resolveTotals(source);
  return totals ? toAmount(totals.damage_deposit ?? 0) : 0;
}

export function getOwnerPayoutAmount(source: BookingTotalsSource): number {
  const totals = resolveTotals(source);
  if (!totals) {
    return 0;
  }
  const fallback = toAmount(totals.rental_subtotal ?? totals.total_charge ?? 0);
  const payout = toAmount(totals.owner_payout ?? fallback);
  return payout || fallback;
}

export function deriveRentalAmounts(direction: RentalDirection, booking: Booking): number {
  return direction === "earned"
    ? getOwnerPayoutAmount(booking)
    : getBookingChargeAmount(booking);
}

export type DisplayRentalStatus =
  | "Requested"
  | "Waiting approval"
  | "Pending"
  | "Awaiting payment"
  | "In progress"
  | "Waiting pick up"
  | "Awaiting pickup"
  | "Completed"
  | "Canceled"
  | "Cancelled";

const DISPLAY_STATUS_VALUES: DisplayRentalStatus[] = [
  "Requested",
  "Waiting approval",
  "Pending",
  "Awaiting payment",
  "In progress",
  "Waiting pick up",
  "Awaiting pickup",
  "Completed",
  "Canceled",
  "Cancelled",
];

function normalizeDisplayStatus(label?: string | null): DisplayRentalStatus | null {
  if (!label) return null;
  const trimmed = label.trim();
  return DISPLAY_STATUS_VALUES.includes(trimmed as DisplayRentalStatus)
    ? (trimmed as DisplayRentalStatus)
    : null;
}

export function deriveDisplayRentalStatus(booking: Booking): DisplayRentalStatus {
  const labelStatus = normalizeDisplayStatus(booking.status_label);
  if (labelStatus) {
    return labelStatus;
  }

  const normalizedStatus = (booking.status || "").toLowerCase();
  switch (normalizedStatus) {
    case "requested":
      return "Waiting approval";
    case "confirmed":
      return "Awaiting payment";
    case "paid":
      return booking.pickup_confirmed_at ? "In progress" : "Awaiting pickup";
    case "completed":
      return "Completed";
    case "canceled":
      return "Canceled";
    default:
      return "Waiting approval";
  }
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
> & { phone?: string | null; avatar?: null };

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
  async uploadAvatar(file: File) {
    const formData = new FormData();
    formData.append("avatar", file);
    const token = AuthStore.getAccess();
    const headers = new Headers();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const response = await fetch(`${API_BASE}/users/me/`, {
      method: "PATCH",
      headers,
      body: formData,
    });
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;
    if (!response.ok) {
      const error: JsonError = { status: response.status, data };
      throw error;
    }
    return data as Profile;
  },
  deleteAvatar() {
    return jsonFetch<Profile>("/users/me/", {
      method: "PATCH",
      body: { avatar: null },
    });
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

export const usersAPI = {
  publicProfile(userId: number) {
    return jsonFetch<PublicProfile>(`/users/public/${userId}/`, {
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
    if (params.owner_id !== undefined) {
      search.set("owner_id", String(params.owner_id));
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
  geocodeLocation(params: ListingGeocodeParams, options?: { signal?: AbortSignal }) {
    const postalCode = params.postalCode?.trim();
    if (!postalCode) {
      throw new Error("postalCode is required");
    }
    const search = new URLSearchParams();
    search.set("postal_code", postalCode);
    if (params.city) {
      search.set("city", params.city);
    }
    if (params.region) {
      search.set("region", params.region);
    }
    const query = search.toString();
    return jsonFetch<ListingGeocodeResponse>(`/listings/geocode/?${query}`, {
      method: "GET",
      signal: options?.signal,
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
  availability(listingId: number) {
    const search = new URLSearchParams({ listing: String(listingId) }).toString();
    return jsonFetch<BookingAvailabilityRange[]>(`/bookings/availability/?${search}`, {
      method: "GET",
    });
  },
  confirm(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/confirm/`, {
      method: "POST",
    });
  },
  pay(
    id: number,
    payload: { stripe_payment_method_id: string; stripe_customer_id?: string },
  ) {
    return jsonFetch<Booking>(`/bookings/${id}/pay/`, {
      method: "POST",
      body: payload,
    });
  },
  cancel(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/cancel/`, {
      method: "POST",
    });
  },
  pendingRequestsCount() {
    return jsonFetch<PendingRequestsCountResponse>("/bookings/pending-requests-count/", {
      method: "GET",
    });
  },
  complete(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/complete/`, {
      method: "POST",
    });
  },
  beforePhotosPresign(id: number, payload: PhotoPresignRequest) {
    return jsonFetch<PhotoPresignResponse>(
      `/bookings/${id}/before-photos/presign/`,
      {
        method: "POST",
        body: payload,
      },
    );
  },
  beforePhotosComplete(id: number, payload: PhotoCompletePayload) {
    return jsonFetch<PhotoCompleteResponse>(
      `/bookings/${id}/before-photos/complete/`,
      {
        method: "POST",
        body: payload,
      },
    );
  },
  confirmPickup(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/confirm-pickup/`, {
      method: "POST",
    });
  },
};
