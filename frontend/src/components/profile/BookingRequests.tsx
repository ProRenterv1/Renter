import { useEffect, useMemo, useState } from "react";
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
import { format } from "date-fns";
import { AuthStore } from "@/lib/auth";
import { bookingsAPI, listingsAPI, type Booking } from "@/lib/api";
import { formatCurrency } from "@/lib/utils";

type RequestStatus = "pending" | "approved" | "denied";
type StatusFilter = "all" | RequestStatus;

interface BookingRequestRow {
  booking: Booking;
  listingPhoto?: string;
  listingCity?: string;
}

const statusClasses: Record<RequestStatus, string> = {
  pending: "bg-warning-bg text-warning-text",
  approved: "bg-success-bg text-success-text",
  denied: "bg-destructive-bg text-destructive-text",
};

const statusLabel: Record<RequestStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  denied: "Denied",
};

const bookingStatusToRequestStatus = (status: Booking["status"]): RequestStatus => {
  switch (status) {
    case "confirmed":
    case "completed":
      return "approved";
    case "canceled":
      return "denied";
    default:
      return "pending";
  }
};

const formatDateRange = (start: string, end: string) => {
  try {
    const startDate = new Date(start);
    const endDate = new Date(end);
    return `${format(startDate, "MMM d")} - ${format(endDate, "MMM d, yyyy")}`;
  } catch {
    return `${start} - ${end}`;
  }
};

const placeholderImage = "https://placehold.co/200x200?text=Listing";

export function BookingRequests() {
  const [requests, setRequests] = useState<BookingRequestRow[]>([]);
  const [selectedRequest, setSelectedRequest] = useState<BookingRequestRow | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);
  const currentUserId = AuthStore.getCurrentUser()?.id ?? null;

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

  const getStatusBadge = (status: RequestStatus) => (
    <Badge variant="outline" className={statusClasses[status]}>
      {statusLabel[status]}
    </Badge>
  );

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

  const handleApprove = async () => {
    if (!selectedRequest) return;
    setActionLoading(true);
    try {
      const updated = await bookingsAPI.confirm(selectedRequest.booking.id);
      updateBookingInState(updated);
    } catch (err) {
      setError("Could not approve this booking. Please try again.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleDeny = async () => {
    if (!selectedRequest) return;
    setActionLoading(true);
    try {
      const updated = await bookingsAPI.cancel(selectedRequest.booking.id);
      updateBookingInState(updated);
    } catch (err) {
      setError("Could not deny this booking. Please try again.");
    } finally {
      setActionLoading(false);
    }
  };

  const pendingRequests = requests.filter(
    (row) => bookingStatusToRequestStatus(row.booking.status) === "pending",
  ).length;

  return (
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
                  const amountRaw = Number(row.booking.totals?.rental_subtotal ?? row.booking.totals?.total_charge ?? 0);
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
                      <TableCell>{getStatusBadge(status)}</TableCell>
                      <TableCell className="text-right text-green-600">{amountLabel}</TableCell>
                      <TableCell className="text-right">
                        <Button variant="outline" size="sm" onClick={() => setSelectedRequest(row)}>
                          Review
                        </Button>
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
                  <div className="flex items-center gap-3">
                    <Avatar className="w-12 h-12">
                      <AvatarImage src="" alt="Renter avatar" />
                      <AvatarFallback>
                        {String(selectedRequest.booking.renter ?? "R").slice(0, 2).toUpperCase()}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                      <p style={{ fontFamily: "Manrope" }}>Renter #{selectedRequest.booking.renter}</p>
                      <p className="text-sm text-muted-foreground">
                        Contact details are shared after approval.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="h-px bg-border" />

                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Date Range</span>
                    <span>{formatDateRange(selectedRequest.booking.start_date, selectedRequest.booking.end_date)}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    {getStatusBadge(bookingStatusToRequestStatus(selectedRequest.booking.status))}
                  </div>
                  <div className="h-px bg-border" />
                  <div className="flex items-center justify-between">
                    <span className="text-[18px]" style={{ fontFamily: "Manrope" }}>
                      You Receive
                    </span>
                    <span className="text-[20px] text-green-600" style={{ fontFamily: "Manrope" }}>
                      {formatCurrency(
                        Number(
                          selectedRequest.booking.totals?.rental_subtotal ??
                            selectedRequest.booking.totals?.total_charge ??
                            0,
                        ),
                        "CAD",
                      )}
                    </span>
                  </div>
                </div>
              </div>

              {bookingStatusToRequestStatus(selectedRequest.booking.status) === "pending" ? (
                <DialogFooter className="gap-2 sm:gap-0">
                  <Button
                    variant="outline"
                    onClick={handleDeny}
                    className="rounded-full"
                    disabled={actionLoading}
                  >
                    {actionLoading ? "Processing..." : "Deny Booking"}
                  </Button>
                  <Button onClick={handleApprove} className="rounded-full" disabled={actionLoading}>
                    {actionLoading ? "Processing..." : "Approve Booking"}
                  </Button>
                </DialogFooter>
              ) : (
                <div className="text-center py-2">
                  <p className="text-muted-foreground">
                    This request has been {bookingStatusToRequestStatus(selectedRequest.booking.status)}.
                  </p>
                </div>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
