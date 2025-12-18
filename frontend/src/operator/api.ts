import { jsonFetch } from "@/lib/api";
import { AuthStore } from "@/lib/auth";
import type { ContactVerificationChannel } from "@/lib/api";

export type OperatorDashboardMetrics = {
  today: {
    new_users: number;
    new_listings: number;
    new_bookings_by_status: Record<string, number>;
    gmv_approx: number | string;
  };
  last_7d: {
    new_users: number;
    new_listings: number;
    new_bookings_by_status: Record<string, number>;
    gmv_approx: number | string;
  };
  risk: {
    overdue_bookings_count: number;
    disputed_bookings_count: number;
  };
  open_disputes_count: number;
  rebuttals_due_soon_count: number;
};

export type OperatorListingOwner = {
  id: number;
  email: string | null;
  name?: string | null;
  phone?: string | null;
  city?: string | null;
};

export type OperatorListingCategory = {
  id: number | null;
  name: string | null;
  slug: string | null;
};

export type OperatorListingListItem = {
  id: number;
  title: string;
  owner: OperatorListingOwner;
  city: string | null;
  category: OperatorListingCategory | null;
  daily_price_cad: string | number;
  is_active: boolean;
  needs_review?: boolean;
  thumbnail_url?: string | null;
  created_at: string;
};

export type OperatorListingDetail = OperatorListingListItem & {
  description: string;
  postal_code: string | null;
  is_available: boolean;
  replacement_value_cad: string | number;
  damage_deposit_cad: string | number;
  photos: { id: number; url: string; ordering: number }[];
};

export type OperatorBookingEvent = {
  id: number;
  type: string;
  payload: Record<string, unknown> | null;
  actor: OperatorListingOwner | null;
  created_at: string;
};

export type OperatorBookingListItem = {
  id: number;
  status: string;
  listing_id: number;
  listing_title: string;
  owner: OperatorListingOwner;
  renter: OperatorListingOwner;
  start_date: string;
  end_date: string;
  is_overdue: boolean;
  total_charge: string | number;
  created_at: string;
};

export type OperatorBookingDetail = OperatorBookingListItem & {
  is_disputed: boolean;
  dispute_window_expires_at: string | null;
  totals: Record<string, unknown>;
  charge_payment_intent_id: string | null;
  deposit_hold_id: string | null;
   deposit_locked?: boolean;
  events: OperatorBookingEvent[];
  disputes: { id: number; status: string; category: string; created_at: string }[];
  pickup_confirmed_at?: string | null;
  returned_by_renter_at?: string | null;
  return_confirmed_at?: string | null;
  after_photos_uploaded_at?: string | null;
};

export type OperatorListingListParams = Partial<{
  owner: number;
  city: string;
  category: string;
  is_active: boolean;
  needs_review: boolean;
  created_at_after: string;
  created_at_before: string;
}>;

export type OperatorBookingListParams = Partial<{
  status: string;
  created_at_after: string;
  created_at_before: string;
  owner: number | string;
  renter: number | string;
  overdue: boolean;
}>;

export type OperatorRiskFlag = {
  id?: number | null;
  level: string | null;
  category: string | null;
  note?: string | null;
  created_at?: string | null;
  created_by_id?: number | null;
  created_by_label?: string | null;
};

export type OperatorUserListItem = {
  id: number;
  email: string | null;
  phone: string | null;
  username: string;
  first_name: string;
  last_name: string;
  city: string | null;
  can_rent: boolean;
  can_list: boolean;
  is_active: boolean;
  date_joined: string;
  listings_count: number;
  bookings_as_renter_count: number;
  bookings_as_owner_count: number;
  disputes_count: number;
  active_risk_flag?: OperatorRiskFlag | null;
  email_verified?: boolean;
  phone_verified?: boolean;
  identity_verified?: boolean;
};

export type OperatorUserDetail = OperatorUserListItem & {
  street_address: string | null;
  province: string | null;
  postal_code: string | null;
  email_verified: boolean;
  phone_verified: boolean;
  identity_verified: boolean;
  last_login: string | null;
  last_login_ip: string | null;
  last_login_ua: string | null;
  bookings?: OperatorBookingSummary[];
  phone?: string | null;
};

export type OperatorUserListResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: OperatorUserListItem[];
};

export type OperatorBookingSummary = {
  id: number;
  status: string;
  listing_title: string;
  other_party: string | null;
  amount: string | number | null;
  end_date: string | null;
  role: "owner" | "renter";
};

export type OperatorNote = {
  id: number;
  entity_type: string;
  entity_id: string;
  text: string;
  tags: string[];
  author: { id: number; email: string | null; name: string | null } | null;
  created_at: string;
};

