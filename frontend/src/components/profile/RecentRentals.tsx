import { ChangeEvent, useEffect, useMemo, useState } from "react";
import { format } from "date-fns";
import { CardElement, useElements, useStripe } from "@stripe/react-stripe-js";
import type { StripeCardElementOptions } from "@stripe/stripe-js";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Checkbox } from "../ui/checkbox";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Separator } from "../ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { ArrowLeft, CreditCard } from "lucide-react";
import { toast } from "sonner";
import { AuthStore } from "@/lib/auth";
import {
  authAPI,
  bookingsAPI,
  deriveDisplayRentalStatus,
  deriveRentalAmounts,
  deriveRentalDirection,
  type Booking,
  type BookingTotals,
  type DisplayRentalStatus,
  type RentalDirection,
  type JsonError,
} from "@/lib/api";

type StatusFilter = "all" | "active" | "completed";
type TypeFilter = "all" | "earned" | "spent";

interface RentalRow {
  id: number;
  toolName: string;
  rentalPeriod: string;
  status: DisplayRentalStatus | "Denied";
  amount: number;
  type: RentalDirection;
  isPayable: boolean;
  rentalSubtotal: number;
  serviceFee: number;
  damageDeposit: number;
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
  const [payingRental, setPayingRental] = useState<PayableRental | null>(null);
  const [savePaymentMethod, setSavePaymentMethod] = useState(false);
  const [paymentForm, setPaymentForm] = useState<PaymentFormState>(createInitialPaymentForm);
  const currentUser = AuthStore.getCurrentUser();
  const currentUserId = currentUser?.id ?? null;
  const stripe = useStripe();
  const elements = useElements();
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [paymentLoading, setPaymentLoading] = useState(false);
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
    let active = true;
    if (!currentUserId) {
      setError("Please sign in to see your rentals.");
      setLoading(false);
      setBookings([]);
      return () => {
        active = false;
      };
    }

    setLoading(true);
    setError(null);

    bookingsAPI
      .listMine()
      .then((data) => {
        if (!active) return;
        setBookings(Array.isArray(data) ? data : []);
      })
      .catch(() => {
        if (!active) return;
        setError("Could not load your rentals. Please try again.");
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [currentUserId]);

  const rentals = useMemo<RentalRow[]>(() => {
    if (!currentUserId) return [];
    return bookings
      .map((booking) => {
        const direction = deriveRentalDirection(currentUserId, booking);
        const normalizedStatus = (booking.status || "").toLowerCase();
        const displayStatus =
          normalizedStatus === "canceled" && direction === "spent"
            ? "Denied"
            : deriveDisplayRentalStatus(booking);
        const amount = deriveRentalAmounts(direction, booking);
        const totals = booking.totals as BookingTotalsWithBase | null;
        const rentalSubtotal = Number(totals?.rental_subtotal ?? totals?.base_amount ?? 0);
        const serviceFee = Number(totals?.service_fee ?? totals?.renter_fee ?? 0);
        const damageDeposit = Number(totals?.damage_deposit ?? 0);
        return {
          id: booking.id,
          toolName: booking.listing_title,
          rentalPeriod: formatDateRange(booking.start_date, booking.end_date),
          status: displayStatus,
          amount,
          type: direction,
          isPayable: direction === "spent" && booking.status === "confirmed",
          rentalSubtotal,
          serviceFee,
          damageDeposit,
        };
      })
      .filter((row) => {
        return true;
      });
  }, [bookings, currentUserId]);

  const filteredRentals = useMemo(() => {
    return rentals.filter((rental) => {
      if (statusFilter === "active") {
        if (rental.status === "Completed" || rental.status === "Canceled" || rental.status === "Denied") {
          return false;
        }
      } else if (statusFilter === "completed") {
        if (rental.status !== "Completed" && rental.status !== "Denied") {
          return false;
        }
      }

      if (typeFilter !== "all" && rental.type !== typeFilter) {
        return false;
      }
      return true;
    });
  }, [rentals, statusFilter, typeFilter]);

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
        // Non-fatal; future payments will still succeed without cached customer ID.
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

  if (payingRental) {
    const totalAmount =
      payingRental.rentalSubtotal + payingRental.serviceFee + payingRental.damageDeposit;
    const isPaymentDisabled = paymentLoading || !stripe || !elements;

    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={resetPaymentState} className="rounded-full">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to Rentals
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
                    <span className="text-muted-foreground">Rental Amount</span>
                    <span>${payingRental.rentalSubtotal.toFixed(2)}</span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Service Fee</span>
                    <span>${payingRental.serviceFee.toFixed(2)}</span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Damage Deposit</span>
                    <span>${payingRental.damageDeposit.toFixed(2)}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">Refundable upon return</p>

                  <Separator />

                  <div className="flex items-center justify-between text-[18px]">
                    <span style={{ fontFamily: "Manrope" }}>Total Due</span>
                    <span className="text-primary" style={{ fontFamily: "Manrope" }}>
                      ${totalAmount.toFixed(2)}
                    </span>
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
              <SelectItem value="active">Active</SelectItem>
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
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                    Loading your rentals...
                  </TableCell>
                </TableRow>
              )}
              {!loading && error && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-sm text-destructive">
                    {error}
                  </TableCell>
                </TableRow>
              )}
              {!loading && !error && filteredRentals.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                    You don't have any rentals yet.
                  </TableCell>
                </TableRow>
              )}
              {!loading &&
                !error &&
                filteredRentals.map((rental) => (
                  <TableRow key={rental.id}>
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
                      <div className="flex items-center justify-end gap-3">
                        <span className={rental.type === "earned" ? "text-green-600" : ""}>
                          {rental.type === "earned" ? "+" : "-"}${Math.abs(rental.amount).toFixed(2)}
                        </span>
                        {rental.isPayable && (
                          <Button
                            size="sm"
                            className="rounded-full"
                            onClick={() => {
                              if (rental.isPayable) {
                                setPaymentError(null);
                                setPaymentLoading(false);
                                setPaymentForm(createInitialPaymentForm());
                                setPayingRental({
                                  ...rental,
                                  bookingId: rental.id,
                                  rentalSubtotal: rental.rentalSubtotal,
                                  serviceFee: rental.serviceFee,
                                  damageDeposit: rental.damageDeposit,
                                });
                              }
                            }}
                          >
                            Pay
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
