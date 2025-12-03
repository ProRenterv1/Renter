import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { AvatarFallback, AvatarImage } from "../ui/avatar";
import { Star, X } from "lucide-react";
import { format } from "date-fns";
import { AuthStore } from "@/lib/auth";
import ChatMessages from "@/components/chat/Messages";
import {
  bookingsAPI,
  deriveDisplayRentalStatus,
  listingsAPI,
  disputesAPI,
  type Booking,
  type BookingTotals,
  type DisputeCase,
  type DisputeStatus,
  type Listing,
} from "@/lib/api";
import { fetchConversations, type ConversationSummary } from "@/lib/chat";
import { formatCurrency } from "@/lib/utils";
import { PolicyConfirmationModal } from "../PolicyConfirmationModal";
import { VerifiedAvatar } from "@/components/VerifiedAvatar";
import { ReviewModal } from "@/components/reviews/ReviewModal";
import { startEventStream, type EventEnvelope } from "@/lib/events";
import { DisputeWizard } from "@/components/disputes/DisputeWizard";

type StatusFilter = "all" | Booking["status"];

interface BookingRequestRow {
  booking: Booking;
  listingPhoto?: string;
  listingCity?: string;
}

export interface BookingRequestsProps {
  onPendingCountChange?: (count: number) => void;
}

const activeDisputeStatuses: DisputeStatus[] = [
  "open",
  "intake_missing_evidence",
  "awaiting_rebuttal",
  "under_review",
];

const formatDisputeStatusLabel = (status: DisputeStatus): string => {
  switch (status) {
    case "awaiting_rebuttal":
      return "Dispute: Awaiting other party";
    case "under_review":
      return "Dispute: Under review";
    case "intake_missing_evidence":
      return "Dispute: Open (needs evidence)";
    default:
      return "Dispute: Open";
  }
};

const canConfirmPickup = (booking: Booking): boolean => {
  if (booking.status !== "paid" || booking.pickup_confirmed_at) {
    return false;
  }
  const requiresBeforePhotos = booking.before_photos_required !== false;
  if (!requiresBeforePhotos) {
    return true;
  }
  return Boolean(booking.before_photos_uploaded_at);
};

type BookingWithReturnFields = Booking & {
  returned_by_renter_at?: string | null;
  return_confirmed_at?: string | null;
  after_photos_uploaded_at?: string | null;
};

const resolveRenterDisplayName = (row: BookingRequestRow | null | undefined): string => {
  if (!row) return "Renter";
  const renterFirstName = row.booking.renter_first_name?.trim() ?? "";
  const renterLastName = row.booking.renter_last_name?.trim() ?? "";
  const renterUsername = row.booking.renter_username ?? "";
  return (
    [renterFirstName, renterLastName].filter(Boolean).join(" ") ||
    renterUsername ||
    (row.booking.renter ? `Renter #${row.booking.renter}` : "Renter")
  );
};

const isReturnPending = (booking: BookingWithReturnFields): boolean => {
  return (
    booking.status === "paid" &&
    !!booking.returned_by_renter_at &&
    !booking.return_confirmed_at &&
    hasReachedReturnWindow(booking.end_date)
  );
};

const parseLocalDate = (isoDate: string) => {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) {
    throw new Error("invalid date");
  }
  return new Date(year, month - 1, day);
};

const startOfToday = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
};

const hasReachedReturnWindow = (endDateRaw: string): boolean => {
  try {
    const endDate = parseLocalDate(endDateRaw);
    endDate.setDate(endDate.getDate() - 1);
    return startOfToday().getTime() >= endDate.getTime();
  } catch {
    return false;
  }
};

const formatDateRange = (start: string, end: string) => {
  try {
    const startDate = parseLocalDate(start);
    const rawEndDate = parseLocalDate(end);
    const displayEndDate = new Date(rawEndDate);
    displayEndDate.setDate(displayEndDate.getDate() - 1);
    if (displayEndDate.getTime() < startDate.getTime()) {
      displayEndDate.setTime(startDate.getTime());
    }
    return `${format(startDate, "MMM d")} - ${format(displayEndDate, "MMM d, yyyy")}`;
  } catch {
    return `${start} - ${end}`;
  }
};

const placeholderImage = "https://placehold.co/200x200?text=Listing";

const hasChargeIntent = (booking: Booking) =>
  Boolean((booking.charge_payment_intent_id ?? "").trim());

const isPrePaymentBooking = (booking: Booking) => !hasChargeIntent(booking);

