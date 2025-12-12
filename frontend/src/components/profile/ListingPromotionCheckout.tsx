import { useCallback, useEffect, useMemo, useState } from "react";
import { addDays, differenceInCalendarDays, eachDayOfInterval, format, parseISO } from "date-fns";
import { CardElement, useElements, useStripe } from "@stripe/react-stripe-js";
import type { StripeCardElementOptions } from "@stripe/stripe-js";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  paymentsAPI,
  promotionsAPI,
  type Listing,
  type OwnerPayoutSummary,
  type PromotionSlot,
  type PaymentMethod,
} from "@/lib/api";
import { AuthStore } from "@/lib/auth";
import { formatCurrency, parseMoney } from "@/lib/utils";
import { Button } from "../ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Calendar } from "../ui/calendar";
import { Checkbox } from "../ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Separator } from "../ui/separator";

interface ListingPromotionCheckoutProps {
  listing: Listing;
  onBack: () => void;
}

const formatCents = (value: number) => formatCurrency(value / 100, "CAD");

type Step = "schedule" | "payment" | "success";
type PaymentMode = "card" | "earnings";

interface PromotionQuote {
  startDate: string;
  endDate: string;
  durationDays: number;
  baseCents: number;
  gstCents: number;
  totalCents: number;
}

const cardElementOptions: StripeCardElementOptions = {
  hidePostalCode: true,
  style: {
    base: {
      color: "var(--foreground)",
      fontFamily: "Manrope, system-ui, sans-serif",
      fontSize: "16px",
      "::placeholder": {
        color: "var(--muted-foreground)",
      },
    },
    invalid: {
      color: "#ef4444",
    },
  },
};

const createInitialBillingState = () => ({
  cardholderName: "",
  city: "",
  postalCode: "",
  province: "",
  country: "CA",
});

