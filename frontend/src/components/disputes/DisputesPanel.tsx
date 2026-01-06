import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Calendar, Clock, Image as ImageIcon, Shield, User } from "lucide-react";
import { disputesAPI, type DisputeCase, type DisputeUserSummary } from "@/lib/api";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { DisputeThread } from "@/components/disputes/DisputeThread";

export const ACTIVE_DISPUTE_STATUSES = [
  "open",
  "intake_missing_evidence",
  "awaiting_rebuttal",
  "under_review",
] as const;

type ActiveDisputeStatus = (typeof ACTIVE_DISPUTE_STATUSES)[number];

export interface DisputesPanelProps {
  onCountChange?: (count: number) => void;
}

export interface UiDispute {
  id: number;
  bookingId: number;
  toolName: string;
  toolImage?: string | null;
  ownerId?: number | null;
  ownerName: string;
  ownerAvatar?: string | null;
  ownerVerified?: boolean;
  ownerRating?: number | null;
  renterId?: number | null;
  renterName: string;
  renterAvatar?: string | null;
  renterVerified?: boolean;
  renterRating?: number | null;
  status: "open" | "in-progress" | "resolved" | "closed";
  problem: string;
  createdAtLabel: string;
  dateRangeLabel: string;
}

type DisputeExtras = Partial<{
  booking_start_date: string;
  booking_end_date: string;
  listing_title: string;
  listing_primary_photo_url: string | null;
  owner_name: string;
  renter_name: string;
  owner_first_name: string;
  owner_last_name: string;
  renter_first_name: string;
  renter_last_name: string;
  tool_name: string;
  tool_image_url: string | null;
  owner_summary: DisputeUserSummary | null;
  renter_summary: DisputeUserSummary | null;
}>;

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});

export function countActiveDisputes(items: DisputeCase[]) {
  return items.filter((item) =>
    ACTIVE_DISPUTE_STATUSES.includes(item.status as ActiveDisputeStatus),
  ).length;
}

export function mapDisputeToUi(dispute: DisputeCase): UiDispute {
  const extras = dispute as DisputeCase & DisputeExtras;
  const ownerSummary = extras.owner_summary;
  const renterSummary = extras.renter_summary;
  const ownerName =
    ownerSummary?.name ??
    extras.owner_name ??
    buildName(extras.owner_first_name, extras.owner_last_name, "Owner");
  const renterName =
    renterSummary?.name ??
    extras.renter_name ??
    buildName(extras.renter_first_name, extras.renter_last_name, "Renter");

  const toolName =
    extras.listing_title ?? dispute.listing_title ?? extras.tool_name ?? `Booking #${dispute.booking}`;
  const toolImage =
    extras.listing_primary_photo_url ??
    dispute.listing_primary_photo_url ??
    extras.tool_image_url ??
    null;

  const problemSource = dispute.description?.trim();
  const problem = problemSource
    ? truncate(problemSource, 140)
    : "Dispute details not provided.";

  const createdAtLabel = formatDateLabel(dispute.filed_at ?? null);
  const dateRangeLabel =
    (extras.booking_start_date || dispute.booking_start_date) &&
    (extras.booking_end_date || dispute.booking_end_date)
      ? `${formatDateLabel(extras.booking_start_date ?? dispute.booking_start_date)} - ${formatDateLabel(extras.booking_end_date ?? dispute.booking_end_date)}`
      : `Booking #${dispute.booking}`;

  return {
    id: dispute.id,
    bookingId: dispute.booking,
    toolName,
    toolImage,
    ownerId: ownerSummary?.id ?? null,
    ownerName,
    ownerAvatar: ownerSummary?.avatar_url ?? null,
    ownerVerified: ownerSummary?.identity_verified ?? false,
    ownerRating: ownerSummary?.rating ?? null,
    renterId: renterSummary?.id ?? null,
    renterName,
    renterAvatar: renterSummary?.avatar_url ?? null,
    renterVerified: renterSummary?.identity_verified ?? false,
    renterRating: renterSummary?.rating ?? null,
    status: mapDisputeStatus(dispute.status),
    problem,
    createdAtLabel,
    dateRangeLabel,
  };
}

