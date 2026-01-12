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

export interface GoogleLoginPayload {
  id_token: string;
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

export type MaintenanceBanner = {
  enabled: boolean;
  severity: "info" | "warning" | "error";
  message: string;
  updated_at: string | null;
};

export type TokenResponse = AuthTokens | TwoFactorLoginStartResponse;

export type PlatformPricing = {
  currency: string;
  renter_fee_bps: number;
  renter_fee_rate: number;
  owner_fee_bps: number;
  owner_fee_rate: number;
  instant_payout_fee_bps: number;
  instant_payout_fee_rate: number;
};

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

export type IdentityVerificationStatus = "pending" | "verified" | "failed" | "canceled";

export interface IdentityStartResponse {
  session_id: string;
  client_secret: string | null;
  status: IdentityVerificationStatus | string;
  already_verified: boolean;
}

export interface IdentityStatusLatest {
  status: IdentityVerificationStatus | string;
  session_id: string;
  verified_at: string | null;
}

export interface IdentityStatusResponse {
  verified: boolean;
  latest: IdentityStatusLatest | null;
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
  identity_verified?: boolean;
}

export type ReviewRole = "owner_to_renter" | "renter_to_owner";

export interface Review {
  id: number;
  booking: number;
  author: number;
  subject: number;
  role: ReviewRole;
  rating: number | null;
  text: string;
  created_at: string;
}

export interface CreateReviewPayload {
  booking: number;
  role: ReviewRole;
  rating?: number | null;
  text?: string;
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
  is_promoted?: boolean;
}

export type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
  page?: number;
  page_size?: number;
  has_next?: boolean;
  has_previous?: boolean;
};