export type OperatorTransactionUser = {
  id: number;
  email: string | null;
  name?: string | null;
};

export type OperatorTransaction = {
  id: number;
  created_at: string;
  kind: string;
  amount: string | number;
  currency: string;
  stripe_id: string | null;
  booking_id: number | null;
  user: OperatorTransactionUser | null;
};

export type OperatorTransactionListResponse = {
  count: number;
  next: string | null;
  previous: string | null;
  results: OperatorTransaction[];
};

export type OperatorBookingFinance = {
  booking_id: number;
  stripe: {
    charge_payment_intent_id: string | null;
    deposit_hold_id: string | null;
  };
  ledger: OperatorTransaction[];
};

export type DbSettingValueType = "bool" | "int" | "decimal" | "str" | "json";

export type OperatorDbSetting = {
  id: number;
  key: string;
  value_type: DbSettingValueType;
  value_json: unknown;
  description: string;
  effective_at: string | null;
  updated_at: string;
  updated_by_id: number | null;
};

export type OperatorEffectiveSetting = {
  key: string;
  value_type: DbSettingValueType;
  value_json: unknown;
  description: string;
  effective_at: string | null;
  updated_at: string | null;
  updated_by_id: number | null;
  source: "db" | "default";
};

export type OperatorFeatureFlag = {
  id: number;
  key: string;
  enabled: boolean;
  updated_at: string;
  updated_by_id: number | null;
};

export type MaintenanceSeverity = "info" | "warning" | "error";

export type OperatorMaintenanceBanner = {
  id?: number;
  enabled: boolean;
  severity: MaintenanceSeverity;
  message: string;
  updated_at: string | null;
  updated_by_id: number | null;
};

export type OperatorHealthResponse = {
  ok: boolean;
  checks: Record<string, Record<string, unknown>>;
};

export type OperatorHealthResult = {
  status: number;
  latency_ms: number;
  data: OperatorHealthResponse | null;
};

export type OperatorJobStatus = "queued" | "running" | "succeeded" | "failed";

export type OperatorJobRun = {
  id: number;
  name: string;
  params: Record<string, unknown>;
  status: OperatorJobStatus;
  output_json: unknown | null;
  requested_by_id: number | null;
  created_at: string;
  finished_at: string | null;
};

type ReasonPayload = { reason: string };
type SuspiciousPayload = ReasonPayload & { level: string; category: string; note?: string | null };
type RestrictionsPayload = ReasonPayload & { can_rent?: boolean; can_list?: boolean };

export type OperatorUserListParams = Partial<{
  email: string;
  name: string;
  phone: string;
  city: string;
  can_rent: boolean;
  can_list: boolean;
  is_active: boolean;
  email_verified: boolean;
  phone_verified: boolean;
  identity_verified: boolean;
  ordering: "newest" | "most_bookings" | "most_disputes";
  page: number;
  page_size: number;
  date_joined_after: string;
  date_joined_before: string;
}>;

