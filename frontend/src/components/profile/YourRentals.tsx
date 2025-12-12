import { ChangeEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import { CardElement, useElements, useStripe } from "@stripe/react-stripe-js";
import type { StripeCardElementOptions } from "@stripe/stripe-js";
import { ArrowLeft, CreditCard, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { useNavigate } from "react-router-dom";
import { AuthStore } from "@/lib/auth";
import ChatMessages from "@/components/chat/Messages";
import { ReviewModal } from "@/components/reviews/ReviewModal";
import {
  authAPI,
  bookingsAPI,
  deriveDisplayRentalStatus,
  getBookingChargeAmount,
  getBookingDamageDeposit,
  listingsAPI,
  disputesAPI,
  paymentsAPI,
  type Booking,
  type BookingTotals,
  type BookingStatus,
  type DisplayRentalStatus,
  type DisputeCase,
  type DisputeStatus,
  type JsonError,
  type Listing,
  type PaymentMethod,
} from "@/lib/api";
import { fetchConversations, type ConversationSummary } from "@/lib/chat";
import { formatCurrency, parseMoney } from "@/lib/utils";
import { startEventStream, type EventEnvelope } from "@/lib/events";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Checkbox } from "../ui/checkbox";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Separator } from "../ui/separator";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { PolicyConfirmationModal } from "../PolicyConfirmationModal";
import { DisputeWizard } from "../disputes/DisputeWizard";

type StatusFilter = "all" | BookingStatus;
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
  endDateRaw: string;
  returnedByRenterAt: string | null;
  returnConfirmedAt: string | null;
  pickupConfirmedAt: string | null;
  beforePhotosUploadedAt: string | null;
  beforePhotosRequired: boolean;
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

type BookingWithReturnFields = Booking & {
  returned_by_renter_at?: string | null;
  return_confirmed_at?: string | null;
};

type BeforePhotoUpload = {
  file: File;
  previewUrl: string;
};

interface YourRentalsProps {
  onUnpaidRentalsChange?: (count: number) => void;
}

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
const cancelableStatuses: BookingStatus[] = ["requested", "confirmed", "paid"];

const parseLocalDate = (isoDate: string) => {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) {
    throw new Error("invalid date");
  }
  return new Date(year, month - 1, day);
};

const msPerDay = 24 * 60 * 60 * 1000;

const hasChargeIntent = (booking: Booking) =>
  Boolean((booking.charge_payment_intent_id ?? "").trim());

const isPrePaymentBooking = (booking: Booking) => !hasChargeIntent(booking);

const isStartDay = (isoDate: string): boolean => {
  try {
    const today = startOfToday();
    const start = parseLocalDate(isoDate);
    return today.getFullYear() === start.getFullYear() &&
      today.getMonth() === start.getMonth() &&
      today.getDate() === start.getDate();
  } catch {
    return false;
  }
};

const getDaysUntilStart = (booking: Booking): number | null => {
  try {
    const today = startOfToday();
    const start = parseLocalDate(booking.start_date);
    return Math.round((start.getTime() - today.getTime()) / msPerDay);
  } catch {
    return null;
  }
};

const buildRenterCancelWarning = (booking: Booking): string => {
  if (isPrePaymentBooking(booking)) {
    return "No payment has been taken yet. Canceling now will simply withdraw your request and notify the owner.";
  }
  const daysUntilStart = getDaysUntilStart(booking);
  const safeDays = daysUntilStart ?? 0;
  if (safeDays > 1) {
    return "If you cancel now, you'll receive a full refund of your rental payment, service fee, and damage deposit.";
  }
  if (safeDays === 1) {
    return "If you cancel now, we'll charge you for 1 rental day plus the service fee for that day. The remaining rental days and your full damage deposit will be refunded.";
  }
  return "If you cancel now, 50% of the rental subtotal and 50% of the service fee will be kept. Your entire damage deposit will be refunded if the tool was never picked up.";
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
  if (filter === "all") return true;
  return row.statusRaw === filter;
};

const hasReachedReturnWindow = (endDateRaw: string): boolean => {
  try {
    const today = startOfToday();
    const endDate = parseLocalDate(endDateRaw);
    endDate.setDate(endDate.getDate() - 1);
    return today.getTime() >= endDate.getTime();
  } catch {
    return false;
  }
};