export interface ListingFeedItem {
  id: number;
  slug: string;
  title: string;
  daily_price_cad: string;
  city: string;
  category: string | null;
  category_name: string | null;
  is_promoted?: boolean;
  primary_photo_url?: string | null;
  owner_rating?: number | null;
  owner_review_count?: number;
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

export type ListingListResponse = PaginatedResponse<Listing>;
export type ListingFeedResponse = PaginatedResponse<ListingFeedItem>;

export interface ListingListParams {
  q?: string;
  category?: string;
  city?: string;
  price_min?: number;
  price_max?: number;
  page?: number;
  owner_id?: number;
  page_size?: number;
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

export interface PromotionPricingResponse {
  price_per_day_cents: number;
}

export interface PromotionAvailabilityRange {
  start_date: string;
  end_date: string;
}

export interface PromotionPaymentPayload {
  listing_id: number;
  promotion_start: string;
  promotion_end: string;
  base_price_cents: number;
  gst_cents: number;
  stripe_payment_method_id?: string;
  stripe_customer_id?: string;
  save_payment_method?: boolean;
  pay_with_earnings?: boolean;
  stripe_setup_intent_id?: string;
  setup_intent_status?: string;
  card_brand?: string;
  card_last4?: string;
  card_exp_month?: number;
  card_exp_year?: number;
}

export interface PromotionSlot {
  id: number;
  listing_id: number;
  starts_at: string;
  ends_at: string;
  price_per_day_cents: number;
  total_price_cents: number;
  duration_days: number;
  base_price_cents: number;
  gst_cents: number;
}

export interface PromotionPaymentResponse {
  slot: PromotionSlot;
}

export interface PaymentMethod {
  id: number;
  brand: string;
  last4: string;
  exp_month: number | null;
  exp_year: number | null;
  is_default: boolean;
  stripe_payment_method_id: string;
  created_at: string;
}

export type PaymentSetupIntentType = "default_card" | "promotion_card";

export interface PaymentMethodSetupIntentResponse {
  setup_intent_id: string;
  client_secret: string;
  status: string;
  intent_type: PaymentSetupIntentType;
}

export interface OwnerPayoutBalances {
  lifetime_gross_earnings: string;
  lifetime_refunds: string;
  lifetime_deposit_captured: string;
  lifetime_deposit_released: string;
  net_earnings: string;
  last_30_days_net: string;
  available_earnings: string;
  connect_available_earnings?: string | null;
}

export interface OwnerPayoutConnect {
  has_account: boolean;
  stripe_account_id: string | null;
  payouts_enabled: boolean;
  charges_enabled: boolean;
  is_fully_onboarded: boolean;
  business_type?: "individual" | "company";
  lifetime_instant_payouts: string;
  requirements_due: {
    currently_due: string[];
    eventually_due: string[];
    past_due: string[];
    disabled_reason: string | null;
  };
  kyc_steps: {
    personal_complete: boolean;
    id_required: boolean;
    id_submitted_pending: boolean;
    kyc_locked: boolean;
    personal_due?: string[];
    id_due?: string[];
  };
  bank_details: {
    transit_number: string;
    institution_number: string;
    account_last4: string;
  } | null;
}

export type OwnerPayoutOnboardingMode = "embedded" | "hosted_fallback";

export interface OwnerPayoutOnboardingResponse {
  client_secret: string | null;
  onboarding_url: string | null;
  mode: OwnerPayoutOnboardingMode;
  stripe_account_id: string | null;
  expires_at?: string | null;
}

export interface OwnerPayoutSummary {
  connect: OwnerPayoutConnect;
  balances: OwnerPayoutBalances;
}

export interface OwnerPayoutHistoryRow {
  id: number;
  created_at: string;
  kind: string;
  amount: string;
  currency: string;
  booking_id: number | null;
  booking_status: string | null;
  listing_title: string | null;
  direction: "credit" | "debit";
  stripe_id?: string | null;
}

export interface OwnerPayoutHistoryResponse {
  results: OwnerPayoutHistoryRow[];
  count: number;
  next_offset: number | null;
}

export interface InstantPayoutResponse {
  executed: boolean;
  currency: string;
  amount_before_fee: string;
  amount_after_fee: string;
  ok?: boolean;
  stripe_payout_id?: string;
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
  listing_owner_avatar_url?: string | null;
  listing_owner_identity_verified?: boolean;
  listing_primary_photo_url?: string | null;
  owner: number;
  renter: number;
  renter_first_name?: string | null;
  renter_last_name?: string | null;
  renter_username?: string;
  renter_avatar_url?: string | null;
  renter_identity_verified?: boolean;
  renter_rating?: number | null;
  totals: BookingTotals | null;
  charge_payment_intent_id?: string;
  deposit_hold_id: string;
  deposit_locked?: boolean;
  is_disputed?: boolean;
  dispute_window_expires_at?: string | null;
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
  renter_unpaid_bookings?: number;
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
  width?: number;
  height?: number;
  original_size?: number;
  compressed_size?: number;
}

export interface PhotoCompleteResponse {
  status: string;
  key: string;
}

export type DisputeCategory =
  | "damage"
  | "missing_item"
  | "not_as_described"
  | "late_return"
  | "incorrect_charges"
  | "safety_or_fraud";

export type DisputeDamageFlowKind = "generic" | "broke_during_use";

export type DisputeStatus =
  | "open"
  | "intake_missing_evidence"
  | "awaiting_rebuttal"
  | "under_review"
  | "resolved_renter"
  | "resolved_owner"
  | "resolved_partial"
  | "closed_auto";

export type DisputeRole = "renter" | "owner" | "admin" | "system";

export interface DisputeMessage {
  id: number;
  dispute: number;
  author: number | null;
  role: DisputeRole;
  text: string;
  created_at: string;
}

export interface DisputeEvidence {
  id: number;
  dispute: number;
  uploaded_by: number;
  kind: "photo" | "video" | "other";
  s3_key: string;
  url?: string | null;
  filename: string;
  content_type: string;
  size: number | null;
  etag: string;
  av_status: "pending" | "clean" | "infected" | "failed";
  created_at: string;
}

export interface DisputeUserSummary {
  id: number;
  name: string;
  avatar_url?: string | null;
  identity_verified?: boolean;
  rating?: number | null;
}

export interface DisputeCase {
  id: number;
  booking: number;
  opened_by?: number;
  opened_by_role: "renter" | "owner";
  category: DisputeCategory;
  damage_flow_kind: DisputeDamageFlowKind;
  description: string;
  status: DisputeStatus;
  filed_at?: string;
  rebuttal_due_at?: string | null;
  auto_rebuttal_timeout?: boolean;
  review_started_at?: string | null;
  resolved_at?: string | null;
  messages?: DisputeMessage[];
  evidence?: DisputeEvidence[];
  booking_start_date?: string | null;
  booking_end_date?: string | null;
  listing_title?: string | null;
  listing_primary_photo_url?: string | null;
  owner_summary?: DisputeUserSummary | null;
  renter_summary?: DisputeUserSummary | null;
}

export interface DisputeCreatePayload {
  booking: number;
  category: DisputeCategory;
  damage_flow_kind?: DisputeDamageFlowKind;
  description: string;
}

export interface DisputeEvidenceCompletePayload {
  key: string;
  filename: string;
  content_type: string;
  size: number;
  etag: string;
  kind: "photo" | "video" | "other";
  width?: number;
  height?: number;
  original_size?: number;
  compressed_size?: number;
}

export type DisputeEvidenceCompleteResponse = {
  status: string;
  key: string;
  id?: number;
};

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
  googleLogin(payload: GoogleLoginPayload) {
    return jsonFetch<TokenResponse>("/users/google/", {
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

export const maintenanceAPI = {
  banner() {
    return jsonFetch<MaintenanceBanner>("/maintenance/", { method: "GET" });
  },
};

export const platformAPI = {
  pricing() {
    return jsonFetch<PlatformPricing>("/platform/pricing/", { method: "GET" });
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
    if (params.page_size !== undefined) {
      search.set("page_size", String(params.page_size));
    }
    if (params.owner_id !== undefined) {
      search.set("owner_id", String(params.owner_id));
    }
    const query = search.toString();
    const path = `/listings/${query ? `?${query}` : ""}`;
    return jsonFetch<ListingListResponse>(path, { method: "GET" });
  },
  feed(params: ListingListParams = {}) {
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
    if (params.page_size !== undefined) {
      search.set("page_size", String(params.page_size));
    }
    if (params.owner_id !== undefined) {
      search.set("owner_id", String(params.owner_id));
    }
    const query = search.toString();
    const path = `/listings/feed/${query ? `?${query}` : ""}`;
    return jsonFetch<ListingFeedResponse>(path, { method: "GET" });
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
    if (params.page_size !== undefined) {
      search.set("page_size", String(params.page_size));
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
    payload: {
      stripe_payment_method_id: string;
      stripe_customer_id?: string;
      stripe_setup_intent_id?: string;
      setup_intent_status?: string;
      card_brand?: string;
      card_last4?: string;
      card_exp_month?: number;
      card_exp_year?: number;
    },
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
  renterReturn(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/renter-return/`, {
      method: "POST",
    });
  },
  ownerMarkReturned(id: number) {
    return jsonFetch<Booking>(`/bookings/${id}/owner-mark-returned/`, {
      method: "POST",
    });
  },
  afterPhotosPresign(id: number, payload: PhotoPresignRequest) {
    return jsonFetch<PhotoPresignResponse>(
      `/bookings/${id}/after-photos/presign/`,
      {
        method: "POST",
        body: payload,
      },
    );
  },
  afterPhotosComplete(id: number, payload: PhotoCompletePayload) {
    return jsonFetch<PhotoCompleteResponse>(
      `/bookings/${id}/after-photos/complete/`,
      {
        method: "POST",
        body: payload,
      },
    );
  },
};

export const disputesAPI = {
  list(params?: { bookingId?: number }) {
    const search = new URLSearchParams();
    if (params?.bookingId) {
      search.set("booking", String(params.bookingId));
    }
    const query = search.toString();
    const suffix = query ? `?${query}` : "";
    return jsonFetch<DisputeCase[]>(`/disputes/${suffix}`, { method: "GET" });
  },
  retrieve(disputeId: number) {
    return jsonFetch<DisputeCase>(`/disputes/${disputeId}/`, { method: "GET" });
  },
  create(payload: DisputeCreatePayload) {
    return jsonFetch<DisputeCase>("/disputes/", {
      method: "POST",
      body: payload,
    });
  },
  createMessage(disputeId: number, text: string) {
    return jsonFetch<DisputeMessage>(`/disputes/${disputeId}/messages/`, {
      method: "POST",
      body: { text },
    });
  },
  evidencePresign(disputeId: number, payload: PhotoPresignRequest) {
    return jsonFetch<PhotoPresignResponse>(`/disputes/${disputeId}/evidence/presign/`, {
      method: "POST",
      body: payload,
    });
  },
  evidenceComplete(disputeId: number, payload: DisputeEvidenceCompletePayload) {
    return jsonFetch<DisputeEvidenceCompleteResponse>(
      `/disputes/${disputeId}/evidence/complete/`,
      {
        method: "POST",
        body: payload,
      },
    );
  },
};

export const reviewsAPI = {
  create(payload: CreateReviewPayload) {
    return jsonFetch<Review>("/reviews/", {
      method: "POST",
      body: payload,
    });
  },
  list(params?: { booking?: number; subject?: number; role?: ReviewRole }) {
    const search = new URLSearchParams();
    if (params?.booking) search.set("booking", String(params.booking));
    if (params?.subject) search.set("subject", String(params.subject));
    if (params?.role) search.set("role", params.role);
    const query = search.toString();
    const path = `/reviews/${query ? `?${query}` : ""}`;
    return jsonFetch<Review[]>(path, { method: "GET" });
  },
  publicList(params: { listing?: number; role?: string } = {}) {
    const search = new URLSearchParams();
    if (params.listing !== undefined) search.set("listing", String(params.listing));
    if (params.role) search.set("role", params.role);
    const query = search.toString();
    return jsonFetch<any>(`/reviews/public/${query ? `?${query}` : ""}`, { method: "GET" });
  },
};

export const promotionsAPI = {
  fetchPromotionPricing(listingId: number) {
    const search = new URLSearchParams({ listing_id: String(listingId) }).toString();
    return jsonFetch<PromotionPricingResponse>(`/promotions/pricing/?${search}`, {
      method: "GET",
    });
  },
  availability(listingId: number) {
    const search = new URLSearchParams({ listing_id: String(listingId) }).toString();
    return jsonFetch<PromotionAvailabilityRange[]>(`/promotions/availability/?${search}`, {
      method: "GET",
    });
  },
  payPromotion(payload: PromotionPaymentPayload) {
    return jsonFetch<PromotionPaymentResponse>("/promotions/pay/", {
      method: "POST",
      body: payload,
    });
  },
};

export const paymentsAPI = {
  listPaymentMethods() {
    return jsonFetch<PaymentMethod[]>("/payments/methods/", { method: "GET" });
  },
  createPaymentMethodSetupIntent(payload: { intent_type?: PaymentSetupIntentType } = {}) {
    return jsonFetch<PaymentMethodSetupIntentResponse>("/payments/methods/setup-intent/", {
      method: "POST",
      body: payload,
    });
  },
  addPaymentMethod(payload: {
    stripe_payment_method_id: string;
    stripe_setup_intent_id?: string;
    setup_intent_status?: string;
    card_brand?: string;
    card_last4?: string;
    card_exp_month?: number | null;
    card_exp_year?: number | null;
  }) {
    return jsonFetch<PaymentMethod>("/payments/methods/", {
      method: "POST",
      body: payload,
    });
  },
  removePaymentMethod(id: number) {
    return jsonFetch<void>(`/payments/methods/${id}/`, {
      method: "DELETE",
    });
  },
  setDefaultPaymentMethod(id: number) {
    return jsonFetch<PaymentMethod>(`/payments/methods/${id}/set-default/`, {
      method: "POST",
      body: {},
    });
  },
  ownerPayoutsSummary() {
    return jsonFetch<OwnerPayoutSummary>("/owner/payouts/summary/", { method: "GET" });
  },
  ownerPayoutsSummaryRaw() {
    return jsonFetch<{ connect: OwnerPayoutConnect }>("/owner/payouts/summary/", {
      method: "GET",
    });
  },
  ownerPayoutsHistory(
    params: {
      kind?: string;
      limit?: number;
      offset?: number;
      scope?: "owner" | "all";
    } = {},
  ) {
    const search = new URLSearchParams();
    if (params.kind) search.set("kind", params.kind);
    if (params.limit !== undefined) search.set("limit", String(params.limit));
    if (params.offset !== undefined) search.set("offset", String(params.offset));
    if (params.scope) {
      search.set("scope", params.scope);
    }
    const query = search.toString();
    const path = `/owner/payouts/history/${query ? `?${query}` : ""}`;
    return jsonFetch<OwnerPayoutHistoryResponse>(path, { method: "GET" });
  },
  updateBankDetails(payload: {
    transit_number: string;
    institution_number: string;
    account_number: string;
  }) {
    return jsonFetch<OwnerPayoutSummary>("/owner/payouts/bank-details/", {
      method: "POST",
      body: payload,
    });
  },
  instantPayoutPreview() {
    return jsonFetch<InstantPayoutResponse>("/owner/payouts/instant-payout/", {
      method: "POST",
      body: {},
    });
  },
  instantPayoutExecute() {
    return jsonFetch<InstantPayoutResponse>("/owner/payouts/instant-payout/", {
      method: "POST",
      body: { confirm: true },
    });
  },
  ownerPayoutsStartOnboarding(payload?: { business_type?: "individual" | "company" }) {
    return jsonFetch<OwnerPayoutOnboardingResponse>("/owner/payouts/start-onboarding/", {
      method: "POST",
      body: payload ?? {},
    });
  },
};

export const identityAPI = {
  start() {
    return jsonFetch<IdentityStartResponse>("/identity/start/", {
      method: "POST",
    });
  },
  status() {
    return jsonFetch<IdentityStatusResponse>("/identity/status/", {
      method: "GET",
    });
  },
};
