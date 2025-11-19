import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import { CardElement, useElements, useStripe } from "@stripe/react-stripe-js";
import type { StripeCardElementOptions } from "@stripe/stripe-js";
import { ArrowLeft, CreditCard } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { AuthStore } from "@/lib/auth";
import {
  authAPI,
  bookingsAPI,
  deriveDisplayRentalStatus,
  getBookingChargeAmount,
  getBookingDamageDeposit,
  listingsAPI,
  type Booking,
  type BookingTotals,
  type BookingStatus,
  type DisplayRentalStatus,
  type JsonError,
  type Listing,
} from "@/lib/api";
import { formatCurrency, parseMoney } from "@/lib/utils";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Checkbox } from "../ui/checkbox";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Separator } from "../ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";

type StatusFilter = "all" | "requested" | "waiting-payment" | "waiting-pickup" | "ongoing";

interface RentalRow {
  bookingId: number;
  toolName: string;
  rentalPeriod: string;
  statusLabel: DisplayRentalStatus;
  statusRaw: BookingStatus;
  listingSlug: string | null;
  ownerFirstName: string;
  ownerLastName: string;
  ownerUsername: string;
  amountToPay: number;
  rentalSubtotal: number;
  serviceFee: number;
  damageDeposit: number;
  isPayable: boolean;
  isCancelable: boolean;
  primaryPhotoUrl: string;
  startDate: string;
  endDate: string;
}

type PayableRental = RentalRow & {
  bookingId: number;
  rentalSubtotal: number;
  serviceFee: number;
  damageDeposit: number;
};

type PaymentFormState = {
  cardholderName: string;
  postalCode: string;
  city: string;
  province: string;
  country: string;
};

type BookingTotalsWithBase = BookingTotals & { base_amount?: string | number };

const createInitialPaymentForm = (): PaymentFormState => ({
  cardholderName: "",
  postalCode: "",
  city: "",
  province: "",
  country: "CA",
});

const getFirstString = (value: unknown): string | null => {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      if (typeof item === "string") {
        return item;
      }
    }
  }
  return null;
};

function isJsonError(error: unknown): error is JsonError {
  return typeof error === "object" && error !== null && "status" in error && "data" in error;
}

const extractJsonErrorMessage = (error: JsonError): string | null => {
  if (typeof error.data === "string") {
    return error.data;
  }
  if (error.data && typeof error.data === "object") {
    const dataObject = error.data as Record<string, unknown>;
    const detailMessage = getFirstString(dataObject.detail);
    if (detailMessage) {
      return detailMessage;
    }
    const nonFieldError = getFirstString(dataObject.non_field_errors);
    if (nonFieldError) {
      return nonFieldError;
    }
  }
  return null;
};

const placeholderImage = "https://placehold.co/200x200?text=Listing";
const cancelableStatuses: BookingStatus[] = ["requested", "confirmed"];

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
};

const startOfToday = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
};

const matchesStatusFilter = (row: RentalRow, filter: StatusFilter) => {
  if (filter === "all") {
    return true;
  }
  if (filter === "requested") {
    return row.statusRaw === "requested";
  }
  if (filter === "waiting-payment") {
    return row.statusRaw === "confirmed";
  }
  if (row.statusRaw !== "paid") {
    return false;
  }
  try {
    const today = startOfToday();
    const startDate = parseLocalDate(row.startDate);
    const endDate = parseLocalDate(row.endDate);
    if (filter === "waiting-pickup") {
      return today < startDate;
    }
    if (filter === "ongoing") {
      return today >= startDate && today < endDate;
    }
  } catch {
    return false;
  }
  return true;
};