const buildOwnerCancelWarning = (booking: Booking): string => {
  if (isPrePaymentBooking(booking)) {
    return "You are about to cancel this booking before any payment was taken. The renter will not be charged and no payout will be made.";
  }
  return "You are canceling after the renter has already paid. Our policy issues the renter a full refund of the rent, service fee, and damage deposit, and you will not receive any payout for this booking. Frequent owner cancellations may impact your account standing.";
};

export function BookingRequests({ onPendingCountChange }: BookingRequestsProps = {}) {
  const [requests, setRequests] = useState<BookingRequestRow[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<BookingRequestRow | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [pendingApprovalId, setPendingApprovalId] = useState<number | null>(null);
  const [policyAcknowledged, setPolicyAcknowledged] = useState(false);
  const [cancelConfirm, setCancelConfirm] = useState<{
    booking: Booking;
    warning: string;
    loading: boolean;
  } | null>(null);
  const [confirmingPickupId, setConfirmingPickupId] = useState<number | null>(null);
  const [afterPhotosTarget, setAfterPhotosTarget] = useState<BookingRequestRow | null>(null);
  const [afterPhotosFiles, setAfterPhotosFiles] = useState<{ file: File; previewUrl: string }[]>([]);
  const [afterUploadLoading, setAfterUploadLoading] = useState(false);
  const [afterUploadError, setAfterUploadError] = useState<string | null>(null);
  const [chatConversations, setChatConversations] = useState<ConversationSummary[]>([]);
  const [chatConversationId, setChatConversationId] = useState<number | null>(null);
  const [ownerReviewTarget, setOwnerReviewTarget] = useState<{
    bookingId: number;
    renterName: string;
  } | null>(null);
  const [disputeWizardOpen, setDisputeWizardOpen] = useState(false);
  const [disputeContext, setDisputeContext] = useState<{
    bookingId: number;
    toolName: string;
    rentalPeriod: string;
  } | null>(null);
  const [disputesByBookingId, setDisputesByBookingId] = useState<Record<number, DisputeCase | null>>({});
  const isMountedRef = useRef(true);
  const requestsRef = useRef<BookingRequestRow[]>([]);
  const afterFileInputRef = useRef<HTMLInputElement | null>(null);
  const currentUserId = AuthStore.getCurrentUser()?.id ?? null;
  const navigate = useNavigate();
  const selectedTotals = selectedRequest?.booking.totals ?? null;
  const selectedOwnerAmount = Number(
    selectedTotals
      ? selectedTotals.owner_payout ??
        selectedTotals.rental_subtotal ??
        selectedTotals.total_charge ??
        0
      : 0,
  );
  const rentalBaseAmount = Number(
    selectedTotals ? selectedTotals.rental_subtotal ?? selectedTotals.total_charge ?? 0 : 0,
  );
  const ownerServiceFeeRaw = Number(
    selectedTotals ? selectedTotals.owner_fee ?? selectedTotals.platform_fee_total ?? 0 : 0,
  );
  const ownerServiceFeeAmount = Math.abs(ownerServiceFeeRaw);
  const ownerServiceFeeText =
    ownerServiceFeeAmount === 0 ? formatCurrency(0, "CAD") : `-${formatCurrency(ownerServiceFeeAmount, "CAD")}`;

  const loadChatConversations = useCallback(async () => {
    try {
      const data = await fetchConversations();
      setChatConversations(data);
      return data;
    } catch (err) {
      console.error("chat: failed to load conversations", err);
      return [];
    }
  }, []);

  useEffect(() => {
    void loadChatConversations();
  }, [loadChatConversations]);

  const reloadRequests = useCallback(async () => {
    if (!currentUserId) {
      setRequests([]);
      setError("Please sign in to see booking requests.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [bookings, listingsResponse] = await Promise.all([
        bookingsAPI.listMine(),
        listingsAPI.mine(),
      ]);
      if (!isMountedRef.current) {
        return;
      }
      const listingEntries = (listingsResponse.results ?? []).map((listing) => [listing.id, listing]);
      const listingMap = new Map<number, Listing>(listingEntries);
      const ownerBookings = bookings.filter((booking) => booking.owner === currentUserId);
      const prepared: BookingRequestRow[] = ownerBookings.map((booking) => {
        const listingInfo = listingMap.get(booking.listing);
        return {
          booking,
          listing: listingInfo,
          listingPhoto: listingInfo?.photos[0]?.url,
          listingCity: listingInfo?.city ?? "",
        };
      });
      setRequests(prepared);
      setError(null);
    } catch (err) {
      if (!isMountedRef.current) {
        return;
      }
      setError("Could not load booking requests. Please try again.");
    } finally {
      if (!isMountedRef.current) {
        return;
      }
      setLoading(false);
    }
  }, [currentUserId]);

  const openChatForBooking = useCallback(
    async (bookingId: number) => {
      const existing = chatConversations.find((conv) => conv.booking_id === bookingId);
      if (existing) {
        setChatConversationId(existing.id);
        return;
      }
      const refreshed = await loadChatConversations();
      const fallback = refreshed.find((conv) => conv.booking_id === bookingId);
      if (fallback) {
        setChatConversationId(fallback.id);
      } else {
        toast.error("Chat is not available for this booking yet.");
      }
    },
    [chatConversations, loadChatConversations],
  );

  useEffect(() => {
    void reloadRequests();
    return () => {
      isMountedRef.current = false;
    };
  }, [reloadRequests]);

  useEffect(() => {
    requestsRef.current = requests;
  }, [requests]);

  useEffect(() => {
    let cancelled = false;
    const loadDisputes = async () => {
      const disputed = requests.filter((row) => row.booking.is_disputed);
      if (!disputed.length) {
        setDisputesByBookingId({});
        return;
      }
      const entries = await Promise.all(
        disputed.map(async (row) => {
          try {
            const cases = await disputesAPI.list({ bookingId: row.booking.id });
            const active =
              cases.find((item) => activeDisputeStatuses.includes(item.status)) ||
              cases[0] ||
              null;
            return [row.booking.id, active] as const;
          } catch {
            return [row.booking.id, null] as const;
          }
        }),
      );
      if (!isMountedRef.current || cancelled) {
        return;
      }
      setDisputesByBookingId(Object.fromEntries(entries));
    };
    void loadDisputes();
    return () => {
      cancelled = true;
    };
  }, [requests]);

  useEffect(() => {
    return () => {
      afterPhotosFiles.forEach((upload) => URL.revokeObjectURL(upload.previewUrl));
    };
  }, [afterPhotosFiles]);

  useEffect(() => {
    if (!currentUserId) {
      return;
    }
    const handle = startEventStream({
      onEvents: (events) => {
        let shouldReload = false;
        for (const event of events as EventEnvelope<any>[]) {
          if (
            event.type === "booking:status_changed" ||
            event.type === "booking:return_requested"
          ) {
            shouldReload = true;
          }
          if (event.type === "booking:review_invite") {
            shouldReload = true;
            const payload = event.payload as {
              booking_id: number;
              owner_id: number;
              renter_id: number;
            };
            if (payload.owner_id === currentUserId) {
              const row = requestsRef.current.find(
                (entry) => entry.booking.id === payload.booking_id,
              );
              const renterName =
                (row && resolveRenterDisplayName(row)) || `Renter #${payload.renter_id}`;
              setOwnerReviewTarget({ bookingId: payload.booking_id, renterName });
            }
          }
        }
        if (shouldReload) {
          void reloadRequests();
        }
      },
    });

    return () => {
      handle.stop();
    };
  }, [currentUserId, reloadRequests]);

  const filteredRequests = useMemo(() => {
    if (statusFilter === "all") {
      return requests;
    }
    return requests.filter((row) => row.booking.status === statusFilter);
  }, [requests, statusFilter]);

  const selectedRenterDetails = useMemo(() => {
    if (!selectedRequest) {
      return null;
    }
    const renterFirstName = selectedRequest.booking.renter_first_name?.trim() ?? "";
    const renterLastName = selectedRequest.booking.renter_last_name?.trim() ?? "";
    const renterUsername = selectedRequest.booking.renter_username ?? "";
    const renterDisplayName = resolveRenterDisplayName(selectedRequest);
    const renterAvatarUrl =
      selectedRequest.booking.renter_avatar_url ||
      `https://api.dicebear.com/7.x/initials/svg?seed=${encodeURIComponent(renterDisplayName)}`;
    const initials =
      (renterFirstName[0] ?? "") + (renterLastName[0] ?? "") ||
      renterUsername.slice(0, 2).toUpperCase() ||
      String(selectedRequest.booking.renter ?? "R").slice(0, 2).toUpperCase();
    const rating =
      selectedRequest.booking.renter_rating ??
      null;

    return {
      displayName: renterDisplayName,
      avatarUrl: renterAvatarUrl,
      initials,
      rating,
      isVerified: Boolean(selectedRequest.booking.renter_identity_verified),
    };
  }, [selectedRequest]);

  const handleViewRenterProfile = () => {
    if (!selectedRequest?.booking?.renter) {
      return;
    }
    const renterId = selectedRequest.booking.renter;
    setSelectedRequest(null);
    navigate(`/users/${renterId}`);
  };

  const getBookingStatusBadge = (booking: Booking) => {
    const badgeVariant =
      booking.status === "completed"
        ? "secondary"
        : booking.status === "canceled"
        ? "outline"
        : booking.status === "paid"
        ? "secondary"
        : "default";
    return <Badge variant={badgeVariant}>{deriveDisplayRentalStatus(booking)}</Badge>;
  };

  const updateBookingInState = (updated: Booking) => {
    setRequests((prev) =>
      prev.map((row) =>
        row.booking.id === updated.id
          ? { ...row, booking: updated }
          : row,
      ),
    );
    setSelectedRequest((prev) =>
      prev && prev.booking.id === updated.id ? { ...prev, booking: updated } : prev,
    );
  };

  const handleApprove = async (bookingId: number) => {
    setActionLoading(true);
    let success = false;
    try {
      const updated = await bookingsAPI.confirm(bookingId);
      updateBookingInState(updated);
      await refreshCountsFromServer();
      success = true;
    } catch (err) {
      setError("Could not approve this booking. Please try again.");
    } finally {
      setActionLoading(false);
    }
    return success;
  };

  const openOwnerCancelDialog = (booking: Booking) => {
    setCancelConfirm({
      booking,
      warning: buildOwnerCancelWarning(booking),
      loading: false,
    });
  };

  const handleConfirmOwnerCancel = async () => {
    if (!cancelConfirm) return;
    const bookingId = cancelConfirm.booking.id;
    setCancelConfirm({ ...cancelConfirm, loading: true });
    try {
      const updated = await bookingsAPI.cancel(bookingId);
      updateBookingInState(updated);
      setCancelConfirm(null);
      await refreshCountsFromServer();
    } catch (err) {
      setError("We couldn't cancel this booking right now. Please try again.");
      setCancelConfirm((prev) => (prev ? { ...prev, loading: false } : prev));
    }
  };

  const handleConfirmPickup = async (bookingId: number) => {
    setConfirmingPickupId(bookingId);
    try {
      const updated = await bookingsAPI.confirmPickup(bookingId);
      updateBookingInState(updated);
      toast.success("Pickup confirmed. Booking is now in progress.");
    } catch (err) {
      console.error("confirm pickup failed", err);
      toast.error("Could not confirm pickup. Please try again.");
    } finally {
      setConfirmingPickupId((current) => (current === bookingId ? null : current));
    }
  };

  const resetAfterPhotosState = () => {
    setAfterPhotosFiles((prev) => {
      prev.forEach((upload) => URL.revokeObjectURL(upload.previewUrl));
      return [];
    });
    setAfterUploadError(null);
    setAfterUploadLoading(false);
  };

  const openAfterPhotosDialog = (row: BookingRequestRow) => {
    resetAfterPhotosState();
    setAfterPhotosTarget(row);
  };

  const closeAfterPhotosDialog = () => {
    resetAfterPhotosState();
    setAfterPhotosTarget(null);
  };

  const handleAfterPhotoInput = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) {
      return;
    }
    const uploads = Array.from(files).map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    setAfterPhotosFiles((prev) => [...prev, ...uploads]);
    setAfterUploadError(null);
    event.target.value = "";
  };

  const removeAfterPhoto = (index: number) => {
    setAfterPhotosFiles((prev) => {
      const next = [...prev];
      const [removed] = next.splice(index, 1);
      if (removed) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return next;
    });
  };

  const handleAfterPhotosSubmit = async () => {
    if (!afterPhotosTarget) {
      return;
    }
    if (afterPhotosFiles.length === 0) {
      setAfterUploadError("Please select at least one photo before continuing.");
      return;
    }
    setAfterUploadError(null);
    setAfterUploadLoading(true);
    const bookingId = afterPhotosTarget.booking.id;
    try {
      const marked = await bookingsAPI.ownerMarkReturned(bookingId);
      updateBookingInState(marked);
      for (const upload of afterPhotosFiles) {
        const presign = await bookingsAPI.afterPhotosPresign(bookingId, {
          filename: upload.file.name,
          content_type: upload.file.type || "application/octet-stream",
          size: upload.file.size,
        });
        const uploadHeaders: Record<string, string> = {
          ...presign.headers,
        };
        if (upload.file.type) {
          uploadHeaders["Content-Type"] = upload.file.type;
        }
        const uploadResponse = await fetch(presign.upload_url, {
          method: "PUT",
          headers: uploadHeaders,
          body: upload.file,
        });
        if (!uploadResponse.ok) {
          throw new Error("Upload failed");
        }
        const etagHeader =
          uploadResponse.headers.get("ETag") ?? uploadResponse.headers.get("etag");
        if (!etagHeader) {
          throw new Error("Upload verification failed");
        }
        const cleanEtag = etagHeader.replace(/"/g, "");
        await bookingsAPI.afterPhotosComplete(bookingId, {
          key: presign.key,
          etag: cleanEtag,
          filename: upload.file.name,
          content_type: upload.file.type || "application/octet-stream",
          size: upload.file.size,
        });
      }
      const renterName = resolveRenterDisplayName(afterPhotosTarget);
      closeAfterPhotosDialog();
      toast.success("After-photos uploaded. Booking will be completed shortly.");
      if (renterName) {
        setOwnerReviewTarget({ bookingId, renterName });
      }
      void reloadRequests();
    } catch (err) {
      console.error("after photos upload failed", err);
      setAfterUploadError("Failed to upload photos. Please try again.");
    } finally {
      setAfterUploadLoading(false);
    }
  };

  const openPolicyModalForApproval = () => {
    if (!selectedRequest) return;
    setPendingApprovalId(selectedRequest.booking.id);
    setPolicyAcknowledged(false);
    setPolicyModalOpen(true);
  };

  const closePolicyModal = () => {
    setPolicyModalOpen(false);
    setPendingApprovalId(null);
  };

  const confirmPolicyAndApprove = async () => {
    if (!pendingApprovalId) return;
    const success = await handleApprove(pendingApprovalId);
    if (success) {
      closePolicyModal();
    }
  };

  const refreshCountsFromServer = useCallback(async () => {
    if (!onPendingCountChange) {
      return;
    }
    try {
      const response = await bookingsAPI.pendingRequestsCount();
      onPendingCountChange(Number(response.pending_requests ?? 0));
    } catch (error) {
      if (import.meta.env.DEV) {
        console.warn("Failed to refresh booking counters", error);
      }
    }
  }, [onPendingCountChange]);

  const pendingRequests = useMemo(
    () => requests.filter((row) => row.booking.status === "requested").length,
    [requests],
  );

  useEffect(() => {
    if (onPendingCountChange) {
      onPendingCountChange(pendingRequests);
    }
  }, [pendingRequests, onPendingCountChange]);

  const renderDialogActions = (booking: Booking) => {
    const requestStatusLabel = deriveDisplayRentalStatus(booking);
    const requestStatus = (booking.status || "").toLowerCase();
    const isPendingRequest = requestStatus === "requested";
    const canCancelAfterApproval = requestStatus === "confirmed" || requestStatus === "paid";
    const returnPending = isReturnPending(booking as BookingWithReturnFields);

    if (isPendingRequest) {
      return (
        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            onClick={() => openOwnerCancelDialog(booking)}
            className="rounded-full"
            disabled={actionLoading}
          >
            Deny Booking
          </Button>
          <Button
            onClick={openPolicyModalForApproval}
            className="rounded-full"
            disabled={actionLoading}
          >
            {actionLoading ? "Processing..." : "Approve Booking"}
          </Button>
        </DialogFooter>
      );
    }

    if (returnPending) {
      return (
        <DialogFooter className="w-full flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1 text-sm text-muted-foreground text-center sm:text-left">
            Renter marked this item as returned. Upload after-photos to finalize.
          </div>
          <Button
            className="rounded-full"
            onClick={() => {
              if (selectedRequest) {
                openAfterPhotosDialog(selectedRequest);
              }
            }}
            disabled={afterUploadLoading}
          >
            {afterUploadLoading ? "Uploading..." : "Mark returned"}
          </Button>
        </DialogFooter>
      );
    }

    if (canConfirmPickup(booking)) {
      return (
        <DialogFooter className="w-full flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1 text-sm text-muted-foreground text-center sm:text-left">
            Renter uploaded before photos. Confirm pickup once the tool has been handed over.
          </div>
          <Button
            className="rounded-full"
            onClick={() => handleConfirmPickup(booking.id)}
            disabled={confirmingPickupId === booking.id}
          >
            {confirmingPickupId === booking.id ? "Confirming..." : "Confirm pickup"}
          </Button>
        </DialogFooter>
      );
    }

    if (canCancelAfterApproval) {
      const statusMessage =
        booking.status === "confirmed"
          ? "Booking approved - awaiting renter payment."
          : "Booking has been paid. Coordinate pickup or cancel if needed.";

      return (
        <DialogFooter className="w-full flex-col sm:flex-row sm:items-center gap-3">
          <div className="flex-1 text-sm text-muted-foreground text-center sm:text-left">
            {statusMessage}
          </div>
          <Button variant="outline" className="rounded-full">
            Report an issue
          </Button>
        </DialogFooter>
      );
    }

    return (
      <div className="text-center py-2">
        <p className="text-muted-foreground">This request is {requestStatusLabel}.</p>
      </div>
    );
  };

  return (
    <>
      <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Booking Requests</h1>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>
            Manage incoming requests for your listings
          </p>
        </div>
        <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
          <SelectTrigger className="w-[160px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="requested">Requested</SelectItem>
            <SelectItem value="confirmed">Confirmed</SelectItem>
            <SelectItem value="paid">Paid</SelectItem>
            <SelectItem value="completed">Completed</SelectItem>
            <SelectItem value="canceled">Canceled</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {error && (
        <Card>
          <CardContent className="py-4">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Pending Requests</CardTitle>
            <CardDescription>Awaiting your approval</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{pendingRequests}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Total Requests</CardTitle>
            <CardDescription>All time</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{requests.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Filtered</CardTitle>
            <CardDescription>Matching current filter</CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold">{filteredRequests.length}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Requests</CardTitle>
          <CardDescription>Review and respond to renter requests</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Listing</TableHead>
                <TableHead>Date Range</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">You Receive</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-sm text-muted-foreground">
                    Loading booking requests...
                  </TableCell>
                </TableRow>
              )}
              {!loading && filteredRequests.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-8 text-sm text-muted-foreground">
                    No booking requests match the selected filter.
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                filteredRequests.map((row) => {
                  const statusLabel = deriveDisplayRentalStatus(row.booking);
                  const totals: BookingTotals = row.booking.totals ?? {};
                  const amountRaw = Number(
                    totals.owner_payout ?? totals.rental_subtotal ?? totals.total_charge ?? 0,
                  );
                  const amountLabel = formatCurrency(amountRaw, "CAD");
                  const dateRange = formatDateRange(row.booking.start_date, row.booking.end_date);
                  const returnPending = isReturnPending(row.booking as BookingWithReturnFields);
                  const disputeWindowExpiresAt = row.booking.dispute_window_expires_at
                    ? new Date(row.booking.dispute_window_expires_at)
                    : null;
                  const now = new Date();
                  const withinDisputeWindow = disputeWindowExpiresAt
                    ? now < disputeWindowExpiresAt
                    : false;
                  const showDisputeButton =
                    withinDisputeWindow &&
                    (row.booking.status === "completed" || row.booking.status === "canceled");

                  return (
                    <TableRow key={row.booking.id} className="hover:bg-muted/50">
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <img
                            src={row.listingPhoto || placeholderImage}
                            alt={row.booking.listing_title}
                            className="w-12 h-12 rounded-lg object-cover border border-border"
                          />
                          <div>
                            <p className="font-medium">{row.booking.listing_title}</p>
                            <p className="text-xs text-muted-foreground">{row.listingCity || "City unknown"}</p>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>{dateRange}</TableCell>
                      <TableCell>
                        {disputesByBookingId[row.booking.id] ? (
                          <Badge variant="outline" className="text-xs font-normal">
                            {formatDisputeStatusLabel(
                              (disputesByBookingId[row.booking.id]?.status ||
                                "open") as DisputeStatus,
                            )}
                          </Badge>
                        ) : (
                          getBookingStatusBadge(row.booking)
                        )}
                      </TableCell>
                      <TableCell className="text-right text-green-600">{amountLabel}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={(event) => {
                              event.stopPropagation();
                              void openChatForBooking(row.booking.id);
                            }}
                          >
                            Chat
                          </Button>
                          {showDisputeButton && !disputesByBookingId[row.booking.id] && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={(event) => {
                                event.stopPropagation();
                                setDisputeContext({
                                  bookingId: row.booking.id,
                                  toolName: row.booking.listing_title,
                                  rentalPeriod: dateRange,
                                });
                                setDisputeWizardOpen(true);
                              }}
                            >
                              Report issue
                            </Button>
                          )}
                          {canConfirmPickup(row.booking) && (
                            <Button
                              size="sm"
                              onClick={(event) => {
                                event.stopPropagation();
                                handleConfirmPickup(row.booking.id);
                              }}
                              disabled={confirmingPickupId === row.booking.id}
                            >
                              {confirmingPickupId === row.booking.id
                                ? "Confirming..."
                                : "Confirm pickup"}
                            </Button>
                          )}
                          {returnPending && (
                            <Button
                              size="sm"
                              onClick={(event) => {
                                event.stopPropagation();
                                openAfterPhotosDialog(row);
                              }}
                              disabled={
                                afterUploadLoading &&
                                afterPhotosTarget?.booking.id === row.booking.id
                              }
                            >
                              {afterUploadLoading &&
                              afterPhotosTarget?.booking.id === row.booking.id
                                ? "Preparing..."
                                : "Mark returned"}
                            </Button>
                          )}
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(event) => {
                              event.stopPropagation();
                              setSelectedRequest(row);
                            }}
                          >
                            Review
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <DisputeWizard
        open={disputeWizardOpen}
        onOpenChange={(open) => {
          setDisputeWizardOpen(open);
          if (!open) {
            setDisputeContext(null);
          }
        }}
        bookingId={disputeContext?.bookingId ?? null}
        role="owner"
        toolName={disputeContext?.toolName}
        rentalPeriodLabel={disputeContext?.rentalPeriod}
      />

      <Dialog open={Boolean(selectedRequest)} onOpenChange={(open) => !open && setSelectedRequest(null)}>
        <DialogContent className="sm:max-w-lg">
          {selectedRequest && (
            <>
              <DialogHeader>
                <DialogTitle>Booking Request Details</DialogTitle>
                <DialogDescription>Review the booking request information</DialogDescription>
              </DialogHeader>

              <div className="space-y-6 py-4">
                <div className="flex items-center gap-4">
                  <img
                    src={selectedRequest.listingPhoto || placeholderImage}
                    alt={selectedRequest.booking.listing_title}
                    className="w-20 h-20 rounded-xl object-cover border border-border"
                  />
                  <div className="flex-1">
                    <h3 className="text-[18px] mb-1" style={{ fontFamily: "Manrope" }}>
                      {selectedRequest.booking.listing_title}
                    </h3>
                    <p className="text-muted-foreground">
                      {formatDateRange(selectedRequest.booking.start_date, selectedRequest.booking.end_date)}
                    </p>
                  </div>
                </div>

                <div className="h-px bg-border" />

                <div>
                  <p className="text-sm text-muted-foreground mb-3">Requested by</p>
                  {selectedRenterDetails && (
                    <div className="flex items-center gap-3">
                      <VerifiedAvatar
                        isVerified={selectedRenterDetails.isVerified}
                        className="w-12 h-12"
                      >
                        <AvatarImage
                          src={selectedRenterDetails.avatarUrl}
                          alt={`${selectedRenterDetails.displayName} avatar`}
                        />
                        <AvatarFallback>{selectedRenterDetails.initials}</AvatarFallback>
                      </VerifiedAvatar>
                      <div className="flex-1">
                        <p style={{ fontFamily: "Manrope" }}>{selectedRenterDetails.displayName}</p>
                        <div className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
                          <Star className="w-4 h-4 text-yellow-500 fill-yellow-500" />
                          {typeof selectedRenterDetails.rating === "number" ? (
                            <>
                              <span className="font-medium text-foreground">
                                {selectedRenterDetails.rating.toFixed(1)}
                              </span>
                              <span>/ 5</span>
                            </>
                          ) : (
                            <span>No rating yet</span>
                          )}
                        </div>
                      </div>
                      <Button
                        variant="outline"
                        size="sm"
                        className="ml-auto whitespace-nowrap"
                        onClick={handleViewRenterProfile}
                      >
                        View Profile
                      </Button>
                    </div>
                  )}
                </div>

                <div className="h-px bg-border" />

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Date Range</span>
                    <span>{formatDateRange(selectedRequest.booking.start_date, selectedRequest.booking.end_date)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    {getBookingStatusBadge(selectedRequest.booking)}
                  </div>
                  <div className="h-px bg-border" />
                  {selectedRequest.booking.status === "paid" && (
                    <Alert className="mt-4 border-primary/30 bg-primary/5">
                      <AlertTitle>At pickup</AlertTitle>
                      <AlertDescription>
                        Before handing over the tool, please check that the renter&apos;s government ID matches
                        their profile name.
                      </AlertDescription>
                    </Alert>
                  )}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Rental amount (days × rate)</span>
                      <span className="font-medium">{formatCurrency(rentalBaseAmount, "CAD")}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Owner service fee</span>
                      <span className="font-medium text-muted-foreground">{ownerServiceFeeText}</span>
                    </div>
                  </div>
                  <div className="h-px bg-border" />
                  <div className="flex items-center justify-between">
                    <span className="text-[18px]" style={{ fontFamily: "Manrope" }}>
                      You Receive
                    </span>
                    <span className="text-[20px] text-green-600" style={{ fontFamily: "Manrope" }}>
                      {formatCurrency(selectedOwnerAmount, "CAD")}
                    </span>
                  </div>
                </div>
              </div>

          {renderDialogActions(selectedRequest.booking)}

            </>
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(afterPhotosTarget)}
        onOpenChange={(open) => {
          if (!open && !afterUploadLoading) {
            closeAfterPhotosDialog();
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Mark returned</DialogTitle>
            <DialogDescription>
              Upload after-photos to finish this booking.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {afterPhotosTarget && (
              <p className="text-sm text-muted-foreground">
                {afterPhotosTarget.booking.listing_title} ·{" "}
                {formatDateRange(
                  afterPhotosTarget.booking.start_date,
                  afterPhotosTarget.booking.end_date,
                )}
              </p>
            )}
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onClick={() => afterFileInputRef.current?.click()}
            >
              <p className="font-medium">Click to upload or drag and drop</p>
              <p className="text-sm text-muted-foreground">
                PNG, JPG or WEBP (max. 15MB each)
              </p>
              <input
                ref={afterFileInputRef}
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={handleAfterPhotoInput}
                disabled={afterUploadLoading}
              />
            </div>

            {afterPhotosFiles.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {afterPhotosFiles.map((upload, index) => (
                  <div
                    key={`${upload.file.name}-${index}`}
                    className="relative aspect-square rounded-lg overflow-hidden bg-muted"
                  >
                    <img
                      src={upload.previewUrl}
                      alt={`After photo ${index + 1}`}
                      className="w-full h-full object-cover"
                    />
                    <button
                      type="button"
                      className="absolute top-2 right-2 w-7 h-7 rounded-full bg-destructive text-white flex items-center justify-center"
                      onClick={() => removeAfterPhoto(index)}
                      disabled={afterUploadLoading}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {afterUploadError && (
              <p className="text-sm text-destructive">{afterUploadError}</p>
            )}
          </div>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={closeAfterPhotosDialog}
              disabled={afterUploadLoading}
            >
              Cancel
            </Button>
            <Button
              onClick={handleAfterPhotosSubmit}
              disabled={afterUploadLoading || afterPhotosFiles.length === 0}
            >
              {afterUploadLoading ? "Uploading..." : "Upload & finish"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog
        open={chatConversationId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setChatConversationId(null);
          }
        }}
      >
        <DialogContent className="max-w-3xl w-full gap-0 p-0">
          {chatConversationId && <ChatMessages conversationId={chatConversationId} />}
        </DialogContent>
      </Dialog>
      <ReviewModal
        open={ownerReviewTarget !== null}
        role="owner_to_renter"
        bookingId={ownerReviewTarget?.bookingId ?? 0}
        otherPartyName={ownerReviewTarget?.renterName ?? ""}
        onClose={() => setOwnerReviewTarget(null)}
        onSubmitted={() => {
          toast.success("Thanks for reviewing your renter.");
        }}
      />
    </div>
    <PolicyConfirmationModal
      open={policyModalOpen}
      roleLabel="owner"
      checkboxChecked={policyAcknowledged}
      onCheckboxChange={(checked) => setPolicyAcknowledged(checked)}
      onConfirm={confirmPolicyAndApprove}
      onCancel={closePolicyModal}
      confirmDisabled={actionLoading}
    />
      <Dialog
        open={Boolean(cancelConfirm)}
        onOpenChange={(open) => {
          if (!open && !cancelConfirm?.loading) {
            setCancelConfirm(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel booking?</DialogTitle>
            <DialogDescription>{cancelConfirm?.warning}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => {
                if (!cancelConfirm?.loading) {
                  setCancelConfirm(null);
                }
              }}
              disabled={cancelConfirm?.loading}
            >
              Go back
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmOwnerCancel}
              disabled={cancelConfirm?.loading}
            >
              {cancelConfirm?.loading ? "Canceling..." : "Yes, cancel booking"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
