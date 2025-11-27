import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "../ui/tooltip";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { AuthStore } from "@/lib/auth";
import {
  bookingsAPI,
  deriveDisplayRentalStatus,
  deriveRentalAmounts,
  deriveRentalDirection,
  getBookingDamageDeposit,
  listingsAPI,
  type Booking,
  type Listing,
  type DisplayRentalStatus,
  type RentalDirection,
} from "@/lib/api";
import { startEventStream, type EventEnvelope } from "@/lib/events";
import { formatCurrency } from "@/lib/utils";

type StatusFilter = "all" | "active" | "completed";
type TypeFilter = "all" | "earned" | "spent";

interface RentalRow {
  id: number;
  toolName: string;
  rentalPeriod: string;
  status: DisplayRentalStatus | "Denied";
  amount: number;
  depositHold: number;
  type: RentalDirection;
  statusRaw: Booking["status"];
  listingSlug: string | null;
}

const parseLocalDate = (isoDate: string) => {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) {
    throw new Error("invalid date");
  }
  return new Date(year, month - 1, day);
};

function formatDateRange(start: string, end: string) {
  try {
    const startDate = parseLocalDate(start);
    const rawEndDate = parseLocalDate(end);
    if (isNaN(startDate.getTime()) || isNaN(rawEndDate.getTime())) {
      return `${start} - ${end}`;
    }
    const endDate = new Date(rawEndDate);
    endDate.setDate(endDate.getDate() - 1);
    if (endDate.getTime() < startDate.getTime()) {
      endDate.setTime(startDate.getTime());
    }
    const sameYear = startDate.getFullYear() === endDate.getFullYear();
    const startPattern = sameYear ? "MMM d" : "MMM d, yyyy";
    return `${format(startDate, startPattern)} - ${format(endDate, "MMM d, yyyy")}`;
  } catch {
    return `${start} - ${end}`;
  }
}

export function RecentRentals() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const currentUserId = AuthStore.getCurrentUser()?.id ?? null;
  const navigate = useNavigate();
  const listingCacheRef = useRef<Map<string, Listing | null>>(new Map());
  const isMountedRef = useRef(true);

  const reloadRecentRentals = useCallback(async () => {
    if (!currentUserId) {
      setError("Please sign in to see your rentals.");
      setLoading(false);
      setBookings([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await bookingsAPI.listMine();
      if (!isMountedRef.current) {
        return;
      }
      setBookings(Array.isArray(data) ? data : []);
    } catch (err) {
      if (!isMountedRef.current) {
        return;
      }
      setError("Could not load your rentals. Please try again.");
    } finally {
      if (!isMountedRef.current) {
        return;
      }
      setLoading(false);
    }
  }, [currentUserId]);

  useEffect(() => {
    void reloadRecentRentals();
    return () => {
      isMountedRef.current = false;
    };
  }, [reloadRecentRentals]);

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
            event.type === "booking:review_invite" ||
            event.type === "booking:return_requested"
          ) {
            shouldReload = true;
          }
        }
        if (shouldReload) {
          void reloadRecentRentals();
        }
      },
    });

    return () => {
      handle.stop();
    };
  }, [currentUserId, reloadRecentRentals]);

  const rentals = useMemo<RentalRow[]>(() => {
    if (!currentUserId) return [];
    return bookings
      .filter((booking) => booking.status === "completed" || booking.status === "canceled")
      .map((booking) => {
        const direction = deriveRentalDirection(currentUserId, booking);
        const normalizedStatus = (booking.status || "").toLowerCase();
        const displayStatus =
          normalizedStatus === "canceled" && direction === "spent"
            ? "Denied"
            : deriveDisplayRentalStatus(booking);
        const amount = deriveRentalAmounts(direction, booking);
        const depositHold = direction === "spent" ? getBookingDamageDeposit(booking) : 0;
        return {
          id: booking.id,
          toolName: booking.listing_title,
          rentalPeriod: formatDateRange(booking.start_date, booking.end_date),
          status: displayStatus,
          amount,
          depositHold,
          type: direction,
          statusRaw: booking.status,
          listingSlug: booking.listing_slug ?? null,
        };
      });
  }, [bookings, currentUserId]);

  const filteredRentals = useMemo(() => {
    return rentals.filter((rental) => {
      if (statusFilter === "completed") {
        if (rental.statusRaw !== "completed" && rental.statusRaw !== "canceled") {
          return false;
        }
      }

      if (typeFilter !== "all" && rental.type !== typeFilter) {
        return false;
      }
      return true;
    });
  }, [rentals, statusFilter, typeFilter]);

  const navigateToListing = async (slug?: string | null) => {
    if (!slug) {
      toast.error("This booking was deleted.");
      return;
    }
    const cached = listingCacheRef.current.get(slug);
    if (cached === null) {
      toast.error("This booking was deleted.");
      return;
    }
    try {
      const listing = cached ?? (await listingsAPI.retrieve(slug));
      listingCacheRef.current.set(slug, listing);
      navigate(`/listings/${slug}`, { state: { listing } });
    } catch {
      listingCacheRef.current.set(slug, null);
      toast.error("This booking was deleted.");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-3xl">Recent Rentals</h1>
          <p className="mt-2 text-muted-foreground">Track your rental history</p>
        </div>
        <div className="flex gap-3 flex-wrap">
          <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
            </SelectContent>
          </Select>
          <Select value={typeFilter} onValueChange={(value) => setTypeFilter(value as TypeFilter)}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="earned">Earned</SelectItem>
              <SelectItem value="spent">Spent</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {error && (
        <Card>
          <CardContent className="py-4">
            <p className="text-sm text-destructive">{error}</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Rental History</CardTitle>
          <CardDescription>Your recent rental activity</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tool Name</TableHead>
                <TableHead>Rental Period</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    Loading your rentals...
                  </TableCell>
                </TableRow>
              )}
              {!loading && error && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-destructive">
                    {error}
                  </TableCell>
                </TableRow>
              )}
              {!loading && !error && filteredRentals.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                    You don't have any rentals yet.
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                filteredRentals.map((rental) => (
                  <TableRow
                    key={rental.id}
                    onClick={() => {
                      void navigateToListing(rental.listingSlug);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        void navigateToListing(rental.listingSlug);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    className="cursor-pointer"
                  >
                    <TableCell className="font-medium">{rental.toolName}</TableCell>
                    <TableCell>{rental.rentalPeriod}</TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          rental.status === "Completed"
                            ? "secondary"
                            : rental.status === "Canceled"
                            ? "outline"
                            : rental.status === "Denied"
                            ? "outline"
                            : "default"
                        }
                      >
                        {rental.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex flex-col items-end gap-1">
                        <span className={rental.type === "earned" ? "text-green-600" : ""}>
                          {rental.type === "earned" ? "+" : "-"}
                          {formatCurrency(Math.abs(rental.amount))}
                        </span>
                        {rental.type === "spent" && rental.depositHold > 0 && (
                          <span className="text-xs text-muted-foreground">
                            Hold {formatCurrency(rental.depositHold)}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(event) => {
                              event.stopPropagation();
                              alert("Issue reporting will be available after 24 hours from booking end.");
                            }}
                            onKeyDown={(event) => event.stopPropagation()}
                          >
                            Report an Issue
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent side="top">
                          Issue can be reported only 24 hours after the end of booking.
                        </TooltipContent>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