const canRequestReturn = (row: RentalRow): boolean => {
  if (row.statusRaw !== "paid" || row.statusLabel !== "In progress") {
    return false;
  }
  if (!hasReachedReturnWindow(row.endDateRaw)) {
    return false;
  }
  if (row.returnedByRenterAt) {
    return false;
  }
  return true;
};

export function YourRentals({ onUnpaidRentalsChange }: YourRentalsProps = {}) {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [payingRental, setPayingRental] = useState<PayableRental | null>(null);
  const [savePaymentMethod, setSavePaymentMethod] = useState(false);
  const [savedMethods, setSavedMethods] = useState<PaymentMethod[]>([]);
  const [savedMethodsLoading, setSavedMethodsLoading] = useState(false);
  const [savedMethodsError, setSavedMethodsError] = useState<string | null>(null);
  const [paymentMode, setPaymentMode] = useState<"new" | "saved">("new");
  const [selectedSavedMethodId, setSelectedSavedMethodId] = useState<number | null>(null);
  const isSavedMode = paymentMode === "saved";
  const [paymentForm, setPaymentForm] = useState<PaymentFormState>(createInitialPaymentForm());
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [paymentLoading, setPaymentLoading] = useState(false);
  const [policyModalOpen, setPolicyModalOpen] = useState(false);
  const [pendingPaymentRow, setPendingPaymentRow] = useState<RentalRow | null>(null);
  const [policyAcknowledged, setPolicyAcknowledged] = useState(false);
  const [cancelDialog, setCancelDialog] = useState<{
    booking: Booking;
    warning: string;
    loading: boolean;
  } | null>(null);
  const [pickupTarget, setPickupTarget] = useState<RentalRow | null>(null);
  const [beforePhotos, setBeforePhotos] = useState<BeforePhotoUpload[]>([]);
  const [beforeUploadLoading, setBeforeUploadLoading] = useState(false);
  const [beforeUploadError, setBeforeUploadError] = useState<string | null>(null);
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null);
  const [chatConversations, setChatConversations] = useState<ConversationSummary[]>([]);
  const [chatConversationId, setChatConversationId] = useState<number | null>(null);
  const [renterReviewTarget, setRenterReviewTarget] = useState<{
    bookingId: number;
    ownerName: string;
  } | null>(null);
  const [disputeWizardOpen, setDisputeWizardOpen] = useState(false);
  const [disputeContext, setDisputeContext] = useState<{
    bookingId: number;
    toolName: string;
    rentalPeriod: string;
  } | null>(null);
  const [disputesByBookingId, setDisputesByBookingId] = useState<Record<number, DisputeCase | null>>({});
  const currentUser = AuthStore.getCurrentUser();
  const currentUserId = currentUser?.id ?? null;
  const stripe = useStripe();
  const elements = useElements();
  const navigate = useNavigate();
  const listingCacheRef = useRef<Map<string, Listing | null>>(new Map());
  const beforeFileInputRef = useRef<HTMLInputElement | null>(null);
  const beforePhotosRef = useRef<BeforePhotoUpload[]>([]);
  const isMountedRef = useRef(true);
  const rentalRowsRef = useRef<RentalRow[]>([]);
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
  const cardElementComputedOptions = useMemo<StripeCardElementOptions>(
    () => ({ ...cardElementOptions, disabled: isSavedMode }),
    [cardElementOptions, isSavedMode],
  );

  const getOwnerDisplayName = useCallback((row: RentalRow | null | undefined) => {
    const first = row?.ownerFirstName?.trim() ?? "";
    const last = row?.ownerLastName?.trim() ?? "";
    const username = row?.ownerUsername ?? "";
    const full = [first, last].filter(Boolean).join(" ").trim();
    return full || username || "Owner";
  }, []);

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

  const reloadBookings = useCallback(async () => {
    if (!currentUserId) {
      setBookings([]);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await bookingsAPI.listMine();
      if (!isMountedRef.current) {
        return;
      }
      const mine = data
        .filter((booking) => booking.renter === currentUserId)
        .sort(
          (a, b) =>
            new Date(b.created_at).getTime() -
            new Date(a.created_at).getTime(),
        );
      setBookings(mine);
    } catch (err) {
      if (!isMountedRef.current) {
        return;
      }
      setError("Unable to load your rentals. Please try again.");
    } finally {
      if (!isMountedRef.current) {
        return;
      }
      setLoading(false);
    }
  }, [currentUserId]);

  useEffect(() => {
    void reloadBookings();
    return () => {
      isMountedRef.current = false;
    };
  }, [reloadBookings]);

  useEffect(() => {
    let cancelled = false;
    const loadDisputes = async () => {
      const disputed = bookings.filter((booking) => booking.is_disputed);
      if (!disputed.length) {
        setDisputesByBookingId({});
        return;
      }
      const entries = await Promise.all(
        disputed.map(async (booking) => {
          try {
            const cases = await disputesAPI.list({ bookingId: booking.id });
            const active =
              cases.find((item) => activeDisputeStatuses.includes(item.status)) ||
              cases[0] ||
              null;
            return [booking.id, active] as const;
          } catch (err) {
            return [booking.id, null] as const;
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
  }, [bookings]);

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
            if (payload.renter_id === currentUserId) {
              const row = rentalRowsRef.current.find(
                (entry) => entry.bookingId === payload.booking_id,
              );
              const ownerName = row ? getOwnerDisplayName(row) : "Owner";
              setRenterReviewTarget({ bookingId: payload.booking_id, ownerName });
            }
          }
        }
        if (shouldReload) {
          void reloadBookings();
        }
      },
    });

    return () => {
      handle.stop();
    };
  }, [currentUserId, getOwnerDisplayName, reloadBookings]);

  useEffect(() => {
    beforePhotosRef.current = beforePhotos;
  }, [beforePhotos]);

  useEffect(() => {
    return () => {
      beforePhotosRef.current.forEach((upload) => {
        URL.revokeObjectURL(upload.previewUrl);
      });
    };
  }, []);

  const handleInputChange = (event: ChangeEvent<HTMLInputElement>) => {
    const { name, value } = event.target;
    const fieldName = name as keyof PaymentFormState;
    setPaymentForm((prev) => ({ ...prev, [fieldName]: value }));
  };

  useEffect(() => {
    let cancelled = false;
    if (!payingRental) {
      setSavedMethods([]);
      setSavedMethodsError(null);
      setSavedMethodsLoading(false);
      setSelectedSavedMethodId(null);
      return;
    }

    const loadSavedMethods = async () => {
      setSavedMethodsLoading(true);
      setSavedMethodsError(null);
      try {
        const methods = await paymentsAPI.listPaymentMethods();
        if (cancelled) return;
        setSavedMethods(methods);
        const preferred = methods.find((method) => method.is_default) ?? methods[0];
        setSelectedSavedMethodId((prev) => prev ?? preferred?.id ?? null);
      } catch (err) {
        if (cancelled) return;
        console.error("payments: failed to load saved methods", err);
        setSavedMethodsError("Could not load saved payment methods.");
        setSavedMethods([]);
        setSelectedSavedMethodId(null);
      } finally {
        if (!cancelled) {
          setSavedMethodsLoading(false);
        }
      }
    };

    void loadSavedMethods();

    return () => {
      cancelled = true;
    };
  }, [payingRental]);

  const selectedSavedMethod = useMemo(
    () => savedMethods.find((method) => method.id === selectedSavedMethodId) ?? null,
    [savedMethods, selectedSavedMethodId],
  );

  const resetPaymentState = () => {
    const cardElement = elements?.getElement(CardElement);
    cardElement?.clear();
    setPayingRental(null);
    setPaymentForm(createInitialPaymentForm());
    setSavePaymentMethod(false);
    setPaymentError(null);
    setPaymentLoading(false);
    setPaymentMode("new");
    setSavedMethods([]);
    setSavedMethodsError(null);
    setSelectedSavedMethodId(null);
  };

  const handlePayment = async () => {
    if (!payingRental) return;

    if (paymentMode === "saved") {
      if (!selectedSavedMethod) {
        setPaymentError("Please select a saved card before paying.");
        return;
      }
      setPaymentError(null);
      setPaymentLoading(true);
      try {
        const stripeCustomerId = currentUser?.stripe_customer_id || undefined;
        const updatedBooking = await bookingsAPI.pay(payingRental.bookingId, {
          stripe_payment_method_id: selectedSavedMethod.stripe_payment_method_id,
          stripe_customer_id: stripeCustomerId,
        });
        setBookings((prev) =>
          prev.map((booking) => (booking.id === updatedBooking.id ? updatedBooking : booking)),
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
      if (savePaymentMethod) {
        try {
          await paymentsAPI.addPaymentMethod({ stripe_payment_method_id: paymentMethod.id });
        } catch (saveErr) {
          console.error("payments: failed to save payment method", saveErr);
          toast.error("Payment succeeded, but we couldn't save this card.");
        }
      }
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
        const bookingWithReturn = booking as BookingWithReturnFields;
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
          endDateRaw: booking.end_date,
          returnedByRenterAt: bookingWithReturn.returned_by_renter_at ?? null,
          returnConfirmedAt: bookingWithReturn.return_confirmed_at ?? null,
          pickupConfirmedAt: booking.pickup_confirmed_at ?? null,
          beforePhotosUploadedAt: booking.before_photos_uploaded_at ?? null,
          beforePhotosRequired: booking.before_photos_required !== false,
        };
      });
  }, [bookings]);

  useEffect(() => {
    rentalRowsRef.current = rentalRows;
  }, [rentalRows]);

  const filteredRows = useMemo(() => {
    return rentalRows.filter((row) => matchesStatusFilter(row, statusFilter));
  }, [rentalRows, statusFilter]);

  const unpaidRentalsCount = useMemo(
    () => rentalRows.filter((row) => row.isPayable).length,
    [rentalRows],
  );

  useEffect(() => {
    if (onUnpaidRentalsChange) {
      onUnpaidRentalsChange(unpaidRentalsCount);
    }
  }, [onUnpaidRentalsChange, unpaidRentalsCount]);

  const openRenterCancelDialog = (booking: Booking) => {
    setCancelDialog({
      booking,
      warning: buildRenterCancelWarning(booking),
      loading: false,
    });
  };

  const handleConfirmRenterCancel = async () => {
    if (!cancelDialog) {
      return;
    }
    const bookingId = cancelDialog.booking.id;
    setCancelDialog({ ...cancelDialog, loading: true });
    try {
      const updated = await bookingsAPI.cancel(bookingId);
      setBookings((prev) =>
        prev.map((booking) => (booking.id === updated.id ? updated : booking)),
      );
      if (payingRental?.bookingId === updated.id) {
        resetPaymentState();
      }
      toast.success("Booking canceled.");
      setCancelDialog(null);
    } catch {
      toast.error("Unable to cancel this booking right now.");
      setCancelDialog((prev) => (prev ? { ...prev, loading: false } : prev));
    }
  };

  const resetBeforePhotoUploads = () => {
    setBeforePhotos((prev) => {
      prev.forEach((upload) => URL.revokeObjectURL(upload.previewUrl));
      return [];
    });
  };

  const closePickupFlow = () => {
    resetBeforePhotoUploads();
    setPickupTarget(null);
    setBeforeUploadError(null);
    setBeforeUploadLoading(false);
  };

  const handleBeforePhotoInput = (event: ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) {
      return;
    }
    const uploads = Array.from(files).map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    setBeforePhotos((prev) => [...prev, ...uploads]);
    setBeforeUploadError(null);
    event.target.value = "";
  };

  const removeBeforePhoto = (index: number) => {
    setBeforePhotos((prev) => {
      const next = [...prev];
      const [removed] = next.splice(index, 1);
      if (removed) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return next;
    });
  };

  const handleBeforePhotosSubmit = async () => {
    if (!pickupTarget) {
      return;
    }
    if (beforePhotos.length === 0) {
      setBeforeUploadError("Please select at least one photo before continuing.");
      return;
    }
    setBeforeUploadLoading(true);
    setBeforeUploadError(null);
    try {
      for (const upload of beforePhotos) {
        const presign = await bookingsAPI.beforePhotosPresign(pickupTarget.bookingId, {
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
          throw new Error("Unable to upload one of the files. Please try again.");
        }
        const etagHeader =
          uploadResponse.headers.get("ETag") ?? uploadResponse.headers.get("etag");
        if (!etagHeader) {
          throw new Error("Upload completed but verification failed. Please retry.");
        }
        const cleanEtag = etagHeader.replace(/"/g, "");
        await bookingsAPI.beforePhotosComplete(pickupTarget.bookingId, {
          key: presign.key,
          etag: cleanEtag,
          filename: upload.file.name,
          content_type: upload.file.type || "application/octet-stream",
          size: upload.file.size,
        });
      }
      const timestamp = new Date().toISOString();
      setBookings((prev) =>
        prev.map((booking) =>
          booking.id === pickupTarget.bookingId
            ? {
                ...booking,
                before_photos_uploaded_at: booking.before_photos_uploaded_at ?? timestamp,
              }
            : booking,
        ),
      );
      toast.success("Before photos uploaded. Owner can now confirm pickup.");
      closePickupFlow();
    } catch (err) {
      console.error("before photo upload failed", err);
      let message = "Could not upload before photos. Please try again.";
      if (isJsonError(err)) {
        message = extractJsonErrorMessage(err) ?? message;
      } else if (err instanceof Error && err.message) {
        message = err.message;
      }
      setBeforeUploadError(message);
      toast.error(message);
    } finally {
      setBeforeUploadLoading(false);
    }
  };

  const handlePickup = (bookingId: number) => {
    const row = rentalRows.find((entry) => entry.bookingId === bookingId);
    if (!row) {
      return;
    }
    setPickupTarget(row);
    resetBeforePhotoUploads();
    setBeforeUploadError(null);
    setBeforeUploadLoading(false);
  };

  const handleRequestReturn = async (row: RentalRow) => {
    const confirmed = window.confirm("Are you sure you want to mark this rental as returned?");
    if (!confirmed) {
      return;
    }
    setActionLoadingId(row.bookingId);
    try {
      const updated = await bookingsAPI.renterReturn(row.bookingId);
      setBookings((prev) =>
        prev.map((booking) => (booking.id === updated.id ? updated : booking)),
      );
      const ownerName = getOwnerDisplayName(row);
      setRenterReviewTarget({ bookingId: row.bookingId, ownerName });
      toast.success("Return requested – waiting for owner.");
    } catch (err) {
      const message = isJsonError(err)
        ? extractJsonErrorMessage(err) ?? "Could not request a return right now."
        : "Could not request a return right now.";
      toast.error(message);
    } finally {
      setActionLoadingId(null);
    }
  };

  const startPaymentFlow = (row: RentalRow) => {
    setPaymentForm(createInitialPaymentForm());
    setSavePaymentMethod(false);
    setPaymentError(null);
    setPaymentLoading(false);
    setPaymentMode("new");
    setSelectedSavedMethodId(null);
    setSavedMethodsError(null);
    setSavedMethods([]);
    setPayingRental({
      ...row,
      bookingId: row.bookingId,
      rentalSubtotal: row.rentalSubtotal,
      serviceFee: row.serviceFee,
      damageDeposit: row.damageDeposit,
    });
  };

  const closePolicyModal = () => {
    setPolicyModalOpen(false);
    setPendingPaymentRow(null);
  };

  const confirmPolicyAndStartPayment = () => {
    if (!pendingPaymentRow) {
      return;
    }
    startPaymentFlow(pendingPaymentRow);
    closePolicyModal();
  };

  const handlePay = (bookingId: number) => {
    const row = rentalRows.find((entry) => entry.bookingId === bookingId);
    if (!row) {
      return;
    }
    setPendingPaymentRow(row);
    setPolicyAcknowledged(false);
    setPolicyModalOpen(true);
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
    const estimatedTotal = depositHold;
    const isPaymentDisabled =
      paymentLoading ||
      (!isSavedMode && (!stripe || !elements)) ||
      (isSavedMode && (savedMethodsLoading || !selectedSavedMethod));

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
                <CardDescription>Use a saved card or enter new details</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant={isSavedMode ? "outline" : "default"}
                    size="sm"
                    className="rounded-full"
                    onClick={() => {
                      setPaymentMode("new");
                      setPaymentError(null);
                    }}
                  >
                    New card
                  </Button>
                  {savedMethods.length > 0 && (
                    <Button
                      variant={isSavedMode ? "default" : "outline"}
                      size="sm"
                      className="rounded-full"
                      onClick={() => {
                        setPaymentMode("saved");
                        setPaymentError(null);
                      }}
                    >
                      Saved card
                    </Button>
                  )}
                </div>

                {savedMethodsError && (
                  <p className="text-xs text-destructive">{savedMethodsError}</p>
                )}

                {isSavedMode && (
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
                              name="saved-payment-method"
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
                  <Label htmlFor="cardholderName">Cardholder Name</Label>
                  <Input
                    id="cardholderName"
                    name="cardholderName"
                    value={paymentForm.cardholderName}
                    onChange={handleInputChange}
                    placeholder="John Doe"
                    className="rounded-xl"
                    disabled={isSavedMode}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Card Details</Label>
                  <div className="rounded-xl border border-input bg-background px-3 py-3 focus-within:ring-2 focus-within:ring-ring transition-shadow">
                    <CardElement options={cardElementComputedOptions} />
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
                      disabled={isSavedMode}
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
                      disabled={isSavedMode}
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
                      disabled={isSavedMode}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="country">Country</Label>
                    <Select
                      value={paymentForm.country}
                      disabled={isSavedMode}
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

                {!isSavedMode && (
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
                )}
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
                    <span>Estimated authorization (deposit hold)</span>
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
    <>
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
              <SelectItem value="confirmed">Confirmed</SelectItem>
              <SelectItem value="paid">Paid</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="canceled">Canceled</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {pickupTarget && (
        <Card>
          <CardHeader>
            <CardTitle>Upload before photos</CardTitle>
            <CardDescription>
              {pickupTarget.toolName} · {pickupTarget.rentalPeriod}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Add photos of the tool before pickup for your protection. Once uploaded, the owner
              can confirm pickup.
            </p>
            <div
              className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-primary transition-colors"
              onClick={() => beforeFileInputRef.current?.click()}
            >
              <Upload className="w-10 h-10 mx-auto mb-3 text-muted-foreground" />
              <p className="font-medium">Click to upload or drag and drop</p>
              <p className="text-sm text-muted-foreground">
                PNG, JPG or WEBP (max. 15MB each)
              </p>
              <input
                ref={beforeFileInputRef}
                type="file"
                multiple
                accept="image/*"
                className="hidden"
                onChange={handleBeforePhotoInput}
                disabled={beforeUploadLoading}
              />
            </div>

            {beforePhotos.length > 0 && (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {beforePhotos.map((upload, index) => (
                  <div
                    key={`${upload.file.name}-${index}`}
                    className="relative aspect-square rounded-lg overflow-hidden bg-muted"
                  >
                    <img
                      src={upload.previewUrl}
                      alt={`Before photo ${index + 1}`}
                      className="w-full h-full object-cover"
                    />
                    <button
                      type="button"
                      className="absolute top-2 right-2 w-6 h-6 rounded-full bg-destructive text-white flex items-center justify-center"
                      onClick={() => removeBeforePhoto(index)}
                      disabled={beforeUploadLoading}
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            {beforeUploadError && (
              <p className="text-sm text-destructive">{beforeUploadError}</p>
            )}

            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end sm:gap-3 pt-2">
              <Button
                variant="outline"
                onClick={closePickupFlow}
                disabled={beforeUploadLoading}
              >
                Cancel
              </Button>
              <Button
                onClick={handleBeforePhotosSubmit}
                disabled={beforeUploadLoading || beforePhotos.length === 0}
              >
                {beforeUploadLoading ? "Uploading..." : "Upload & continue"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

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
                filteredRows.map((row) => {
                  const showPickupButton =
                    row.statusRaw === "paid" &&
                    isStartDay(row.startDate) &&
                    row.beforePhotosRequired &&
                    !row.beforePhotosUploadedAt &&
                    !row.pickupConfirmedAt;
                  const awaitingOwner =
                    row.statusRaw === "paid" &&
                    row.beforePhotosRequired &&
                    Boolean(row.beforePhotosUploadedAt) &&
                    !row.pickupConfirmedAt;
                  const isInProgress = row.statusLabel === "In progress";
                  const canReturnRental = canRequestReturn(row);
                  const isRowActionLoading = actionLoadingId === row.bookingId;
                  const hasReturnRequest = Boolean(row.returnedByRenterAt);

                  return (
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
                        <div className="flex flex-col gap-1">
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
                          {disputesByBookingId[row.bookingId] && (
                            <Badge variant="outline" className="text-xs font-normal">
                              {formatDisputeStatusLabel(
                                (disputesByBookingId[row.bookingId]?.status ||
                                  "open") as DisputeStatus,
                              )}
                            </Badge>
                          )}
                        </div>
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
                        <div className="flex flex-col items-end gap-1">
                          <div className="flex justify-end gap-2">
                            {!isInProgress && (
                              <Button
                                size="sm"
                                variant="secondary"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void openChatForBooking(row.bookingId);
                                }}
                              >
                                Chat
                              </Button>
                            )}
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
                            {showPickupButton && (
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
                            {canReturnRental && (
                              <Button
                                size="sm"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  void handleRequestReturn(row);
                                }}
                                disabled={isRowActionLoading}
                              >
                                {isRowActionLoading ? "Requesting..." : "Return rental"}
                              </Button>
                            )}
                            {isInProgress && !disputesByBookingId[row.bookingId] && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  setDisputeContext({
                                    bookingId: row.bookingId,
                                    toolName: row.toolName,
                                    rentalPeriod: row.rentalPeriod,
                                  });
                                  setDisputeWizardOpen(true);
                                }}
                              >
                                Report an Issue
                              </Button>
                            )}
                            {!isInProgress && row.isCancelable && (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  const booking = bookings.find(
                                    (entry) => entry.id === row.bookingId,
                                  );
                                  if (!booking) {
                                    return;
                                  }
                                  openRenterCancelDialog(booking);
                                }}
                              >
                                Cancel
                              </Button>
                            )}
                          </div>
                          {awaitingOwner && (
                            <span className="text-xs text-muted-foreground">
                              Before photos uploaded · Awaiting owner
                            </span>
                          )}
                          {hasReturnRequest && (
                            <span className="text-xs text-muted-foreground">
                              Return requested – waiting for owner
                            </span>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      </div>
      <DisputeWizard
        open={disputeWizardOpen}
        onOpenChange={(open) => {
          setDisputeWizardOpen(open);
          if (!open) {
            setDisputeContext(null);
          }
        }}
        bookingId={disputeContext?.bookingId ?? null}
        role="renter"
        toolName={disputeContext?.toolName}
        rentalPeriodLabel={disputeContext?.rentalPeriod}
      />
      <Dialog
        open={Boolean(cancelDialog)}
        onOpenChange={(open) => {
          if (!open && !cancelDialog?.loading) {
            setCancelDialog(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancel this booking?</DialogTitle>
            <DialogDescription>{cancelDialog?.warning}</DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button
              variant="outline"
              onClick={() => {
                if (!cancelDialog?.loading) {
                  setCancelDialog(null);
                }
              }}
              disabled={cancelDialog?.loading}
            >
              Keep booking
            </Button>
            <Button
              variant="destructive"
              onClick={handleConfirmRenterCancel}
              disabled={cancelDialog?.loading}
            >
              {cancelDialog?.loading ? "Canceling..." : "Yes, cancel"}
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
        open={renterReviewTarget !== null}
        role="renter_to_owner"
        bookingId={renterReviewTarget?.bookingId ?? 0}
        otherPartyName={renterReviewTarget?.ownerName ?? "Owner"}
        onClose={() => setRenterReviewTarget(null)}
        onSubmitted={() => {
          toast.success("Thanks for reviewing the owner.");
        }}
      />
      <PolicyConfirmationModal
        open={policyModalOpen}
        roleLabel="renter"
        checkboxChecked={policyAcknowledged}
        onCheckboxChange={(checked) => setPolicyAcknowledged(checked)}
        onConfirm={confirmPolicyAndStartPayment}
        onCancel={closePolicyModal}
        confirmDisabled={paymentLoading}
      />
    </>
  );
}

export const __testables = { parseLocalDate, startOfToday, isStartDay };