export function ListingPromotionCheckout({ listing, onBack }: ListingPromotionCheckoutProps) {
  const stripe = useStripe();
  const elements = useElements();
  const [step, setStep] = useState<Step>("schedule");
  const today = useMemo(() => {
    const base = new Date();
    base.setHours(0, 0, 0, 0);
    return base;
  }, [listing.id]);
  const [dateRange, setDateRange] = useState<{ from: Date | undefined; to: Date | undefined }>(() => ({
    from: today,
    to: addDays(today, 6),
  }));
  const [blockedDates, setBlockedDates] = useState<Date[]>([]);
  const [isLoadingAvailability, setIsLoadingAvailability] = useState<boolean>(false);
  const [availabilityError, setAvailabilityError] = useState<string | null>(null);
  const [pricePerDayCents, setPricePerDayCents] = useState<number | null>(null);
  const [pricingError, setPricingError] = useState<string | null>(null);
  const [isLoadingPricing, setIsLoadingPricing] = useState<boolean>(true);
  const [checkoutSummary, setCheckoutSummary] = useState<PromotionQuote | null>(null);
  const [paymentForm, setPaymentForm] = useState(createInitialBillingState);
  const [savePaymentMethod, setSavePaymentMethod] = useState(true);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [successSlot, setSuccessSlot] = useState<PromotionSlot | null>(null);
  const [payoutSummary, setPayoutSummary] = useState<OwnerPayoutSummary | null>(null);
  const [availableEarningsCents, setAvailableEarningsCents] = useState<number | null>(null);
  const [paymentMode, setPaymentMode] = useState<PaymentMode>("card");
  const [cardSource, setCardSource] = useState<"new" | "saved">("new");
  const [savedMethods, setSavedMethods] = useState<PaymentMethod[]>([]);
  const [savedMethodsLoading, setSavedMethodsLoading] = useState(false);
  const [savedMethodsError, setSavedMethodsError] = useState<string | null>(null);
  const [selectedSavedMethodId, setSelectedSavedMethodId] = useState<number | null>(null);
  const [earningsError, setEarningsError] = useState<string | null>(null);
  const currentUser = AuthStore.getCurrentUser();

  const loadPricing = useCallback(async () => {
    setIsLoadingPricing(true);
    setPricingError(null);
    try {
      const data = await promotionsAPI.fetchPromotionPricing(listing.id);
      setPricePerDayCents(data?.price_per_day_cents ?? null);
    } catch {
      setPricingError("Failed to load promotion pricing. Please try again.");
      setPricePerDayCents(null);
    } finally {
      setIsLoadingPricing(false);
    }
  }, [listing.id]);

  const loadAvailability = useCallback(async () => {
    setIsLoadingAvailability(true);
    setAvailabilityError(null);
    try {
      const ranges = await promotionsAPI.availability(listing.id);
      const blocked: Date[] = [];
      ranges.forEach((range) => {
        const start = parseISO(range.start_date);
        const end = parseISO(range.end_date);
        if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
          return;
        }
        const days = eachDayOfInterval({ start, end });
        days.forEach((day) => {
          const normalized = new Date(day);
          normalized.setHours(0, 0, 0, 0);
          blocked.push(normalized);
        });
      });
      setBlockedDates(blocked);
    } catch (err) {
      console.error("promotions: failed to load availability", err);
      setBlockedDates([]);
      setAvailabilityError("Unable to load promotion availability.");
    } finally {
      setIsLoadingAvailability(false);
    }
  }, [listing.id]);

  useEffect(() => {
    void loadPricing();
  }, [loadPricing]);

  useEffect(() => {
    setBlockedDates([]);
    void loadAvailability();
  }, [loadAvailability]);

  useEffect(() => {
    setDateRange({
      from: today,
      to: addDays(today, 6),
    });
    setPricingError(null);
    setAvailabilityError(null);
    setStep("schedule");
    setCheckoutSummary(null);
    setSuccessSlot(null);
  }, [listing.id, today]);

  const durationDays = useMemo(() => {
    if (dateRange.from && dateRange.to) {
      const diff = differenceInCalendarDays(dateRange.to, dateRange.from) + 1;
      return diff > 0 ? diff : 0;
    }
    return 0;
  }, [dateRange]);

  const baseCents = pricePerDayCents && durationDays > 0 ? pricePerDayCents * durationDays : 0;
  const gstCents = Math.round(baseCents * 0.05);
  const totalCents = baseCents + gstCents;

  const promotionStart = dateRange.from ? format(dateRange.from, "yyyy-MM-dd") : "";
  const promotionEnd = dateRange.to ? format(dateRange.to, "yyyy-MM-dd") : "";

  const blockedDateSet = useMemo(
    () => new Set(blockedDates.map((day) => format(day, "yyyy-MM-dd"))),
    [blockedDates],
  );

  const isDateBlocked = useCallback(
    (day: Date) => blockedDateSet.has(format(day, "yyyy-MM-dd")),
    [blockedDateSet],
  );

  const selectionHasBlockedDays = useMemo(() => {
    if (!dateRange.from || !dateRange.to) return false;
    try {
      return eachDayOfInterval({ start: dateRange.from, end: dateRange.to }).some((day) =>
        isDateBlocked(day),
      );
    } catch {
      return false;
    }
  }, [dateRange, isDateBlocked]);

  const preferredAvailableString =
    payoutSummary?.balances?.connect_available_earnings ??
    payoutSummary?.balances?.available_earnings;
  const availableEarningsAmount =
    availableEarningsCents !== null
      ? availableEarningsCents / 100
      : preferredAvailableString !== undefined
        ? parseMoney(preferredAvailableString ?? "0")
        : null;
  const availableEarningsDisplay =
    availableEarningsAmount !== null ? formatCurrency(availableEarningsAmount, "CAD") : null;
  const availableEarningsCentsForCheck =
    availableEarningsAmount !== null ? Math.round(availableEarningsAmount * 100) : null;

  const handleRangeSelect = (range: { from?: Date; to?: Date } | undefined) => {
    if (!range) {
      setDateRange({ from: undefined, to: undefined });
      return;
    }
    if (range.from && range.to) {
      try {
        const hasBlocked = eachDayOfInterval({ start: range.from, end: range.to }).some((day) =>
          isDateBlocked(day),
        );
        if (hasBlocked) {
          setPricingError("Some of the selected days are already promoted.");
          toast.error("Some of the selected days are already promoted.");
          return;
        }
      } catch {
        // ignore invalid interval and allow selection reset
      }
    }
    setPricingError(null);
    setDateRange({
      from: range.from,
      to: range.to,
    });
  };

  const handleProceedToPayment = () => {
    if (!dateRange.from || !dateRange.to || durationDays <= 0 || !pricePerDayCents) {
      setPricingError("Please select a valid date range to continue.");
      return;
    }
    if (selectionHasBlockedDays) {
      setPricingError("Some of the selected days are already promoted.");
      toast.error("Some of the selected days are already promoted.");
      return;
    }
    setPaymentMode("card");
    setCardSource("new");
    setSavedMethods([]);
    setSavedMethodsError(null);
    setSelectedSavedMethodId(null);
    setAvailableEarningsCents(null);
    setEarningsError(null);
    setPricingError(null);
    setCheckoutSummary({
      startDate: promotionStart,
      endDate: promotionEnd,
      durationDays,
      baseCents,
      gstCents,
      totalCents,
    });
    setPaymentError(null);
    setStep("payment");
  };

  const handlePaymentInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    setPaymentForm((prev) => ({ ...prev, [name]: value }));
  };

  useEffect(() => {
    if (step !== "payment") {
      setCardSource("new");
      setSavedMethods([]);
      setSavedMethodsError(null);
      setSavedMethodsLoading(false);
      setSelectedSavedMethodId(null);
      return;
    }
    let cancelled = false;

    if (paymentMode === "card") {
      const loadSavedMethods = async () => {
        setSavedMethodsLoading(true);
        setSavedMethodsError(null);
        try {
          const methods = await paymentsAPI.listPaymentMethods();
          if (cancelled) return;
          setSavedMethods(methods);
          const preferred = methods.find((method) => method.is_default) ?? methods[0];
          setSelectedSavedMethodId((prev) => prev ?? preferred?.id ?? null);
          if (methods.length === 0 && cardSource === "saved") {
            setCardSource("new");
          }
        } catch (err) {
          if (cancelled) return;
          console.error("payments: failed to load saved payment methods", err);
          setSavedMethodsError("Saved cards are unavailable right now.");
          setSavedMethods([]);
          setSelectedSavedMethodId(null);
          if (cardSource === "saved") {
            setCardSource("new");
          }
        } finally {
          if (!cancelled) {
            setSavedMethodsLoading(false);
          }
        }
      };
      void loadSavedMethods();
    }

    const loadAvailableEarnings = async () => {
      try {
        const summary = await paymentsAPI.ownerPayoutsSummary();
        if (cancelled) return;
        setPayoutSummary(summary);
        const raw =
          summary.balances?.connect_available_earnings ??
          summary.balances?.available_earnings ??
          "0.00";
        const amount = parseMoney(raw);
        setAvailableEarningsCents(Math.round(amount * 100));
        setEarningsError(null);
      } catch {
        if (!cancelled) {
          setPayoutSummary(null);
          setAvailableEarningsCents(null);
          setEarningsError("Unable to load your available earnings balance.");
        }
      }
    };
    void loadAvailableEarnings();
    return () => {
      cancelled = true;
    };
  }, [step, paymentMode, cardSource]);

  const handlePayment = async () => {
    if (!checkoutSummary) return;

    if (paymentMode === "earnings") {
      setPaymentError(null);
      setPaymentLoading(true);
      try {
        const payload = {
          listing_id: listing.id,
          promotion_start: checkoutSummary.startDate,
          promotion_end: checkoutSummary.endDate,
          base_price_cents: checkoutSummary.baseCents,
          gst_cents: checkoutSummary.gstCents,
          pay_with_earnings: true,
        };
        const response = await promotionsAPI.payPromotion(payload);
        setSuccessSlot(response.slot);
        toast.success("Promotion scheduled using your earnings.");
        setStep("success");
      } catch (err: any) {
        const message =
          (err?.data &&
            typeof err.data === "object" &&
            "detail" in err.data &&
            typeof err.data.detail === "string" &&
            err.data.detail) ||
          "Unable to use your earnings for this promotion. Please try again or use a card.";
        setPaymentError(message);
      } finally {
        setPaymentLoading(false);
      }
      return;
    }

    if (cardSource === "saved") {
      if (!selectedSavedMethodId) {
        setPaymentError("Please select a saved card.");
        return;
      }
      const selected = savedMethods.find((m) => m.id === selectedSavedMethodId);
      if (!selected) {
        setPaymentError("Please select a saved card.");
        return;
      }
      setPaymentError(null);
      setPaymentLoading(true);
      try {
        const payload = {
          listing_id: listing.id,
          promotion_start: checkoutSummary.startDate,
          promotion_end: checkoutSummary.endDate,
          base_price_cents: checkoutSummary.baseCents,
          gst_cents: checkoutSummary.gstCents,
          stripe_payment_method_id: selected.stripe_payment_method_id,
          stripe_customer_id: currentUser?.stripe_customer_id || undefined,
          save_payment_method: false,
          pay_with_earnings: false,
        };
        const response = await promotionsAPI.payPromotion(payload);
        setSuccessSlot(response.slot);
        toast.success("Promotion scheduled!");
        setStep("success");
      } catch (err) {
        const message =
          (typeof err === "object" &&
            err !== null &&
            "status" in err &&
            typeof (err as { data?: unknown }).data === "object" &&
            err.data &&
            typeof (err.data as { detail?: string }).detail === "string" &&
            (err.data as { detail?: string }).detail) ||
          "Payment could not be completed. Please try again.";
        setPaymentError(message);
      } finally {
        setPaymentLoading(false);
      }
      return;
    }

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
          state: paymentForm.province || undefined,
          postal_code: paymentForm.postalCode || undefined,
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
      const payload = {
        listing_id: listing.id,
        promotion_start: checkoutSummary.startDate,
        promotion_end: checkoutSummary.endDate,
        base_price_cents: checkoutSummary.baseCents,
        gst_cents: checkoutSummary.gstCents,
        stripe_payment_method_id: paymentMethod.id,
        stripe_customer_id: currentUser?.stripe_customer_id || undefined,
        save_payment_method: savePaymentMethod,
        pay_with_earnings: false,
      };
      const response = await promotionsAPI.payPromotion(payload);
      if (savePaymentMethod) {
        try {
          await paymentsAPI.addPaymentMethod({ stripe_payment_method_id: paymentMethod.id });
        } catch (saveErr) {
          console.error("payments: failed to save card", saveErr);
          toast.error("Payment succeeded, but we couldn't save this card.");
        }
      }
      setSuccessSlot(response.slot);
      toast.success("Promotion scheduled!");
      setStep("success");
    } catch (err) {
      const message =
        (typeof err === "object" &&
          err !== null &&
          "status" in err &&
          typeof (err as { data?: unknown }).data === "object" &&
          err.data &&
          typeof (err.data as { detail?: string }).detail === "string" &&
          (err.data as { detail?: string }).detail) ||
        "Payment could not be completed. Please try again.";
      setPaymentError(message);
    } finally {
      setPaymentLoading(false);
    }
  };

  const resetPaymentStepState = () => {
    setPaymentError(null);
    setPaymentLoading(false);
    setCardSource("new");
    setSavedMethods([]);
    setSavedMethodsError(null);
    setSelectedSavedMethodId(null);
    setSavePaymentMethod(true);
    setPaymentForm(createInitialBillingState());
  };

  const renderScheduleStep = () => (
    <>
      <div>
        <h1 className="text-3xl">Promote listing</h1>
        <p className="mt-2 text-muted-foreground">Choose when and for how long to boost visibility.</p>
      </div>

      {pricingError && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {pricingError}
        </div>
      )}
      {availabilityError && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {availabilityError}
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>Promotion window</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-muted-foreground">
              <div className="flex flex-wrap items-center justify-between gap-2 text-foreground">
                <span className="font-medium">Listing #{listing.id}</span>
                <span className="text-muted-foreground">{listing.slug}</span>
              </div>
              <div>
                <p className="text-lg font-semibold text-foreground">{listing.title}</p>
                <p>{listing.city || "Unknown location"}</p>
              </div>
              <div className="grid gap-4 text-foreground lg:grid-cols-[minmax(0,1fr)_220px]">
                <div className="rounded-2xl border border-border bg-muted/40 p-4">
                  <Calendar
                    mode="range"
                    numberOfMonths={1}
                    selected={dateRange}
                    onSelect={handleRangeSelect}
                    defaultMonth={dateRange.from ?? today}
                    disabled={(date) => date < today || isDateBlocked(date)}
                  />
                </div>
                <div className="space-y-4 rounded-2xl border border-border bg-muted/20 p-4">
                  <div>
                    <Label className="text-xs uppercase text-muted-foreground">Start date</Label>
                    <p className="text-base font-semibold">
                      {dateRange.from ? format(dateRange.from, "MMM d, yyyy") : "Select a start date"}
                    </p>
                  </div>
                  <div>
                    <Label className="text-xs uppercase text-muted-foreground">End date</Label>
                    <p className="text-base font-semibold">
                      {dateRange.to ? format(dateRange.to, "MMM d, yyyy") : "Select an end date"}
                    </p>
                  </div>
                  <div>
                    <Label className="text-xs uppercase text-muted-foreground">Total days</Label>
                    <p className="text-base font-semibold">
                      {durationDays > 0
                        ? `${durationDays} ${durationDays === 1 ? "day" : "days"}`
                        : "0 days"}
                    </p>
                  </div>
                  {selectionHasBlockedDays && (
                    <p className="text-xs text-destructive">
                      Some of these days are already promoted. Pick a different window.
                    </p>
                  )}
                  {pricePerDayCents && (
                    <p className="text-sm text-muted-foreground">
                      {formatCents(pricePerDayCents)} per day of boosted visibility
                    </p>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Order summary</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              <div className="flex items-center justify-between">
                <span>Promotion ({durationDays || 0} {durationDays === 1 ? "day" : "days"})</span>
                <span>{formatCents(baseCents)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span>GST (5%)</span>
                <span>{formatCents(gstCents)}</span>
              </div>
              <Separator />
              <div className="flex items-center justify-between text-base font-semibold text-foreground">
                <span>Total</span>
                <span>{formatCents(totalCents)}</span>
              </div>
              <Button
                className="w-full rounded-full"
                disabled={
                  !pricePerDayCents ||
                  !dateRange.from ||
                  !dateRange.to ||
                  durationDays <= 0 ||
                  isLoadingPricing ||
                  isLoadingAvailability ||
                  availabilityError !== null ||
                  selectionHasBlockedDays
                }
                onClick={handleProceedToPayment}
              >
                Proceed to payment
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );

  const renderPaymentStep = () => {
    if (!checkoutSummary) return null;
    const chargeAmount = checkoutSummary.baseCents + checkoutSummary.gstCents;
    const canPayWithEarnings =
      !!payoutSummary?.connect?.has_account &&
      !!payoutSummary?.connect?.payouts_enabled &&
      availableEarningsCentsForCheck !== null &&
      availableEarningsCentsForCheck >= chargeAmount;
    const isSavedSource = cardSource === "saved";
    const cardFieldsDisabled = paymentMode !== "card" || isSavedSource;
    const selectedSavedMethod =
      savedMethods.find((method) => method.id === selectedSavedMethodId) ?? null;

    return (
      <>

        <div>
          <h1 className="text-3xl">Promotion payment</h1>
          <p className="mt-2 text-muted-foreground">Complete your payment for {listing.title}</p>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle>How would you like to pay?</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex flex-col gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setPaymentMode("card");
                      setCardSource("new");
                      setPaymentError(null);
                    }}
                    disabled={paymentLoading}
                    className={`rounded-xl border px-4 py-3 text-left transition ${
                      paymentMode === "card"
                        ? "border-primary bg-primary/5 text-foreground"
                        : "border-border bg-background text-foreground/80"
                    } ${paymentLoading ? "pointer-events-none opacity-60" : ""}`}
                  >
                    Pay with card
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setPaymentMode("earnings");
                      setCardSource("new");
                      setPaymentError(null);
                    }}
                    disabled={!canPayWithEarnings || paymentLoading}
                    className={`rounded-xl border px-4 py-3 text-left transition ${
                      paymentMode === "earnings"
                        ? "border-primary bg-primary/5 text-foreground"
                        : "border-border bg-background text-foreground/80"
                    } ${(!canPayWithEarnings || paymentLoading) ? "opacity-60" : ""}`}
                  >
                    <div className="flex flex-col gap-1">
                      <span>Pay with earnings</span>
                      {availableEarningsDisplay && (
                        <span className="text-xs text-muted-foreground">
                          Available {availableEarningsDisplay}
                        </span>
                      )}
                    </div>
                  </button>
                </div>
                {!canPayWithEarnings && availableEarningsDisplay && (
                  <p className="text-xs text-muted-foreground">
                    You currently have {availableEarningsDisplay} in earnings,
                    which is not enough to cover this promotion.
                  </p>
                )}
                {earningsError && <p className="text-xs text-destructive">{earningsError}</p>}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Payment method</CardTitle>
              </CardHeader>
              <CardContent
                className="space-y-4"
              >
                {paymentMode === "card" && (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant={!isSavedSource ? "default" : "outline"}
                      size="sm"
                      className="rounded-full"
                      onClick={() => {
                        setCardSource("new");
                        setPaymentError(null);
                      }}
                      disabled={paymentLoading}
                    >
                      New card
                    </Button>
                    {savedMethods.length > 0 && (
                      <Button
                        variant={isSavedSource ? "default" : "outline"}
                        size="sm"
                        className="rounded-full"
                        onClick={() => {
                          setCardSource("saved");
                          setPaymentError(null);
                        }}
                        disabled={paymentLoading}
                      >
                        Saved card
                      </Button>
                    )}
                  </div>
                )}

                {savedMethodsError && (
                  <p className="text-xs text-destructive">{savedMethodsError}</p>
                )}

                {paymentMode === "card" && isSavedSource && (
                  <div className="space-y-3">
                    {savedMethodsLoading && (
                      <p className="text-sm text-muted-foreground">Loading saved cards...</p>
                    )}
                    {!savedMethodsLoading && savedMethods.length === 0 && (
                      <p className="text-sm text-muted-foreground">No saved cards yet.</p>
                    )}
                    {!savedMethodsLoading &&
                      savedMethods.map((method) => {
                        const isSelected = method.id === selectedSavedMethodId;
                        return (
                          <label
                            key={method.id}
                            className={`flex items-center justify-between rounded-xl border p-3 cursor-pointer transition-colors ${
                              isSelected ? "border-primary bg-primary/5" : "hover:border-primary/60"
                            }`}
                          >
                            <input
                              type="radio"
                              name="saved-promo-payment-method"
                              className="sr-only"
                              checked={isSelected}
                              onChange={() => {
                                setSelectedSavedMethodId(method.id);
                                setPaymentError(null);
                              }}
                            />
                            <div className="flex items-center gap-3">
                              <div className="h-10 w-10 rounded-lg bg-muted flex items-center justify-center">
                                <CreditCard className="h-5 w-5 text-muted-foreground" />
                              </div>
                              <div className="space-y-1">
                                <div className="flex items-center gap-2 text-sm font-medium">
                                  <span>
                                    {method.brand} ending in {method.last4}
                                  </span>
                                  {method.is_default && (
                                    <Badge variant="secondary" className="text-[10px]">
                                      Default
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-xs text-muted-foreground">
                                  Expires {String(method.exp_month ?? "--").padStart(2, "0")}/
                                  {method.exp_year ?? "--"}
                                </p>
                              </div>
                            </div>
                          </label>
                        );
                      })}
                    {!savedMethodsLoading &&
                      savedMethods.length > 0 &&
                      !selectedSavedMethod &&
                      !paymentLoading && (
                        <p className="text-xs text-destructive">
                          Select a saved card to continue.
                        </p>
                      )}
                  </div>
                )}

                <div className="space-y-2">
                  <Label htmlFor="cardholderName">Cardholder name</Label>
                  <Input
                    id="cardholderName"
                    name="cardholderName"
                    value={paymentForm.cardholderName}
                    onChange={handlePaymentInputChange}
                    placeholder="Jane Doe"
                    className="rounded-xl"
                    disabled={cardFieldsDisabled}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Card details</Label>
                  <div className="rounded-xl border border-input bg-background px-3 py-3 focus-within:ring-2 focus-within:ring-ring transition-shadow">
                    <CardElement
                      options={{
                        ...cardElementOptions,
                        disabled: cardFieldsDisabled,
                      }}
                    />
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Billing address</CardTitle>
              </CardHeader>
              <CardContent
                className={`space-y-4 ${
                  cardFieldsDisabled || paymentMode !== "card"
                    ? "opacity-60 pointer-events-none"
                    : ""
                }`}
              >
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="city">City</Label>
                    <Input
                      id="city"
                      name="city"
                      value={paymentForm.city}
                      onChange={handlePaymentInputChange}
                      placeholder="Edmonton"
                      className="rounded-xl"
                      disabled={cardFieldsDisabled}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="postalCode">ZIP / Postal code</Label>
                    <Input
                      id="postalCode"
                      name="postalCode"
                      value={paymentForm.postalCode}
                      onChange={handlePaymentInputChange}
                      placeholder="T5A 0A1"
                      className="rounded-xl"
                      disabled={cardFieldsDisabled}
                    />
                  </div>
                </div>
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="province">Province/State</Label>
                    <Input
                      id="province"
                      name="province"
                      value={paymentForm.province}
                      onChange={handlePaymentInputChange}
                      placeholder="Alberta"
                      className="rounded-xl"
                      disabled={cardFieldsDisabled}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="country">Country</Label>
                    <Select
                      value={paymentForm.country}
                      disabled={cardFieldsDisabled}
                      onValueChange={(value) => setPaymentForm((prev) => ({ ...prev, country: value }))}
                    >
                      <SelectTrigger className="rounded-xl">
                        <SelectValue placeholder="Country" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="CA">Canada</SelectItem>
                        <SelectItem value="US">United States</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <Separator />

                {paymentMode === "card" && !isSavedSource && (
                  <div className="flex items-center space-x-2">
                    <Checkbox
                      id="savePaymentMethod"
                      checked={savePaymentMethod}
                      onCheckedChange={(checked) => setSavePaymentMethod(checked === true)}
                    />
                    <Label htmlFor="savePaymentMethod" className="cursor-pointer text-sm">
                      Save payment method for future promotions
                    </Label>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="space-y-4">
            <Card className="sticky top-24">
              <CardHeader>
                <CardTitle>Order summary</CardTitle>
                <p className="text-sm text-muted-foreground">
                  {format(new Date(checkoutSummary.startDate), "MMM d, yyyy")} –{" "}
                  {format(new Date(checkoutSummary.endDate), "MMM d, yyyy")}
                </p>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div className="flex items-center justify-between">
                  <span>Promotion ({checkoutSummary.durationDays} days)</span>
                  <span>{formatCents(checkoutSummary.baseCents)}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>GST (5%)</span>
                  <span>{formatCents(checkoutSummary.gstCents)}</span>
                </div>
                <Separator />
                <div className="flex items-center justify-between text-base font-semibold text-foreground">
                  <span>Total</span>
                  <span>{formatCents(chargeAmount)}</span>
                </div>
                {paymentError && <p className="text-sm text-destructive">{paymentError}</p>}
                <Button
                  onClick={handlePayment}
                  className="w-full rounded-full"
                  size="lg"
                  disabled={
                    paymentLoading ||
                    (paymentMode === "earnings" && !canPayWithEarnings) ||
                    (paymentMode === "card" && isSavedSource && (!selectedSavedMethod || savedMethodsLoading))
                  }
                >
                  {paymentLoading ? "Processing..." : "Complete payment"}
                </Button>
                <Button
                  onClick={() => {
                    resetPaymentStepState();
                    setStep("schedule");
                  }}
                  variant="outline"
                  className="w-full rounded-full"
                >
                  Cancel
                </Button>
              </CardContent>
            </Card>
          </div>
        </div>
      </>
    );
  };

  const renderSuccessStep = () => {
    if (!successSlot) return null;
    const start = format(new Date(successSlot.starts_at), "MMM d, yyyy");
    const end = format(new Date(successSlot.ends_at), "MMM d, yyyy");

    return (
      <div className="space-y-6">
        <div className="rounded-3xl border border-border bg-muted/40 p-6 text-center">
          <h2 className="text-2xl font-semibold">Promotion scheduled</h2>
          <p className="mt-2 text-muted-foreground">
            {listing.title} will be highlighted from {start} to {end}.
          </p>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-6 text-sm text-muted-foreground">
            <div>
              <p className="text-xs uppercase">Total days</p>
              <p className="text-lg font-semibold text-foreground">{successSlot.duration_days}</p>
            </div>
            <div>
              <p className="text-xs uppercase">Total charged</p>
              <p className="text-lg font-semibold text-foreground">
                {formatCents(successSlot.total_price_cents)}
              </p>
            </div>
          </div>
          <div className="mt-6 flex justify-center gap-3">
            <Button onClick={onBack} className="rounded-full">
              Back to listing management
            </Button>
          </div>
        </div>
      </div>
    );
  };

  let content: React.ReactNode;
  if (step === "payment") {
    content = renderPaymentStep();
  } else if (step === "success") {
    content = renderSuccessStep();
  } else {
    content = renderScheduleStep();
  }

  const backAction =
    step === "schedule"
      ? onBack
      : step === "payment"
        ? () => {
            resetPaymentStepState();
            setStep("schedule");
          }
        : onBack;

  const backLabel =
    step === "schedule"
      ? "Back to listing edit"
      : step === "payment"
        ? "Back to scheduling"
        : "Back to listing edit";

  return (
    <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="sm"
            onClick={backAction}
            className="rounded-full"
          >
            &larr; {backLabel}
          </Button>
        </div>

      {isLoadingPricing && step === "schedule" ? (
        <div className="flex items-center gap-2 rounded-xl border border-dashed border-border p-4 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading promotion pricing…
        </div>
      ) : (
        content
      )}
    </div>
  );
}