export function YourRentals() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [cancelingId, setCancelingId] = useState<number | null>(null);
  const [payingRental, setPayingRental] = useState<PayableRental | null>(null);
  const [savePaymentMethod, setSavePaymentMethod] = useState(false);
  const [paymentForm, setPaymentForm] = useState<PaymentFormState>(createInitialPaymentForm());
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [paymentLoading, setPaymentLoading] = useState(false);
  const currentUser = AuthStore.getCurrentUser();
  const currentUserId = currentUser?.id ?? null;
  const stripe = useStripe();
  const elements = useElements();
  const navigate = useNavigate();
  const listingCacheRef = useRef<Map<string, Listing | null>>(new Map());
  const cardElementOptions = useMemo<StripeCardElementOptions>(
    () => ({
      hidePostalCode: true,
      style: {
        base: {
          fontSize: "16px",
          color: "#111827",
          fontFamily: "Manrope, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont",
          "::placeholder": {
            color: "#9CA3AF",
          },
        },
        invalid: {
          color: "#EF4444",
        },
      },
    }),
    []
  );

  useEffect(() => {
    if (!currentUserId) {
      setBookings([]);
      setError(null);
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setError(null);
    bookingsAPI
      .listMine()
      .then((data) => {
        if (!active) return;
        const mine = data
          .filter((booking) => booking.renter === currentUserId)
          .sort(
            (a, b) =>
              new Date(b.created_at).getTime() -
              new Date(a.created_at).getTime(),
          );
        setBookings(mine);
      })
      .catch(() => {
        if (!active) return;
        setError("Unable to load your rentals. Please try again.");
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [currentUserId]);

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    const fieldName = name as keyof PaymentFormState;
    setPaymentForm((prev) => ({ ...prev, [fieldName]: value }));
  };

  const resetPaymentState = () => {
    const cardElement = elements?.getElement(CardElement);
    cardElement?.clear();
    setPayingRental(null);
    setPaymentForm(createInitialPaymentForm());
    setSavePaymentMethod(false);
    setPaymentError(null);
    setPaymentLoading(false);
  };

  const handlePayment = async () => {
    if (!payingRental) return;
    if (!stripe || !elements) {
      setPaymentError("Payment form is still loading. Please try again.");
      return;
    }

    const cardElement = elements.getElement(CardElement);
    if (!cardElement) {
      setPaymentError("Payment form is not ready. Please refresh and try again.");
      return;
    }

    setPaymentError(null);
    setPaymentLoading(true);

    const { error, paymentMethod } = await stripe.createPaymentMethod({
      type: "card",
      card: cardElement,
      billing_details: {
        name: paymentForm.cardholderName || undefined,
        address: {
          city: paymentForm.city || undefined,
          postal_code: paymentForm.postalCode || undefined,
          state: paymentForm.province || undefined,
          country: paymentForm.country || undefined,
        },
      },
    });

    if (error || !paymentMethod) {
      setPaymentError(error?.message || "We couldn't verify your card. Please try again.");
      setPaymentLoading(false);
      return;
    }

    try {
      const stripeCustomerId = currentUser?.stripe_customer_id || undefined;
      const updatedBooking = await bookingsAPI.pay(payingRental.bookingId, {
        stripe_payment_method_id: paymentMethod.id,
        stripe_customer_id: stripeCustomerId,
      });
      setBookings((prev) =>
        prev.map((booking) => (booking.id === updatedBooking.id ? updatedBooking : booking))
      );
      try {
        const refreshedProfile = await authAPI.me();
        AuthStore.setCurrentUser(refreshedProfile);
      } catch {
        // Non-fatal if profile refresh fails.
      }
      toast.success("Payment successful!");
      resetPaymentState();
    } catch (err) {
      const message = isJsonError(err)
        ? extractJsonErrorMessage(err) ?? "Payment could not be completed. Please try again."
        : "Payment could not be completed. Please try again.";
      setPaymentError(message);
    } finally {
      setPaymentLoading(false);
    }
  };

  const rentalRows = useMemo<RentalRow[]>(() => {
    return bookings
      .filter(
        (booking) => booking.status !== "canceled" && booking.status !== "completed",
      )
      .map((booking) => {
        const totals = booking.totals as BookingTotalsWithBase | null;
        let rentalSubtotal = parseMoney(totals?.rental_subtotal ?? totals?.base_amount ?? 0);
        const rawServiceFee = parseMoney(totals?.service_fee ?? totals?.renter_fee ?? 0);
        const amountToPay = getBookingChargeAmount(booking);
        if (!rentalSubtotal && amountToPay && rawServiceFee && amountToPay >= rawServiceFee) {
          rentalSubtotal = Math.max(amountToPay - rawServiceFee, 0);
        }
        const serviceFee =
          rawServiceFee || Math.max(amountToPay - rentalSubtotal, 0);
        const damageDeposit = getBookingDamageDeposit(booking);
        const ownerFirstName = booking.listing_owner_first_name?.trim() || "";
        const ownerLastName = booking.listing_owner_last_name?.trim() || "";
        const ownerUsername = booking.listing_owner_username?.trim() || "";
        return {
          bookingId: booking.id,
          toolName: booking.listing_title,
          rentalPeriod: formatDateRange(booking.start_date, booking.end_date),
          statusLabel: deriveDisplayRentalStatus(booking),
          statusRaw: booking.status,
          listingSlug: booking.listing_slug ?? null,
          ownerFirstName,
          ownerLastName,
          ownerUsername,
          amountToPay,
          rentalSubtotal,
          serviceFee,
          damageDeposit,
          isPayable: booking.status === "confirmed",
          isCancelable: cancelableStatuses.includes(booking.status),
          primaryPhotoUrl: booking.listing_primary_photo_url || placeholderImage,
          startDate: booking.start_date,
          endDate: booking.end_date,
        };
      });
  }, [bookings]);

  const filteredRows = useMemo(() => {
    return rentalRows.filter((row) => matchesStatusFilter(row, statusFilter));
  }, [rentalRows, statusFilter]);

  const handleCancel = async (bookingId: number) => {
    if (cancelingId === bookingId) {
      return;
    }
    setCancelingId(bookingId);
    try {
      await bookingsAPI.cancel(bookingId);
      setBookings((prev) => prev.filter((booking) => booking.id !== bookingId));
      if (payingRental?.bookingId === bookingId) {
        resetPaymentState();
      }
      toast.success("Booking canceled.");
    } catch {
      toast.error("Unable to cancel this booking right now.");
    } finally {
      setCancelingId(null);
    }
  };

  const handlePickup = (bookingId: number) => {
    const booking = bookings.find((entry) => entry.id === bookingId);
    if (!booking) {
      return;
    }
    toast.info(
      `Pickup instructions for ${booking.listing_title} will be available soon.`,
    );
  };

  const handlePay = (bookingId: number) => {
    const row = rentalRows.find((entry) => entry.bookingId === bookingId);
    if (!row) {
      return;
    }
    setPaymentForm(createInitialPaymentForm());
    setSavePaymentMethod(false);
    setPaymentError(null);
    setPaymentLoading(false);
    setPayingRental({
      ...row,
      bookingId: row.bookingId,
      rentalSubtotal: row.rentalSubtotal,
      serviceFee: row.serviceFee,
      damageDeposit: row.damageDeposit,
    });
  };

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

  const handleRowNavigate = (row: RentalRow) => {
    void navigateToListing(row.listingSlug);
  };

  if (!currentUserId) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Your rentals</h2>
          <p className="text-sm text-muted-foreground">
            Manage your current and upcoming rentals
          </p>
        </div>
        <Card>
          <CardContent className="py-6 text-sm text-muted-foreground">
            Please sign in to see your rentals.
          </CardContent>
        </Card>
      </div>
    );
  }

  if (payingRental) {
    const chargeAmount = payingRental.rentalSubtotal + payingRental.serviceFee;
    const depositHold = payingRental.damageDeposit;
    const estimatedTotal = chargeAmount + depositHold;
    const isPaymentDisabled = paymentLoading || !stripe || !elements;

    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={resetPaymentState} className="rounded-full">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Your rentals
          </Button>
        </div>

        <div>
          <h1 className="text-3xl">Payment</h1>
          <p className="mt-2 text-muted-foreground">
            Complete your payment for {payingRental.toolName}
          </p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CreditCard className="h-5 w-5" />
                  Payment Method
                </CardTitle>
                <CardDescription>Enter your card details</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="cardholderName">Cardholder Name</Label>
                  <Input
                    id="cardholderName"
                    name="cardholderName"
                    value={paymentForm.cardholderName}
                    onChange={handleInputChange}
                    placeholder="John Doe"
                    className="rounded-xl"
                  />
                </div>

                <div className="space-y-2">
                  <Label>Card Details</Label>
                  <div className="rounded-xl border border-input bg-background px-3 py-3 focus-within:ring-2 focus-within:ring-ring transition-shadow">
                    <CardElement options={cardElementOptions} />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Billing Address</CardTitle>
                <CardDescription>Enter your billing information</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="city">City</Label>
                    <Input
                      id="city"
                      name="city"
                      value={paymentForm.city}
                      onChange={handleInputChange}
                      placeholder="Edmonton"
                      className="rounded-xl"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="postalCode">Postal Code</Label>
                    <Input
                      id="postalCode"
                      name="postalCode"
                      value={paymentForm.postalCode}
                      onChange={handleInputChange}
                      placeholder="T5K 2J8"
                      className="rounded-xl"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="province">Province</Label>
                    <Input
                      id="province"
                      name="province"
                      value={paymentForm.province}
                      onChange={handleInputChange}
                      placeholder="Alberta"
                      className="rounded-xl"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="country">Country</Label>
                    <Select
                      value={paymentForm.country}
                      onValueChange={(value) =>
                        setPaymentForm((prev) => ({ ...prev, country: value }))
                      }
                    >
                      <SelectTrigger className="rounded-xl">
                        <SelectValue placeholder="Country" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="CA">Canada</SelectItem>
                        <SelectItem value="US">United States</SelectItem>
                        <SelectItem value="MX">Mexico</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <Separator className="my-4" />

                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="savePayment"
                    checked={savePaymentMethod}
                    onCheckedChange={(checked) => setSavePaymentMethod(checked === true)}
                  />
                  <Label htmlFor="savePayment" className="cursor-pointer text-sm">
                    Save payment method for future use
                  </Label>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card className="sticky top-24">
              <CardHeader>
                <CardTitle>Payment Summary</CardTitle>
                <CardDescription>{payingRental.toolName}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Rental Period</span>
                    <span className="text-sm">{payingRental.rentalPeriod}</span>
                  </div>

                  <Separator />

                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Rental amount</span>
                    <span>{formatCurrency(payingRental.rentalSubtotal)}</span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Service fee</span>
                    <span>{formatCurrency(payingRental.serviceFee)}</span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Damage deposit hold</span>
                    <span>{formatCurrency(depositHold)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">Refundable upon return</p>

                  <Separator />

                  <div className="flex items-center justify-between text-[18px]">
                    <span style={{ fontFamily: "Manrope" }}>Charge today</span>
                    <span className="text-primary" style={{ fontFamily: "Manrope" }}>
                      {formatCurrency(chargeAmount)}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>Estimated authorization</span>
                    <span>{formatCurrency(estimatedTotal)}</span>
                  </div>
                </div>

                <Separator className="my-6" />

                <div className="space-y-3">
                  <Button
                    onClick={handlePayment}
                    className="w-full rounded-full"
                    size="lg"
                    disabled={isPaymentDisabled}
                  >
                    {paymentLoading ? "Processing..." : "Complete Payment"}
                  </Button>
                  <Button
                    onClick={resetPaymentState}
                    variant="outline"
                    className="w-full rounded-full"
                  >
                    Cancel
                  </Button>
                  {paymentError && (
                    <p className="text-sm text-destructive text-center">{paymentError}</p>
                  )}
                </div>

                <p className="mt-4 text-center text-xs text-muted-foreground">
                  Your payment is secured with 256-bit SSL encryption
                </p>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    );
  }


  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Your rentals</h2>
          <p className="text-sm text-muted-foreground">
            Manage your current and upcoming rentals
          </p>
        </div>
        <div className="flex gap-3">
          <Select
            value={statusFilter}
            onValueChange={(value) => setStatusFilter(value as StatusFilter)}
          >
            <SelectTrigger className="w-[200px]">
              <SelectValue placeholder="Filter status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="requested">Requested</SelectItem>
              <SelectItem value="waiting-payment">Waiting payment</SelectItem>
              <SelectItem value="waiting-pickup">Waiting pickup</SelectItem>
              <SelectItem value="ongoing">Ongoing</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card>
        <CardContent className="pr-2 pl-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tool</TableHead>
                <TableHead>Date range</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Charge today</TableHead>
                <TableHead className="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-8 text-center text-sm text-muted-foreground"
                  >
                    Loading your rentals...
                  </TableCell>
                </TableRow>
              )}
              {!loading && error && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-8 text-center text-sm text-destructive"
                  >
                    {error}
                  </TableCell>
                </TableRow>
              )}
              {!loading && !error && filteredRows.length === 0 && (
                <TableRow>
                  <TableCell
                    colSpan={6}
                    className="py-8 text-center text-sm text-muted-foreground"
                  >
                    You don&apos;t have any active rentals yet.
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                filteredRows.map((row) => (
                  <TableRow
                    key={row.bookingId}
                    onClick={() => handleRowNavigate(row)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleRowNavigate(row);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                    className="cursor-pointer [&>td]:py-4"
                  >
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <img
                          src={row.primaryPhotoUrl}
                          alt={row.toolName}
                          className="h-12 w-12 rounded-lg object-cover"
                        />
                        <div className="font-normal">{row.toolName}</div>
                      </div>
                    </TableCell>
                    <TableCell>{row.rentalPeriod}</TableCell>
                    <TableCell>
                      <div className="flex flex-col leading-tight text-sm">
                        <span className="font-normal">
                          {row.ownerFirstName || row.ownerUsername || "Unknown owner"}
                        </span>
                        <span className="text-muted-foreground">
                          {row.ownerLastName || "\u00A0"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge
                        variant={
                          row.statusRaw === "completed"
                            ? "secondary"
                            : row.statusRaw === "canceled"
                            ? "outline"
                            : "default"
                        }
                      >
                        {row.statusLabel}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1">
                        <span>{formatCurrency(row.amountToPay)}</span>
                        {row.damageDeposit > 0 && (
                          <span className="text-xs text-muted-foreground">
                            Hold {formatCurrency(row.damageDeposit)}
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-2">
                        {row.isPayable && (
                          <Button
                            size="sm"
                            onClick={(event) => {
                              event.stopPropagation();
                              handlePay(row.bookingId);
                            }}
                          >
                            Pay
                          </Button>
                        )}
                        {row.statusRaw === "paid" && (
                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={(event) => {
                              event.stopPropagation();
                              handlePickup(row.bookingId);
                            }}
                          >
                            Pick up
                          </Button>
                        )}
                        {row.isCancelable && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(event) => {
                              event.stopPropagation();
                              handleCancel(row.bookingId);
                            }}
                            disabled={cancelingId === row.bookingId}
                          >
                            {cancelingId === row.bookingId ? "Canceling..." : "Cancel"}
                          </Button>
                        )}
                      </div>
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
