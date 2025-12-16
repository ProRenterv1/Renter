import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { addDays, format, parse } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "../../components/ui/drawer";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { Skeleton } from "../../components/ui/skeleton";
import { Search, ExternalLink, AlertTriangle, AlertCircle } from "lucide-react";
import {
  operatorAPI,
  type OperatorBookingListItem,
  type OperatorBookingListParams,
} from "../api";

const DATE_ONLY_REGEX = /^\d{4}-\d{2}-\d{2}$/;

function toIsoDate(value: string) {
  if (!value) return undefined;
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return undefined;
  return parsed.toISOString();
}

const parseBookingDate = (value?: string | null) => {
  if (!value) return undefined;
  if (DATE_ONLY_REGEX.test(value)) {
    const parsed = parse(value, "yyyy-MM-dd", new Date());
    return Number.isNaN(parsed.getTime()) ? undefined : parsed;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? undefined : parsed;
};

const displayDate = (value?: string | null, offsetDays = 0) => {
  const parsed = parseBookingDate(value);
  if (!parsed) return value || "—";
  const adjusted = offsetDays ? addDays(parsed, offsetDays) : parsed;
  return format(adjusted, "yyyy-MM-dd");
};

export function BookingsList() {
  const navigate = useNavigate();
  const [searchId, setSearchId] = useState("");
  const [searchListing, setSearchListing] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [overdueOnly, setOverdueOnly] = useState(false);
  const [ownerQuery, setOwnerQuery] = useState("");
  const [renterQuery, setRenterQuery] = useState("");
  const [createdAfter, setCreatedAfter] = useState("");
  const [createdBefore, setCreatedBefore] = useState("");
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [bookings, setBookings] = useState<OperatorBookingListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchBookings = async () => {
      setLoading(true);
      setError(null);
      const params: OperatorBookingListParams = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (overdueOnly) params.overdue = true;
      if (ownerQuery.trim()) params.owner = ownerQuery.trim();
      if (renterQuery.trim()) params.renter = renterQuery.trim();
      if (createdAfter) params.created_at_after = toIsoDate(createdAfter);
      if (createdBefore) params.created_at_before = toIsoDate(createdBefore);
      try {
        const data = await operatorAPI.bookings(params);
        if (cancelled) return;
        const results = Array.isArray((data as any)?.results) ? (data as any).results : data;
        setBookings(Array.isArray(results) ? results : []);
      } catch (err) {
        console.error("Failed to load bookings", err);
        if (!cancelled) setError("Unable to load bookings right now.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    fetchBookings();
    return () => {
      cancelled = true;
    };
  }, [statusFilter, overdueOnly, ownerQuery, renterQuery, createdAfter, createdBefore]);

  const statuses = useMemo(() => {
    const unique = Array.from(new Set(bookings.map((b) => b.status || ""))).filter(Boolean);
    return unique.sort();
  }, [bookings]);

  const filteredBookings = useMemo(() => {
    return bookings.filter((booking) => {
      if (searchId && !String(booking.id).toLowerCase().includes(searchId.toLowerCase())) {
        return false;
      }
      if (
        searchListing &&
        !booking.listing_title.toLowerCase().includes(searchListing.toLowerCase())
      ) {
        return false;
      }
      return true;
    });
  }, [bookings, searchId, searchListing]);

  const handleViewBooking = (bookingId: number) => {
    navigate(`/operator/bookings/${bookingId}`);
  };

  const statusVariant = (status: string) => {
    const s = status.toLowerCase();
    if (s === "completed") return "secondary";
    if (s === "paid" || s === "confirmed") return "default";
    if (s === "canceled") return "outline";
    return "outline";
  };

  const displayStatus = (booking: OperatorBookingListItem) => {
    const status = booking.status?.toLowerCase?.() || "";
    const today = new Date().toISOString().slice(0, 10);
    if (status === "completed") return "Completed";
    if (status === "canceled") return "Canceled";
    if ((booking as any).after_photos_uploaded_at) return "Completed";
    if ((booking as any).returned_by_renter_at || (booking as any).return_confirmed_at) return "Waiting After Photo";
    if (booking.end_date && booking.end_date === today) return "Waiting return";
    if ((booking as any).pickup_confirmed_at) return "In progress";
    if (status === "paid") return "Waiting pick up";
    return booking.status || "Unknown";
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="mb-2">Bookings</h1>
          <p className="text-muted-foreground">View and monitor all rental bookings (Read-only)</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="space-y-2">
              <Label htmlFor="search-id">Search Booking ID</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="search-id"
                  type="text"
                  placeholder="123"
                  value={searchId}
                  onChange={(e) => setSearchId(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="search-listing">Search Listing</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="search-listing"
                  type="text"
                  placeholder="Search listing titles..."
                  value={searchListing}
                  onChange={(e) => setSearchListing(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="status-filter">Status</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger id="status-filter">
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  {statuses.map((status) => (
                    <SelectItem key={status} value={status}>
                      {status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="pt-2">
            <Button variant="outline" size="sm" onClick={() => setAdvancedOpen(true)}>
              Advanced Filters
            </Button>
          </div>

          <div className="pt-4 border-t border-border">
            <p className="text-sm text-muted-foreground">
              Showing {filteredBookings.length} of {bookings.length} bookings
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-border">
                <tr>
                  <th className="text-left p-4 font-medium">Booking ID</th>
                  <th className="text-left p-4 font-medium">Listing</th>
                  <th className="text-left p-4 font-medium">Owner</th>
                  <th className="text-left p-4 font-medium">Renter</th>
                  <th className="text-left p-4 font-medium">Date Range</th>
                  <th className="text-left p-4 font-medium">Status</th>
                  <th className="text-left p-4 font-medium">Total</th>
                  <th className="text-left p-4 font-medium">Flags</th>
                  <th className="text-left p-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={9} className="p-6">
                      <div className="flex gap-3">
                        <Skeleton className="h-12 w-12 rounded" />
                        <Skeleton className="h-12 flex-1" />
                      </div>
                    </td>
                  </tr>
                ) : error ? (
                  <tr>
                    <td colSpan={9} className="p-8 text-center text-muted-foreground">
                      {error}
                    </td>
                  </tr>
                ) : filteredBookings.length > 0 ? (
                  filteredBookings.map((booking) => (
                    <tr
                      key={booking.id}
                      className="border-b border-border hover:bg-muted/50 transition-colors"
                    >
                      <td className="p-4">
                        <div className="font-mono text-sm">{booking.id}</div>
                      </td>
                      <td className="p-4">
                        <div className="font-medium truncate">{booking.listing_title}</div>
                      </td>
                      <td className="p-4">
                        <button
                          onClick={() => navigate(`/operator/users/${booking.owner?.id}`)}
                          className="text-primary hover:underline"
                        >
                          {booking.owner?.name || booking.owner?.email || "Owner"}
                        </button>
                      </td>
                      <td className="p-4">
                        <button
                          onClick={() => navigate(`/operator/users/${booking.renter?.id}`)}
                          className="text-primary hover:underline"
                        >
                          {booking.renter?.name || booking.renter?.email || "Renter"}
                        </button>
                      </td>
                      <td className="p-4">
                        <div className="text-sm">
                          <div>{displayDate(booking.start_date)}</div>
                          <div className="text-muted-foreground">to {displayDate(booking.end_date, -1)}</div>
                        </div>
                      </td>
                      <td className="p-4">
                        <Badge variant={statusVariant(booking.status)}>{displayStatus(booking)}</Badge>
                        {booking.is_overdue && (
                          <Badge variant="destructive" className="ml-2">
                            <AlertTriangle className="w-3 h-3 mr-1" />
                            Overdue
                          </Badge>
                        )}
                      </td>
                      <td className="p-4">${booking.total_charge ?? "—"}</td>
                      <td className="p-4">
                        {booking.is_overdue && (
                          <Badge variant="outline" className="border-orange-500 text-orange-700">
                            <AlertCircle className="w-3 h-3 mr-1" />
                            Overdue
                          </Badge>
                        )}
                      </td>
                      <td className="p-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleViewBooking(booking.id)}
                          className="text-primary"
                        >
                          View <ExternalLink className="w-4 h-4 ml-2" />
                        </Button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9} className="p-8 text-center text-muted-foreground">
                      <div className="flex flex-col items-center gap-2">
                        <AlertCircle className="w-5 h-5" />
                        <p className="m-0">No bookings match your filters.</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      <Drawer direction="right" open={advancedOpen} onOpenChange={setAdvancedOpen}>
        <DrawerContent className="bg-background sm:max-w-md">
          <DrawerHeader>
            <DrawerTitle>Advanced Filters</DrawerTitle>
          </DrawerHeader>
          <div className="p-4 space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="owner-query">Owner (name or email)</Label>
                <Input
                  id="owner-query"
                  type="text"
                  placeholder="Owner name or email"
                  value={ownerQuery}
                  onChange={(e) => setOwnerQuery(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="renter-query">Renter (name or email)</Label>
                <Input
                  id="renter-query"
                  type="text"
                  placeholder="Renter name or email"
                  value={renterQuery}
                  onChange={(e) => setRenterQuery(e.target.value)}
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="created-after">Created After</Label>
                <Input
                  id="created-after"
                  type="date"
                  value={createdAfter}
                  onChange={(e) => setCreatedAfter(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="created-before">Created Before</Label>
                <Input
                  id="created-before"
                  type="date"
                  value={createdBefore}
                  onChange={(e) => setCreatedBefore(e.target.value)}
                />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="overdue-only"
                checked={overdueOnly}
                onChange={(e) => setOverdueOnly(e.target.checked)}
                className="h-4 w-4 rounded border-border text-primary focus:ring-primary"
              />
              <Label htmlFor="overdue-only">Overdue only</Label>
            </div>
          </div>
        </DrawerContent>
      </Drawer>
    </div>
  );
}
