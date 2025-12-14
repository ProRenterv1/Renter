import { jsonFetch } from "@/lib/api";
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
};

export function formatOperatorUserName(user: Pick<OperatorUserListItem, "first_name" | "last_name" | "username" | "email">) {
  const full = `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim();
  if (full) return full;
  if (user.username?.trim()) return user.username.trim();
  return user.email?.trim() || "User";
}
