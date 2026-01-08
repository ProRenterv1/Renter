import { jsonFetch } from "@/lib/api";
import { AuthStore } from "@/lib/auth";
import type { ContactVerificationChannel } from "@/lib/api";
import { parseMoney } from "@/lib/utils";

export type OperatorDashboardOverdueItem = {
  booking_id: number;
  listing_id?: number | null;
  listing_title?: string | null;
  renter_name?: string | null;
  renter_email?: string | null;
  end_date?: string | null;
  overdue_days?: number;
};

export type OperatorDashboardDisputedItem = {
  dispute_id: number;
  booking_id: number;
  filed_at?: string | null;
};

export type OperatorDashboardFailedPaymentItem = {
  booking_id: number;
  renter_name?: string | null;
  renter_email?: string | null;
  amount?: number | string | null;
  created_at?: string | null;
};

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
    failed_payments_count?: number;
  };
  risk_items?: {
    overdue_bookings: OperatorDashboardOverdueItem[];
    disputed_bookings: OperatorDashboardDisputedItem[];
    failed_payments: OperatorDashboardFailedPaymentItem[];
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
  pickup_confirmed_at?: string | null;
  returned_by_renter_at?: string | null;
  return_confirmed_at?: string | null;
  after_photos_uploaded_at?: string | null;
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

export type OperatorDisputeListItem = {
  id: number;
  booking_id: number;
  listing_title: string | null;
  listing_id?: number | null;
  opened_by: string;
  opened_by_label?: string | null;
  opened_by_role?: "owner" | "renter";
  category: string;
  flow: string;
  stage: string;
  status: string;
  filed_at: string;
  evidence_due_at?: string | null;
  rebuttal_due_at?: string | null;
  evidence_missing?: boolean;
  rebuttal_overdue?: boolean;
  flags?: string[];
  safety_flag?: boolean;
  suspend_flag?: boolean;
  owner_email?: string | null;
  renter_email?: string | null;
};

export type OperatorDisputeEvidenceItem = {
  id: number;
  url: string | null;
  thumbnail_url?: string | null;
  filename?: string | null;
  label?: string | null;
  av_status?: string | null;
  uploaded_at?: string | null;
};

export type OperatorDisputeMessage = {
  id: number;
  author_role: "owner" | "renter" | "operator" | "system";
  author_label?: string | null;
  body: string;
  created_at: string;
};

export type OperatorDisputeTimelineItem = {
  id: number | string;
  type: string;
  label: string;
  description?: string | null;
  actor_label?: string | null;
  created_at: string;
};

export type OperatorDisputeBookingContext = {
  id: number;
  listing_title?: string | null;
  owner_email?: string | null;
  renter_email?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  deposit_locked?: boolean;
  deposit_hold_id?: string | null;
  deposit_status?: string | null;
  chat_url?: string | null;
  chat_thread_id?: string | number | null;
  totals?: {
    subtotal_cents?: number | null;
    service_fee_cents?: number | null;
    taxes_cents?: number | null;
    total_cents?: number | null;
    deposit_hold_cents?: number | null;
  };
};

export type OperatorDisputeResolution = {
  refund_cents?: number | null;
  capture_cents?: number | null;
  resolved_at?: string | null;
  resolved_by?: string | null;
  note?: string | null;
};

export type OperatorDisputeDetail = OperatorDisputeListItem & {
  evidence: {
    before_photos: OperatorDisputeEvidenceItem[];
    after_photos: OperatorDisputeEvidenceItem[];
    dispute_uploads: OperatorDisputeEvidenceItem[];
  };
  messages: OperatorDisputeMessage[];
  timeline: OperatorDisputeTimelineItem[];
  booking: OperatorDisputeBookingContext | null;
  resolution?: OperatorDisputeResolution | null;
};

export type OperatorDisputeEvidenceRequestPayload = {
  target: "owner" | "renter" | "both";
  template_key?: string;
  message: string;
  due_at: string;
  notify_email: boolean;
  notify_sms: boolean;
};

export type OperatorDisputeClosePayload = {
  reason: "late" | "duplicate" | "no_evidence";
  notes: string;
};

export type OperatorDisputeResolvePayload = {
  decision: "renter" | "owner" | "partial" | "deny";
  refund_amount: number;
  deposit_capture_amount: number;
  reason?: string;
  opened_by_role?: "owner" | "renter";
  suspend_listing?: boolean;
  mark_renter_suspicious?: boolean;
  mark_owner_suspicious?: boolean;
  notes: string;
};

export type OperatorDisputeAppealPayload = {
  reason: string;
  new_evidence_uploaded?: boolean;
  due_at?: string;
};

export type OperatorDisputeActionResponse = {
  ok: boolean;
};

export type OperatorCommsParticipant = {
  user_id: number | null;
  name: string;
  email?: string | null;
  avatar_url?: string | null;
};

export type OperatorCommsConversationListItem = {
  id: number;
  booking_id: number | null;
  listing_id: number | null;
  listing_title: string;
  participants: OperatorCommsParticipant[];
  status: string;
  unread_count: number;
  last_message_at: string | null;
  created_at: string;
};

export type OperatorCommsMessage = {
  id: number;
  sender_id: number | null;
  sender_name: string;
  message_type: "user" | "system";
  system_kind?: string | null;
  text: string;
  created_at: string;
};

export type OperatorCommsNotification = {
  id: number;
  type: string;
  channel: "email" | "sms";
  status: "sent" | "failed";
  created_at: string;
  user_id: number | null;
  user_name: string;
};

export type OperatorCommsConversationDetail = OperatorCommsConversationListItem & {
  messages: OperatorCommsMessage[];
  notifications: OperatorCommsNotification[];
};

export type OperatorPromotionListItem = {
  id: number;
  listing: number;
  listing_title?: string | null;
  owner: number;
  owner_name?: string | null;
  owner_email?: string | null;
  placement?: string | null;
  price_per_day_cents?: number | null;
  base_price_cents?: number | null;
  gst_cents?: number | null;
  total_price_cents?: number | null;
  starts_at?: string | null;
  ends_at?: string | null;
  active: boolean;
  stripe_session_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
};

export type OperatorPromotionListParams = Partial<{
  active: boolean;
  owner_id: number | string;
  listing_id: number | string;
}>;

export type OperatorPromotionGrantPayload = {
  listing_id: number;
  starts_at: string;
  ends_at: string;
  reason: string;
  placement?: string;
  comped?: boolean;
};

export type OperatorPromotionCancelPayload = {
  reason: string;
  note?: string;
};

export type OperatorAuditActor = {
  id: number;
  name?: string | null;
  email?: string | null;
};

export type OperatorAuditEvent = {
  id: number;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string;
  before_json?: unknown;
  after_json?: unknown;
  meta_json?: unknown;
  ip?: string | null;
  user_agent?: string | null;
  created_at: string;
  actor?: OperatorAuditActor | null;
};

export type OperatorAuditLogParams = Partial<{
  actor_id: number | string;
  actor: string;
  entity_type: string;
  action: string;
  created_at_after: string;
  created_at_before: string;
  page: number;
  page_size: number;
}>;

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

export type OperatorDisputeListParams = Partial<{
  status: string;
  category: string;
  flow: string;
  stage: string;
  evidence_missing: boolean;
  rebuttal_overdue: boolean;
  safety_flag: boolean;
  owner_email: string;
  renter_email: string;
  booking_id: number | string;
  page: number;
  page_size: number;
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
  updated_by_name: string | null;
};

export type OperatorEffectiveSetting = {
  key: string;
  value_type: DbSettingValueType;
  value_json: unknown;
  description: string;
  effective_at: string | null;
  updated_at: string | null;
  updated_by_id: number | null;
  updated_by_name: string | null;
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
  id: number;
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

const mockDisputesEnabled = import.meta.env.VITE_OPS_MOCK_DISPUTES === "1";

const MOCK_DISPUTES: OperatorDisputeListItem[] = buildMockDisputes();
const MOCK_IMAGE_DATA =
  "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480' viewBox='0 0 640 480'><rect width='640' height='480' fill='%23e9e5e2'/><rect x='60' y='80' width='520' height='320' rx='24' fill='%23d8dee3'/><rect x='90' y='320' width='220' height='24' rx='12' fill='%23b7c2cb'/><circle cx='420' cy='200' r='52' fill='%23c7d1d8'/><circle cx='500' cy='250' r='36' fill='%23c7d1d8'/></svg>";

function buildMockDisputes(): OperatorDisputeListItem[] {
  const now = Date.now();
  return [
    {
      id: 2401,
      booking_id: 9012,
      listing_title: "Makita Impact Driver Kit",
      listing_id: 551,
      opened_by: "renter",
      opened_by_label: "renter@maple.tools",
      category: "damage",
      flow: "standard",
      stage: "intake",
      status: "open",
      filed_at: new Date(now - 4 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: new Date(now + 2 * 24 * 60 * 60 * 1000).toISOString(),
      rebuttal_due_at: null,
      evidence_missing: true,
      flags: [],
      owner_email: "owner@maple.tools",
      renter_email: "renter@maple.tools",
    },
    {
      id: 2402,
      booking_id: 9027,
      listing_title: "Stihl Chainsaw MS 271",
      listing_id: 612,
      opened_by: "owner",
      opened_by_label: "owner@pineworks.ca",
      category: "late_return",
      flow: "standard",
      stage: "awaiting_rebuttal",
      status: "open",
      filed_at: new Date(now - 6 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: null,
      rebuttal_due_at: new Date(now + 6 * 60 * 60 * 1000).toISOString(),
      evidence_missing: false,
      flags: ["safety"],
      safety_flag: true,
      owner_email: "owner@pineworks.ca",
      renter_email: "renter@coastal.io",
    },
    {
      id: 2403,
      booking_id: 9054,
      listing_title: "DeWalt Tile Saw",
      listing_id: 779,
      opened_by: "renter",
      opened_by_label: "renter@cedarline.com",
      category: "missing_item",
      flow: "standard",
      stage: "under_review",
      status: "pending_review",
      filed_at: new Date(now - 9 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
      rebuttal_due_at: new Date(now - 1 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_missing: false,
      rebuttal_overdue: true,
      flags: ["suspend"],
      suspend_flag: true,
      owner_email: "owner@cedarline.com",
      renter_email: "renter@cedarline.com",
    },
    {
      id: 2404,
      booking_id: 9078,
      listing_title: "Toro Snow Blower",
      listing_id: 810,
      opened_by: "owner",
      opened_by_label: "owner@northern.yards",
      category: "safety",
      flow: "safety",
      stage: "intake",
      status: "open",
      filed_at: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: new Date(now + 10 * 60 * 60 * 1000).toISOString(),
      rebuttal_due_at: null,
      evidence_missing: true,
      flags: ["safety", "suspend"],
      safety_flag: true,
      suspend_flag: true,
      owner_email: "owner@northern.yards",
      renter_email: "renter@northbay.ca",
    },
    {
      id: 2405,
      booking_id: 9091,
      listing_title: "Milwaukee Hammer Drill",
      listing_id: 430,
      opened_by: "system",
      opened_by_label: "System",
      category: "fraud",
      flow: "fraud",
      stage: "under_review",
      status: "pending_review",
      filed_at: new Date(now - 12 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: null,
      rebuttal_due_at: new Date(now + 2 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_missing: false,
      flags: ["safety"],
      safety_flag: true,
      owner_email: "owner@ridgecrew.ca",
      renter_email: "renter@ridgecrew.ca",
    },
    {
      id: 2406,
      booking_id: 9103,
      listing_title: "Bosch Laser Level",
      listing_id: 982,
      opened_by: "renter",
      opened_by_label: "renter@graniteworks.io",
      category: "service",
      flow: "standard",
      stage: "resolved",
      status: "closed",
      filed_at: new Date(now - 20 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: null,
      rebuttal_due_at: null,
      evidence_missing: false,
      flags: [],
      owner_email: "owner@graniteworks.io",
      renter_email: "renter@graniteworks.io",
    },
    {
      id: 2407,
      booking_id: 9118,
      listing_title: "Honda Generator EU2200i",
      listing_id: 674,
      opened_by: "owner",
      opened_by_label: "owner@trailcraft.ca",
      category: "damage",
      flow: "standard",
      stage: "awaiting_rebuttal",
      status: "open",
      filed_at: new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: null,
      rebuttal_due_at: new Date(now - 4 * 60 * 60 * 1000).toISOString(),
      evidence_missing: false,
      rebuttal_overdue: true,
      flags: [],
      owner_email: "owner@trailcraft.ca",
      renter_email: "renter@trailcraft.ca",
    },
    {
      id: 2408,
      booking_id: 9130,
      listing_title: "Ryobi Pressure Washer",
      listing_id: 540,
      opened_by: "renter",
      opened_by_label: "renter@riverbend.co",
      category: "other",
      flow: "standard",
      stage: "resolved",
      status: "resolved",
      filed_at: new Date(now - 15 * 24 * 60 * 60 * 1000).toISOString(),
      evidence_due_at: null,
      rebuttal_due_at: null,
      evidence_missing: false,
      flags: [],
      owner_email: "owner@riverbend.co",
      renter_email: "renter@riverbend.co",
    },
  ];
}

function mockDisputesList(params: OperatorDisputeListParams) {
  const now = Date.now();
  const filtered = MOCK_DISPUTES.filter((dispute) => {
    if (params.status && dispute.status !== params.status) return false;
    if (params.category && dispute.category !== params.category) return false;
    if (params.flow && dispute.flow !== params.flow) return false;
    if (params.stage && dispute.stage !== params.stage) return false;
    if (params.evidence_missing && !dispute.evidence_missing) return false;
    if (params.safety_flag && !(dispute.safety_flag || dispute.flags?.includes("safety"))) return false;
    if (params.rebuttal_overdue) {
      const rebuttalDue = dispute.rebuttal_due_at ? new Date(dispute.rebuttal_due_at).getTime() : null;
      const overdue = dispute.rebuttal_overdue ?? (rebuttalDue !== null && rebuttalDue < now);
      if (!overdue) return false;
    }
    if (params.owner_email) {
      const ownerEmail = dispute.owner_email?.toLowerCase() ?? "";
      if (!ownerEmail.includes(params.owner_email.toLowerCase())) return false;
    }
    if (params.renter_email) {
      const renterEmail = dispute.renter_email?.toLowerCase() ?? "";
      if (!renterEmail.includes(params.renter_email.toLowerCase())) return false;
    }
    if (params.booking_id) {
      const bookingId = String(dispute.booking_id);
      if (!bookingId.includes(String(params.booking_id))) return false;
    }
    return true;
  });

  return Promise.resolve(filtered);
}

function mockDisputeDetail(disputeId: number) {
  const detail = buildMockDisputeDetail(disputeId);
  if (!detail) {
    return Promise.reject({ status: 404, data: { detail: "Dispute not found." } });
  }
  return Promise.resolve(normalizeOperatorDisputeDetail(detail));
}

function mockDisputeAction() {
  return Promise.resolve({ ok: true } as OperatorDisputeActionResponse);
}

function buildMockDisputeDetail(disputeId: number): OperatorDisputeDetail | null {
  const base = MOCK_DISPUTES.find((item) => item.id === disputeId);
  if (!base) return null;

  const now = Date.now();
  const filedAt = base.filed_at;
  const evidenceDueAt = base.evidence_due_at ?? new Date(now + 24 * 60 * 60 * 1000).toISOString();
  const rebuttalDueAt = base.rebuttal_due_at ?? new Date(now + 48 * 60 * 60 * 1000).toISOString();

  const evidenceItems: OperatorDisputeEvidenceItem[] = [
    {
      id: disputeId * 10 + 1,
      url: MOCK_IMAGE_DATA,
      thumbnail_url: MOCK_IMAGE_DATA,
      label: "Pickup photo 1",
      av_status: "clean",
      uploaded_at: new Date(now - 5 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: disputeId * 10 + 2,
      url: MOCK_IMAGE_DATA,
      thumbnail_url: MOCK_IMAGE_DATA,
      label: "Pickup photo 2",
      av_status: "pending",
      uploaded_at: new Date(now - 5 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ];

  const afterItems: OperatorDisputeEvidenceItem[] = [
    {
      id: disputeId * 10 + 3,
      url: MOCK_IMAGE_DATA,
      thumbnail_url: MOCK_IMAGE_DATA,
      label: "Return photo 1",
      av_status: "clean",
      uploaded_at: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ];

  const disputeUploads: OperatorDisputeEvidenceItem[] = [
    {
      id: disputeId * 10 + 4,
      url: MOCK_IMAGE_DATA,
      thumbnail_url: MOCK_IMAGE_DATA,
      label: "Damage close-up",
      av_status: "blocked",
      uploaded_at: new Date(now - 1 * 24 * 60 * 60 * 1000).toISOString(),
    },
  ];

  const messages: OperatorDisputeMessage[] = [
    {
      id: disputeId * 100 + 1,
      author_role: "system",
      author_label: "System",
      body: `Dispute opened by ${base.opened_by}.`,
      created_at: filedAt,
    },
    {
      id: disputeId * 100 + 2,
      author_role: "owner",
      author_label: base.owner_email || "Owner",
      body: "Tool returned with visible cracks on casing. Photos attached.",
      created_at: new Date(now - 3 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: disputeId * 100 + 3,
      author_role: "renter",
      author_label: base.renter_email || "Renter",
      body: "No damage when returned. I have my own pickup photos.",
      created_at: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: disputeId * 100 + 4,
      author_role: "operator",
      author_label: "Ops",
      body: "Reviewing evidence and AV status results.",
      created_at: new Date(now - 12 * 60 * 60 * 1000).toISOString(),
    },
  ];

  const timeline: OperatorDisputeTimelineItem[] = [
    {
      id: `${disputeId}-opened`,
      type: "stage_change",
      label: "Dispute opened",
      description: `${formatLabel(base.category)} • ${formatLabel(base.flow)}`,
      actor_label: base.opened_by_label || formatLabel(base.opened_by),
      created_at: filedAt,
    },
    {
      id: `${disputeId}-evidence`,
      type: "reminder_sent",
      label: "Evidence reminder sent",
      description: `Evidence due ${formatDateTime(evidenceDueAt)}`,
      actor_label: "System",
      created_at: new Date(now - 36 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: `${disputeId}-rebuttal`,
      type: "reminder_sent",
      label: "Rebuttal reminder sent",
      description: `Rebuttal due ${formatDateTime(rebuttalDueAt)}`,
      actor_label: "System",
      created_at: new Date(now - 12 * 60 * 60 * 1000).toISOString(),
    },
    {
      id: `${disputeId}-review`,
      type: "operator_action",
      label: "Operator review started",
      description: "Evidence and booking context pulled into review queue.",
      actor_label: "Ops",
      created_at: new Date(now - 2 * 60 * 60 * 1000).toISOString(),
    },
  ];

  const booking: OperatorDisputeBookingContext = {
    id: base.booking_id,
    listing_title: base.listing_title,
    owner_email: base.owner_email ?? null,
    renter_email: base.renter_email ?? null,
    start_date: new Date(now - 10 * 24 * 60 * 60 * 1000).toISOString(),
    end_date: new Date(now - 6 * 24 * 60 * 60 * 1000).toISOString(),
    deposit_locked: base.stage !== "resolved",
    deposit_hold_id: base.stage !== "resolved" ? `dep_${base.booking_id}` : null,
    deposit_status: base.stage !== "resolved" ? "held" : "released",
    chat_thread_id: `booking-${base.booking_id}`,
    totals: {
      subtotal_cents: 18500,
      service_fee_cents: 1480,
      taxes_cents: 1200,
      total_cents: 21180,
      deposit_hold_cents: 5000,
    },
  };

  const resolution: OperatorDisputeResolution | null =
    base.stage === "resolved"
      ? {
          refund_cents: 2500,
          capture_cents: 0,
          resolved_at: new Date(now - 2 * 24 * 60 * 60 * 1000).toISOString(),
          resolved_by: "Ops",
          note: "Refunded partial deposit after review.",
        }
      : null;

  return {
    ...base,
    evidence: {
      before_photos: evidenceItems,
      after_photos: afterItems,
      dispute_uploads: disputeUploads,
    },
    messages,
    timeline,
    booking,
    resolution,
  };
}

function formatLabel(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
}

function formatDateTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
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
  disputesList(params: OperatorDisputeListParams = {}) {
    if (mockDisputesEnabled) {
      return mockDisputesList(params);
    }
    const query = buildQuery(params as Record<string, string | number | boolean>);
    return jsonFetch<OperatorDisputeListItem[] | { results: OperatorDisputeListItem[] }>(
      `/operator/disputes/${query}`,
      { method: "GET" },
    );
  },
  disputeDetail(disputeId: number) {
    if (mockDisputesEnabled) {
      return mockDisputeDetail(disputeId);
    }
    return jsonFetch<any>(`/operator/disputes/${disputeId}/`, { method: "GET" })
      .then((data) => normalizeOperatorDisputeDetail(data));
  },
  requestMoreEvidence(disputeId: number, payload: OperatorDisputeEvidenceRequestPayload) {
    if (mockDisputesEnabled) {
      return mockDisputeAction();
    }
    return jsonFetch<OperatorDisputeActionResponse>(
      `/operator/disputes/${disputeId}/request-more-evidence/`,
      { method: "POST", body: payload },
    );
  },
  closeDispute(disputeId: number, payload: OperatorDisputeClosePayload) {
    if (mockDisputesEnabled) {
      return mockDisputeAction();
    }
    return jsonFetch<OperatorDisputeActionResponse>(`/operator/disputes/${disputeId}/close/`, {
      method: "POST",
      body: payload,
    });
  },
  resolveDispute(disputeId: number, payload: OperatorDisputeResolvePayload) {
    if (mockDisputesEnabled) {
      return mockDisputeAction();
    }
    const decision = normalizeResolveDecision(payload.decision, payload.opened_by_role);
    const refundCents = toCents(payload.refund_amount);
    const captureCents = toCents(payload.deposit_capture_amount);
    const decisionNotes = payload.notes?.trim() ?? "";
    const reason = (payload.reason ?? decisionNotes).trim();
    return jsonFetch<OperatorDisputeActionResponse>(`/operator/disputes/${disputeId}/resolve/`, {
      method: "POST",
      body: {
        decision,
        refund_amount_cents: refundCents,
        deposit_capture_amount_cents: captureCents,
        decision_notes: decisionNotes,
        reason,
        suspend_listing: payload.suspend_listing,
        mark_renter_suspicious: payload.mark_renter_suspicious,
        mark_owner_suspicious: payload.mark_owner_suspicious,
      },
    });
  },
  appealDispute(disputeId: number, payload: OperatorDisputeAppealPayload) {
    if (mockDisputesEnabled) {
      return mockDisputeAction();
    }
    return jsonFetch<OperatorDisputeActionResponse>(`/operator/disputes/${disputeId}/appeal/`, {
      method: "POST",
      body: payload,
    });
  },
  auditLog(params: OperatorAuditLogParams = {}) {
    const query = buildQuery(params as Record<string, string | number | boolean>);
    return jsonFetch<OperatorAuditEvent[] | { results: OperatorAuditEvent[]; count?: number }>(
      `/operator/audit/${query}`,
      { method: "GET" },
    );
  },
  auditDetail(eventId: number) {
    return jsonFetch<OperatorAuditEvent>(`/operator/audit/${eventId}/`, { method: "GET" });
  },
  promotions(params: OperatorPromotionListParams = {}) {
    const query = buildQuery(params as Record<string, string | number | boolean>);
    return jsonFetch<OperatorPromotionListItem[] | { results: OperatorPromotionListItem[] }>(
      `/operator/promotions/${query}`,
      { method: "GET" },
    );
  },
  grantCompedPromotion(payload: OperatorPromotionGrantPayload) {
    return jsonFetch<OperatorPromotionListItem>("/operator/promotions/grant-comped/", {
      method: "POST",
      body: payload,
    });
  },
  cancelPromotionEarly(promotionId: number, payload: OperatorPromotionCancelPayload) {
    return jsonFetch<OperatorPromotionListItem>(
      `/operator/promotions/${promotionId}/cancel-early/`,
      { method: "POST", body: payload },
    );
  },
  commsConversations() {
    return jsonFetch<OperatorCommsConversationListItem[]>("/operator/comms/", { method: "GET" });
  },
  commsConversationDetail(conversationId: number) {
    return jsonFetch<OperatorCommsConversationDetail>(
      `/operator/comms/${conversationId}/`,
      { method: "GET" },
    );
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

function normalizeOperatorDisputeDetail(raw: any): OperatorDisputeDetail {
  const base = raw ?? {};
  const booking = normalizeBookingContext(base);
  const evidence = normalizeDisputeEvidence(base.evidence);
  const messages = normalizeDisputeMessages(base.messages);
  const timeline = normalizeDisputeTimeline(base);
  const resolution = normalizeDisputeResolution(base);

  return {
    ...base,
    booking,
    evidence,
    messages,
    timeline,
    resolution,
  } as OperatorDisputeDetail;
}

function normalizeBookingContext(raw: any): OperatorDisputeBookingContext | null {
  if (raw?.booking && typeof raw.booking === "object") {
    const booking = raw.booking as OperatorDisputeBookingContext;
    const totals = normalizeBookingTotals(booking?.totals ?? raw?.booking_summary?.totals ?? raw?.totals);
    return totals ? { ...booking, totals } : booking;
  }
  const summary = raw?.booking_summary;
  const bookingId = summary?.id ?? raw?.booking_id ?? raw?.booking;
  if (!bookingId) return null;
  const totals = normalizeBookingTotals(summary?.totals ?? raw?.totals);

  return {
    id: bookingId,
    listing_title: raw?.listing_title ?? raw?.listing_summary?.title ?? null,
    owner_email: raw?.owner_email ?? null,
    renter_email: raw?.renter_email ?? null,
    start_date: summary?.start_date ?? null,
    end_date: summary?.end_date ?? null,
    deposit_locked: summary?.deposit_locked ?? raw?.deposit_locked ?? false,
    deposit_hold_id: summary?.deposit_hold_id ?? null,
    totals,
  };
}

function normalizeBookingTotals(rawTotals: any): OperatorDisputeBookingContext["totals"] | undefined {
  if (!rawTotals || typeof rawTotals !== "object") return undefined;
  const parseCents = (value: unknown): number | null => {
    if (value === null || value === undefined || value === "") return null;
    const parsed =
      typeof value === "number"
        ? value
        : typeof value === "string"
          ? Number(value.replace(/,/g, "").trim())
          : Number.NaN;
    return Number.isFinite(parsed) ? Math.round(parsed) : null;
  };
  const parseDollarsToCents = (value: unknown): number | null => {
    if (value === null || value === undefined || value === "") return null;
    const amount = parseMoney(value);
    return Number.isFinite(amount) ? Math.round(amount * 100) : null;
  };
  const subtotalCents =
    parseCents(rawTotals.subtotal_cents) ??
    parseDollarsToCents(rawTotals.subtotal ?? rawTotals.rental_subtotal);
  const serviceFeeCents =
    parseCents(rawTotals.service_fee_cents) ??
    parseDollarsToCents(rawTotals.service_fee ?? rawTotals.renter_fee);
  const taxesCents =
    parseCents(rawTotals.taxes_cents) ??
    parseDollarsToCents(rawTotals.taxes);
  const totalCents =
    parseCents(rawTotals.total_cents) ??
    parseDollarsToCents(rawTotals.total_charge ?? rawTotals.total);
  const depositHoldCents =
    parseCents(rawTotals.deposit_hold_cents) ??
    parseDollarsToCents(rawTotals.damage_deposit ?? rawTotals.deposit_hold);

  return {
    subtotal_cents: subtotalCents ?? undefined,
    service_fee_cents: serviceFeeCents ?? undefined,
    taxes_cents: taxesCents ?? undefined,
    total_cents: totalCents ?? undefined,
    deposit_hold_cents: depositHoldCents ?? undefined,
  };
}

function normalizeDisputeEvidence(rawEvidence: any) {
  if (rawEvidence && !Array.isArray(rawEvidence) && typeof rawEvidence === "object") {
    return {
      before_photos: normalizeEvidenceList(rawEvidence.before_photos),
      after_photos: normalizeEvidenceList(rawEvidence.after_photos),
      dispute_uploads: normalizeEvidenceList(rawEvidence.dispute_uploads),
    };
  }

  if (Array.isArray(rawEvidence)) {
    return {
      before_photos: [],
      after_photos: [],
      dispute_uploads: normalizeEvidenceList(rawEvidence),
    };
  }

  return { before_photos: [], after_photos: [], dispute_uploads: [] };
}

function normalizeEvidenceList(items: any): OperatorDisputeEvidenceItem[] {
  if (!Array.isArray(items)) return [];
  return items.map((item) => {
    const url = typeof item?.url === "string" ? item.url : null;
    const thumbnail = typeof item?.thumbnail_url === "string" ? item.thumbnail_url : null;
    const fallback = typeof item?.s3_key === "string" ? item.s3_key : null;
    const label = item?.label ?? item?.filename ?? null;
    return {
      id: item?.id,
      url: url ?? thumbnail ?? fallback,
      thumbnail_url: thumbnail,
      filename: item?.filename ?? null,
      label,
      av_status: item?.av_status ?? null,
      uploaded_at: item?.uploaded_at ?? item?.created_at ?? null,
    } as OperatorDisputeEvidenceItem;
  });
}

function normalizeDisputeMessages(rawMessages: any): OperatorDisputeMessage[] {
  if (!Array.isArray(rawMessages)) return [];
  return rawMessages.map((message) => {
    const role = message?.author_role ?? message?.role ?? "system";
    const normalizedRole = role === "admin" ? "operator" : role;
    return {
      id: message?.id,
      author_role: normalizedRole,
      author_label: message?.author_label ?? null,
      body: message?.body ?? message?.text ?? "",
      created_at: message?.created_at,
    } as OperatorDisputeMessage;
  });
}

function normalizeDisputeTimeline(raw: any): OperatorDisputeTimelineItem[] {
  if (Array.isArray(raw?.timeline) && raw.timeline.length > 0) {
    return raw.timeline as OperatorDisputeTimelineItem[];
  }

  const items: OperatorDisputeTimelineItem[] = [];
  const openedAt = raw?.filed_at ?? raw?.created_at;
  if (openedAt) {
    items.push({
      id: `${raw?.id}-opened`,
      type: "stage_opened",
      label: "Dispute opened",
      actor_label: raw?.opened_by_label ?? null,
      created_at: openedAt,
    });
  }
  const evidenceDueAt = raw?.intake_evidence_due_at ?? raw?.evidence_due_at;
  if (evidenceDueAt) {
    items.push({
      id: `${raw?.id}-evidence-due`,
      type: "evidence_due",
      label: "Evidence due",
      description: raw?.evidence_missing ? "Awaiting evidence upload." : null,
      created_at: evidenceDueAt,
    });
  }
  if (raw?.rebuttal_due_at) {
    items.push({
      id: `${raw?.id}-rebuttal-due`,
      type: "rebuttal_due",
      label: "Rebuttal due",
      created_at: raw.rebuttal_due_at,
    });
  }
  if (raw?.review_started_at) {
    items.push({
      id: `${raw?.id}-review`,
      type: "stage_under_review",
      label: "Review started",
      created_at: raw.review_started_at,
    });
  }
  if (raw?.resolved_at) {
    items.push({
      id: `${raw?.id}-resolved`,
      type: "stage_resolved",
      label: "Dispute resolved",
      created_at: raw.resolved_at,
    });
  }
  return items;
}

function normalizeDisputeResolution(raw: any): OperatorDisputeResolution | null {
  if (raw?.resolution && typeof raw.resolution === "object") {
    return raw.resolution as OperatorDisputeResolution;
  }
  if (
    raw?.refund_amount_cents == null &&
    raw?.deposit_capture_amount_cents == null &&
    !raw?.resolved_at &&
    !raw?.decision_notes
  ) {
    return null;
  }
  return {
    refund_cents: raw?.refund_amount_cents ?? null,
    capture_cents: raw?.deposit_capture_amount_cents ?? null,
    resolved_at: raw?.resolved_at ?? null,
    resolved_by: raw?.resolved_by ?? null,
    note: raw?.decision_notes ?? null,
  };
}

function normalizeResolveDecision(
  decision: OperatorDisputeResolvePayload["decision"],
  openedByRole?: OperatorDisputeResolvePayload["opened_by_role"],
) {
  if (decision === "owner") return "resolved_owner";
  if (decision === "renter") return "resolved_renter";
  if (decision === "partial") return "resolved_partial";
  if (decision === "deny") {
    if (openedByRole === "owner") return "resolved_renter";
    if (openedByRole === "renter") return "resolved_owner";
    return "resolved_owner";
  }
  return decision;
}

function toCents(value: unknown) {
  const amount = parseMoney(value);
  return Number.isFinite(amount) ? Math.round(amount * 100) : 0;
}

export function formatOperatorUserName(user: Pick<OperatorUserListItem, "first_name" | "last_name" | "username" | "email">) {
  const full = `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim();
  if (full) return full;
  if (user.username?.trim()) return user.username.trim();
  return user.email?.trim() || "User";
}