export function DisputesPanel({ onCountChange }: DisputesPanelProps) {
  const navigate = useNavigate();
  const [disputes, setDisputes] = useState<DisputeCase[]>([]);
  const [selectedDisputeId, setSelectedDisputeId] = useState<number | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const handleViewProfile = useCallback(
    (userId?: number | null) => {
      if (!userId) return;
      navigate(`/users/${userId}`);
    },
    [navigate],
  );

  const refreshDisputes = useCallback(
    async (nextSelectedId?: number | null) => {
      setLoading(true);
      setError(null);
      try {
        const data = await disputesAPI.list();
        const items = data || [];
        setDisputes(items);
        onCountChange?.(countActiveDisputes(items));
        setSelectedDisputeId((current) => {
          const hasNextSelected =
            typeof nextSelectedId === "number" &&
            items.some((item) => item.id === nextSelectedId);
          if (hasNextSelected) {
            return nextSelectedId;
          }
          if (current && items.some((item) => item.id === current)) {
            return current;
          }
          return null;
        });
      } catch (fetchError) {
        setError("Unable to load disputes right now.");
        onCountChange?.(0);
      } finally {
        setLoading(false);
      }
    },
    [onCountChange],
  );

  useEffect(() => {
    void refreshDisputes();
  }, [refreshDisputes]);

  useEffect(() => {
    const handleDisputeCreated = (event: Event) => {
      const detail = (event as CustomEvent<{ id?: number }>).detail;
      void refreshDisputes(detail?.id ?? undefined);
    };
    window.addEventListener("dispute:created", handleDisputeCreated);
    return () => {
      window.removeEventListener("dispute:created", handleDisputeCreated);
    };
  }, [refreshDisputes]);

  const uiDisputes = useMemo(() => disputes.map(mapDisputeToUi), [disputes]);
  const selectedDispute = useMemo(() => {
    if (selectedDisputeId === null) return null;
    return disputes.find((item) => item.id === selectedDisputeId) ?? null;
  }, [disputes, selectedDisputeId]);
  const selectedUiDispute = useMemo(
    () => (selectedDispute ? mapDisputeToUi(selectedDispute) : null),
    [selectedDispute],
  );

  const hasDisputes = uiDisputes.length > 0;
  const showingList = selectedDisputeId === null;

  if (!loading && !hasDisputes) {
    return (
      <div>
        <div className="mb-6">
          <h2 className="text-2xl mb-2">Disputes</h2>
          <p className="text-muted-foreground">
            View and manage your rental disputes. Our support team is here to help resolve any
            issues.
          </p>
        </div>
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <div className="bg-card border rounded-lg p-12 text-center">
          <AlertTriangle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="font-medium mb-2">No Disputes</h3>
          <p className="text-muted-foreground">
            You do not have any active disputes. We hope your rentals continue to go smoothly!
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="mb-2">
        <h2 className="text-2xl mb-2">Disputes</h2>
        <p className="text-muted-foreground">
          View and manage your rental disputes. Our support team is here to help resolve any issues.
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {loading && <p className="text-sm text-muted-foreground">Loading disputes...</p>}

      {hasDisputes && showingList && (
        <div className="space-y-4">
          {uiDisputes.map((dispute) => (
            <button
              key={dispute.id}
              type="button"
              onClick={() => setSelectedDisputeId(dispute.id)}
              className="w-full text-left"
            >
              <div className="bg-card border rounded-lg p-5 hover:border-[var(--primary)] transition shadow-sm">
                <div className="flex items-start gap-4">
                  {dispute.toolImage ? (
                    <img
                      src={dispute.toolImage}
                      alt={dispute.toolName}
                      className="w-28 h-24 object-cover rounded-lg"
                    />
                  ) : (
                    <div className="w-28 h-24 bg-muted rounded-lg flex items-center justify-center">
                      <ImageIcon className="w-8 h-8 text-muted-foreground" />
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="font-semibold text-lg leading-tight break-words">
                          {dispute.toolName}
                        </h3>
                        <p className="text-sm text-muted-foreground">Booking #{dispute.bookingId}</p>
                      </div>
                      <Badge className={getStatusColor(dispute.status)}>
                        {dispute.status.replace("-", " ")}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-2 mt-3">
                      <AlertTriangle className="w-4 h-4 text-orange-500 flex-shrink-0" />
                      <span className="font-medium text-sm leading-snug break-words">
                        {dispute.problem}
                      </span>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm mt-4">
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-muted-foreground" />
                        <span className="text-muted-foreground">Owner:</span>
                        <span className="truncate">{dispute.ownerName}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <User className="w-4 h-4 text-muted-foreground" />
                        <span className="text-muted-foreground">Renter:</span>
                        <span className="truncate">{dispute.renterName}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <Calendar className="w-4 h-4 text-muted-foreground" />
                        <span className="text-muted-foreground">Opened:</span>
                        <span className="truncate">{dispute.createdAtLabel}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
      )}

      {hasDisputes && !showingList && selectedDispute && selectedUiDispute && (
        <div className="space-y-6">
          <button
            onClick={() => setSelectedDisputeId(null)}
            className="flex items-center gap-2 text-[var(--primary)] hover:underline"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Disputes
          </button>

          <div className="bg-card border rounded-lg p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl mb-2">Dispute #{selectedUiDispute.id}</h2>
                <p className="text-muted-foreground">Booking #{selectedUiDispute.bookingId}</p>
              </div>
              <Badge className={getStatusColor(selectedUiDispute.status)}>
                {selectedUiDispute.status.replace("-", " ").toUpperCase()}
              </Badge>
            </div>

            <div className="flex items-center gap-4 mb-4">
              {selectedUiDispute.toolImage ? (
                <img
                  src={selectedUiDispute.toolImage}
                  alt={selectedUiDispute.toolName}
                  className="w-20 h-20 object-cover rounded-lg"
                />
              ) : (
                <div className="w-20 h-20 bg-muted rounded-lg flex items-center justify-center">
                  <ImageIcon className="w-6 h-6 text-muted-foreground" />
                </div>
              )}
              <div>
                <h3 className="font-medium">{selectedUiDispute.toolName}</h3>
                <p className="text-sm text-muted-foreground">{selectedUiDispute.problem}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t">
              <div className="flex items-center gap-2 text-sm">
                <Calendar className="w-4 h-4 text-muted-foreground" />
                <span>Rental: {selectedUiDispute.dateRangeLabel}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Clock className="w-4 h-4 text-muted-foreground" />
                <span>Dispute opened: {selectedUiDispute.createdAtLabel}</span>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <PartyCard
              title="Tool Owner"
              name={selectedUiDispute.ownerName}
              avatarUrl={selectedUiDispute.ownerAvatar}
              verified={selectedUiDispute.ownerVerified}
              rating={selectedUiDispute.ownerRating}
              userId={selectedUiDispute.ownerId}
              onViewProfile={handleViewProfile}
            />
            <PartyCard
              title="Renter"
              name={selectedUiDispute.renterName}
              avatarUrl={selectedUiDispute.renterAvatar}
              verified={selectedUiDispute.renterVerified}
              rating={selectedUiDispute.renterRating}
              userId={selectedUiDispute.renterId}
              onViewProfile={handleViewProfile}
            />
          </div>

          <div className="bg-card border rounded-lg p-6">
            <h3 className="font-medium mb-2">Dispute Description</h3>
            <p className="text-muted-foreground">
              {selectedDispute.description?.trim() || "No description provided."}
            </p>
          </div>

          {selectedDisputeId !== null && <DisputeThread disputeId={selectedDisputeId} />}
        </div>
      )}
    </div>
  );
}

interface PartyCardProps {
  title: string;
  name: string;
  avatarUrl?: string | null;
  verified?: boolean;
  rating?: number | null;
  userId?: number | null;
  onViewProfile?: (userId: number) => void;
}

function PartyCard({ title, name, avatarUrl, verified, rating, userId, onViewProfile }: PartyCardProps) {
  const hasRating = typeof rating === "number";
  const subtitle = hasRating
    ? `Rating: ${rating.toFixed(1)} ★`
    : verified
      ? "Verified member"
      : "Member";
  const canViewProfile = typeof userId === "number" && Boolean(onViewProfile);
  return (
    <div className="bg-card border rounded-lg p-4">
      <h3 className="text-sm text-muted-foreground mb-3">{title}</h3>
      <div className="flex items-center gap-3">
        <Avatar className="w-12 h-12">
          <AvatarImage src={avatarUrl ?? undefined} />
          <AvatarFallback
            className="bg-[var(--primary)]"
            style={{ color: "var(--primary-foreground)" }}
          >
            {getInitials(name)}
          </AvatarFallback>
        </Avatar>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h4 className="font-medium truncate">{name}</h4>
            {verified ? <Shield className="w-4 h-4 text-green-600" /> : null}
          </div>
          <p className="text-sm text-muted-foreground">{subtitle}</p>
        </div>
        <button
          type="button"
          className="px-3 py-1.5 text-sm bg-[var(--primary)] text-[var(--primary-foreground)] rounded-lg hover:opacity-90 transition-opacity disabled:cursor-not-allowed disabled:opacity-50"
          onClick={() => {
            if (userId && onViewProfile) {
              onViewProfile(userId);
            }
          }}
          disabled={!canViewProfile}
        >
          View Profile
        </button>
      </div>
    </div>
  );
}

function mapDisputeStatus(status: DisputeCase["status"]): UiDispute["status"] {
  switch (status) {
    case "under_review":
      return "in-progress";
    case "resolved_renter":
    case "resolved_owner":
    case "resolved_partial":
      return "resolved";
    case "closed_auto":
      return "closed";
    default:
      return "open";
  }
}

function getStatusColor(status: UiDispute["status"]) {
  switch (status) {
    case "open":
      return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300";
    case "in-progress":
      return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300";
    case "resolved":
      return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300";
    case "closed":
    default:
      return "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300";
  }
}

function formatDateLabel(value?: string | null) {
  if (!value) {
    return "Date unavailable";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return "Date unavailable";
  }
  return dateFormatter.format(parsed);
}

function truncate(text: string, maxLength: number) {
  if (text.length <= maxLength) return text;
  return `${text.slice(0, Math.max(0, maxLength - 3))}...`;
}

function buildName(first?: string | null, last?: string | null, fallback: string = "Guest") {
  const safeFirst = first?.trim() ?? "";
  const safeLast = last?.trim() ?? "";
  const combined = `${safeFirst} ${safeLast}`.trim();
  return combined || fallback;
}

function getInitials(name: string) {
  const parts = name.split(" ").filter(Boolean);
  if (parts.length === 0) return "U";
  return parts
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}