function buildQuery(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null) return;
    search.set(key, String(value));
  });
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const operatorAPI = {
  dashboard() {
    return jsonFetch<OperatorDashboardMetrics>("/operator/dashboard/", { method: "GET" });
  },
  settings() {
    return jsonFetch<OperatorDbSetting[]>("/operator/settings/", { method: "GET" });
  },
  settingsCurrent() {
    return jsonFetch<OperatorEffectiveSetting[]>("/operator/settings/current/", { method: "GET" });
  },
  putSetting(payload: {
    key: string;
    value_type: DbSettingValueType;
    value: unknown;
    description?: string;
    effective_at?: string | null;
    reason: string;
  }) {
    return jsonFetch<OperatorDbSetting>("/operator/settings/", { method: "PUT", body: payload });
  },
  featureFlags() {
    return jsonFetch<OperatorFeatureFlag[]>("/operator/feature-flags/", { method: "GET" });
  },
  putFeatureFlag(payload: { key: string; enabled: boolean; reason: string }) {
    return jsonFetch<OperatorFeatureFlag>("/operator/feature-flags/", { method: "PUT", body: payload });
  },
  maintenance() {
    return jsonFetch<OperatorMaintenanceBanner>("/operator/maintenance/", { method: "GET" });
  },
  putMaintenance(payload: { enabled: boolean; severity: MaintenanceSeverity; message?: string; reason: string }) {
    return jsonFetch<OperatorMaintenanceBanner>("/operator/maintenance/", { method: "PUT", body: payload });
  },
  async health(): Promise<OperatorHealthResult> {
    const token = AuthStore.getAccess();
    const started = Date.now();
    const resp = await fetch("/api/operator/health/", {
      method: "GET",
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        Accept: "application/json",
      },
    });
    const latency_ms = Date.now() - started;
    const text = await resp.text();
    const data = text ? (JSON.parse(text) as OperatorHealthResponse) : null;
    return { status: resp.status, latency_ms, data };
  },
  testEmail(payload: { to?: string }) {
    return jsonFetch<{ ok: boolean; to: string }>("/operator/health/test-email/", { method: "POST", body: payload });
  },
  jobRuns() {
    return jsonFetch<OperatorJobRun[]>("/operator/jobs/", { method: "GET" });
  },
  runJob(payload: { name: string; params?: Record<string, unknown>; reason: string }) {
    return jsonFetch<{ ok: boolean; job_run_id: number }>("/operator/jobs/run/", { method: "POST", body: payload });
  },
  users(params: OperatorUserListParams = {}) {
    const query = buildQuery({
      email: params.email,
      name: params.name,
      phone: params.phone,
      city: params.city,
      can_rent: params.can_rent,
      can_list: params.can_list,
      is_active: params.is_active,
      email_verified: params.email_verified,
      phone_verified: params.phone_verified,
      identity_verified: params.identity_verified,
      ordering: params.ordering,
      page: params.page,
      page_size: params.page_size,
      date_joined_after: params.date_joined_after,
      date_joined_before: params.date_joined_before,
    });
    return jsonFetch<OperatorUserListResponse>(`/operator/users/${query}`, { method: "GET" });
  },
  userDetail(userId: number) {
    return jsonFetch<OperatorUserDetail>(`/operator/users/${userId}/`, { method: "GET" });
  },
  suspendUser(userId: number, payload: ReasonPayload) {
    return jsonFetch<{ ok: boolean; user_id: number; is_active: boolean }>(
      `/operator/users/${userId}/suspend/`,
      { method: "POST", body: payload },
    );
  },
  reinstateUser(userId: number, payload: ReasonPayload) {
    return jsonFetch<{ ok: boolean; user_id: number; is_active: boolean }>(
      `/operator/users/${userId}/reinstate/`,
      { method: "POST", body: payload },
    );
  },
  setUserRestrictions(userId: number, payload: RestrictionsPayload) {
    return jsonFetch<{ ok: boolean; user_id: number; can_rent: boolean; can_list: boolean }>(
      `/operator/users/${userId}/set-restrictions/`,
      { method: "POST", body: payload },
    );
  },
  markUserSuspicious(userId: number, payload: SuspiciousPayload) {
    return jsonFetch<{ ok: boolean; risk_flag_id: number }>(
      `/operator/users/${userId}/mark-suspicious/`,
      { method: "POST", body: payload },
    );
  },
  sendPasswordReset(userId: number, payload: ReasonPayload) {
    return jsonFetch<{ ok: boolean; challenge_id?: number }>(
      `/operator/users/${userId}/send-password-reset/`,
      { method: "POST", body: payload },
    );
  },
  resendVerification(
    userId: number,
    payload: ReasonPayload & { channel: ContactVerificationChannel },
  ) {
    return jsonFetch<{ ok: boolean; challenge_id?: number; channel: ContactVerificationChannel }>(
      `/operator/users/${userId}/resend-verification/`,
      { method: "POST", body: payload },
    );
  },
  listNotes(entityType: string, entityId: string | number) {
    const query = buildQuery({ entity_type: entityType, entity_id: entityId });
    return jsonFetch<OperatorNote[]>(`/operator/notes/${query}`, { method: "GET" });
  },
  createNote(payload: {
    entity_type: string;
    entity_id: string | number;
    text: string;
    tags?: string[];
    reason: string;
  }) {
    return jsonFetch<OperatorNote>("/operator/notes/", { method: "POST", body: payload });
  },
  listings(params: OperatorListingListParams = {}) {
    const query = buildQuery(params as Record<string, string | number | boolean>);
    return jsonFetch<OperatorListingListItem[]>(`/operator/listings/${query}`, { method: "GET" });
  },
  listingDetail(listingId: number) {
    return jsonFetch<OperatorListingDetail>(`/operator/listings/${listingId}/`, { method: "GET" });
  },
  activateListing(listingId: number, payload: ReasonPayload) {
    return jsonFetch<{ ok: boolean; id: number; is_active: boolean }>(
      `/operator/listings/${listingId}/activate/`,
      { method: "POST", body: payload },
    );
  },
  deactivateListing(listingId: number, payload: ReasonPayload) {
    return jsonFetch<{ ok: boolean; id: number; is_active: boolean }>(
      `/operator/listings/${listingId}/deactivate/`,
      { method: "POST", body: payload },
    );
  },
  markListingNeedsReview(listingId: number, payload: ReasonPayload & { text: string }) {
    return jsonFetch<{ ok: boolean; id: number; note_id: number }>(
      `/operator/listings/${listingId}/mark-needs-review/`,
      { method: "POST", body: payload },
    );
  },
  emergencyEditListing(listingId: number, payload: ReasonPayload & { title?: string; description?: string }) {
    return jsonFetch<{ ok: boolean; id: number; updated_fields: string[] }>(
      `/operator/listings/${listingId}/emergency-edit/`,
      { method: "PATCH", body: payload },
    );
  },
  bookings(params: OperatorBookingListParams = {}) {
    const query = buildQuery(params as Record<string, string | number | boolean>);
    return jsonFetch<OperatorBookingListItem[]>(`/operator/bookings/${query}`, { method: "GET" });
  },
  bookingDetail(bookingId: number) {
    return jsonFetch<OperatorBookingDetail>(`/operator/bookings/${bookingId}/`, { method: "GET" });
  },
  forceCancelBooking(bookingId: number, payload: { actor: "system" | "owner" | "renter" | "no_show"; reason: string }) {
    return jsonFetch<{ ok: boolean; booking_id: number; status: string }>(
      `/operator/bookings/${bookingId}/force-cancel/`,
      { method: "POST", body: payload },
    );
  },
  forceCompleteBooking(bookingId: number, payload: { reason: string }) {
    return jsonFetch<{ ok: boolean; booking_id: number; status: string }>(
      `/operator/bookings/${bookingId}/force-complete/`,
      { method: "POST", body: payload },
    );
  },
  adjustBookingDates(bookingId: number, payload: { start_date: string; end_date: string; reason: string }) {
    return jsonFetch<{ ok: boolean; booking_id: number; status: string; start_date: string; end_date: string; totals: unknown }>(
      `/operator/bookings/${bookingId}/adjust-dates/`,
      { method: "POST", body: payload },
    );
  },
  resendBookingNotifications(bookingId: number, payload: { types: string[]; reason?: string }) {
    return jsonFetch<{ ok: boolean; booking_id: number; status: string; queued: string[]; failed?: string[] | null }>(
      `/operator/bookings/${bookingId}/resend-notifications/`,
      { method: "POST", body: payload },
    );
  },

  financeTransactions(
    params: Partial<{
      kind: string;
      booking: number | string;
      user: number | string;
      created_at_after: string;
      created_at_before: string;
    }> = {},
  ) {
    const query = buildQuery(params as Record<string, string | number>);
    return jsonFetch<OperatorTransactionListResponse | OperatorTransaction[]>(`/operator/transactions/${query}`, {
      method: "GET",
    });
  },

  bookingFinance(bookingId: number) {
    return jsonFetch<OperatorBookingFinance>(`/operator/bookings/${bookingId}/finance`, { method: "GET" });
  },

  refundBooking(
    bookingId: number,
    payload: { amount?: string | number; reason: string; notify_user?: boolean },
  ) {
    return jsonFetch<{ ok: boolean; booking_id: number; refund_id?: string | null; refunded_cents?: number | null }>(
      `/operator/bookings/${bookingId}/refund`,
      { method: "POST", body: payload },
    );
  },

  captureDeposit(bookingId: number, payload: { amount: string | number; reason: string }) {
    return jsonFetch<{ ok: boolean; booking_id: number; payment_intent_id?: string | null; captured_cents?: number | null }>(
      `/operator/bookings/${bookingId}/deposit/capture`,
      { method: "POST", body: payload },
    );
  },

  releaseDeposit(bookingId: number, payload: { reason: string }) {
    return jsonFetch<{ ok: boolean; booking_id: number; deposit_hold_id?: string | null }>(
      `/operator/bookings/${bookingId}/deposit/release`,
      { method: "POST", body: payload },
    );
  },

  async downloadPlatformRevenue(params: { from?: string; to?: string }) {
    const query = buildQuery(params as Record<string, string>);
    const token = AuthStore.getAccess();
    const res = await fetch(`/api/operator/exports/platform-revenue.csv${query}`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!res.ok) throw new Error("Unable to download platform revenue export");
    return res.blob();
  },

  async downloadOwnerLedger(params: { owner_id?: number | string; from?: string; to?: string }) {
    const query = buildQuery(params as Record<string, string | number>);
    const token = AuthStore.getAccess();
    const res = await fetch(`/api/operator/exports/owner-ledger.csv${query}`, {
      headers: {
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
    if (!res.ok) throw new Error("Unable to download owner ledger export");
    return res.blob();
  },
};

export function formatOperatorUserName(user: Pick<OperatorUserListItem, "first_name" | "last_name" | "username" | "email">) {
  const full = `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim();
  if (full) return full;
  if (user.username?.trim()) return user.username.trim();
  return user.email?.trim() || "User";
}
