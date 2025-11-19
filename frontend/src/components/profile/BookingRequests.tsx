import { useEffect, useMemo, useState } from "react";
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
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Star } from "lucide-react";
import { format } from "date-fns";
import { AuthStore } from "@/lib/auth";
import {
  bookingsAPI,
  deriveDisplayRentalStatus,
  listingsAPI,
  type Booking,
  type BookingTotals,
  type Listing,
} from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { PolicyConfirmationModal } from "../PolicyConfirmationModal";

type RequestStatus = "pending" | "approved" | "denied";
type StatusFilter = "all" | RequestStatus;

interface BookingRequestRow {
  booking: Booking;
  listingPhoto?: string;
  listingCity?: string;
}

export interface BookingRequestsProps {
  onPendingCountChange?: (count: number) => void;
}

const requestStatusLabel: Record<RequestStatus, string> = {
  pending: "pending",
  approved: "approved",
  denied: "denied",
};

const bookingStatusToRequestStatus = (status: Booking["status"]): RequestStatus => {
  switch (status) {
    case "confirmed":
    case "completed":
    case "paid":
      return "approved";
    case "canceled":
      return "denied";
    default:
      return "pending";
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

const parseLocalDate = (isoDate: string) => {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) {
    throw new Error("invalid date");
  }
  return new Date(year, month - 1, day);
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

  useEffect(() => {
    let active = true;
    if (!currentUserId) {
      setError("Please sign in to see booking requests.");
      setLoading(false);
      return;
    }
    setLoading(true);
    const loadData = async () => {
      try {
        const [bookings, listingsResponse] = await Promise.all([
          bookingsAPI.listMine(),
          listingsAPI.mine(),
        ]);
        if (!active) return;
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
        if (!active) return;
        setError("Could not load booking requests. Please try again.");
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadData();
    return () => {
      active = false;
    };
  }, [currentUserId]);

  const filteredRequests = useMemo(() => {
    if (statusFilter === "all") {
      return requests;
    }
    return requests.filter((row) => bookingStatusToRequestStatus(row.booking.status) === statusFilter);
  }, [requests, statusFilter]);

  const selectedRenterDetails = useMemo(() => {
    if (!selectedRequest) {
      return null;
    }
    const renterFirstName = selectedRequest.booking.renter_first_name?.trim() ?? "";
    const renterLastName = selectedRequest.booking.renter_last_name?.trim() ?? "";
    const renterUsername = selectedRequest.booking.renter_username ?? "";
    const renterDisplayName =
      [renterFirstName, renterLastName].filter(Boolean).join(" ") ||
      renterUsername ||
      `Renter #${selectedRequest.booking.renter}`;
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

  const pendingRequests = requests.filter(
    (row) => bookingStatusToRequestStatus(row.booking.status) === "pending",
  ).length;

  useEffect(() => {
    if (onPendingCountChange) {
      onPendingCountChange(pendingRequests);
    }
  }, [pendingRequests, onPendingCountChange]);

  const renderDialogActions = (booking: Booking) => {
    const requestStatus = bookingStatusToRequestStatus(booking.status);
    const canCancelAfterApproval = booking.status === "confirmed" || booking.status === "paid";

    if (requestStatus === "pending") {
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
          <Button
            variant="outline"
            onClick={() => openOwnerCancelDialog(booking)}
            className="rounded-full"
          >
            Cancel Booking
          </Button>
        </DialogFooter>
      );
    }

    return (
      <div className="text-center py-2">
        <p className="text-muted-foreground">
          This request has been {requestStatusLabel[requestStatus]}.
        </p>
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
            <SelectItem value="all">All Status</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="approved">Approved</SelectItem>
            <SelectItem value="denied">Denied</SelectItem>
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
                  const status = bookingStatusToRequestStatus(row.booking.status);
                  const totals: BookingTotals = row.booking.totals ?? {};
                  const amountRaw = Number(
                    totals.owner_payout ?? totals.rental_subtotal ?? totals.total_charge ?? 0,
                  );
                  const amountLabel = formatCurrency(amountRaw, "CAD");
                  const dateRange = formatDateRange(row.booking.start_date, row.booking.end_date);

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
                      <TableCell>{getBookingStatusBadge(row.booking)}</TableCell>
                      <TableCell className="text-right text-green-600">{amountLabel}</TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
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
                      <Avatar className="w-12 h-12">
                        <AvatarImage
                          src={selectedRenterDetails.avatarUrl}
                          alt={`${selectedRenterDetails.displayName} avatar`}
                        />
                        <AvatarFallback>{selectedRenterDetails.initials}</AvatarFallback>
                      </Avatar>
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
