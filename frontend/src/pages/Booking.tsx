import { useEffect, useState, type MouseEvent } from "react";
import {
  ArrowLeft,
  Star,
  MapPin,
  Shield,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  X,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import { Badge } from "../components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Separator } from "../components/ui/separator";
import { BookingMap } from "../components/BookingMap";
import { LoginModal } from "../components/LoginModal";
import { Header } from "../components/Header";
import { addDays, differenceInDays, format } from "date-fns";
import { useNavigate } from "react-router-dom";
import { bookingsAPI, usersAPI, type Listing as ApiListing, type PublicProfile } from "@/lib/api";
import { AuthStore } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface BookingPageProps {
  listing: ApiListing | null;
  onBack: () => void;
  isLoading?: boolean;
  errorMessage?: string;
}

interface Review {
  id: number;
  userName: string;
  userAvatar: string;
  rating: number;
  date: string;
  comment: string;
}


export default function Booking({
  listing,
  onBack,
  isLoading = false,
  errorMessage,
}: BookingPageProps) {
  const navigate = useNavigate();
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [dateRange, setDateRange] = useState<{
    from: Date | undefined;
    to: Date | undefined;
  }>({
    from: undefined,
    to: undefined,
  });
  const [unavailableDates, setUnavailableDates] = useState<Date[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);
  const [isLightboxOpen, setIsLightboxOpen] = useState(false);
  const [isMapVisible, setIsMapVisible] = useState(false);
  const [loginModalOpen, setLoginModalOpen] = useState(false);
  const [loginModalMode, setLoginModalMode] = useState<"login" | "signup">(
    "login",
  );
  const [ownerProfile, setOwnerProfile] = useState<PublicProfile | null>(null);
  const [isDescriptionExpanded, setIsDescriptionExpanded] = useState(false);

  useEffect(() => {
    if (!listing?.owner) {
      setOwnerProfile(null);
      return;
    }
    let isMounted = true;
    usersAPI
      .publicProfile(listing.owner)
      .then((data) => {
        if (!isMounted) return;
        setOwnerProfile(data);
      })
      .catch((error) => {
        console.error("Failed to load owner profile", error);
        if (!isMounted) return;
        setOwnerProfile(null);
      });
    return () => {
      isMounted = false;
    };
  }, [listing?.owner]);

  useEffect(() => {
    setIsDescriptionExpanded(false);
  }, [listing?.slug]);

  useEffect(() => {
    if (!listing?.id) {
      setUnavailableDates([]);
      return;
    }

    let active = true;

    bookingsAPI
      .availability(listing.id)
      .then((ranges) => {
        if (!active) return;

        const parseLocalDate = (iso: string) => {
          const [year, month, day] = iso.split("-").map(Number);
          return new Date(year, month - 1, day);
        };

        const allDates: Date[] = [];

        for (const range of ranges) {
          const start = parseLocalDate(range.start_date);
          const endExclusive = parseLocalDate(range.end_date);

          for (
            let cursor = new Date(start.getTime());
            cursor < endExclusive;
            cursor.setDate(cursor.getDate() + 1)
          ) {
            allDates.push(
              new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate()),
            );
          }
        }

        setUnavailableDates(allDates);
      })
      .catch((error) => {
        console.error("Failed to load booking availability", error);
        if (!active) return;
        setUnavailableDates([]);
      });

    return () => {
      active = false;
    };
  }, [listing?.id]);

  if (!listing) {
    return (
      <div className="min-h-screen w-full" style={{ backgroundColor: "#f9f9f9" }}>
        <Header />
        <div className="max-w-7xl mx-auto px-6 py-8">
          <div className="mb-4">
            <Button variant="ghost" onClick={onBack} className="gap-2">
              <ArrowLeft className="w-4 h-4" />
              Back to Feed
            </Button>
          </div>
          <p className="text-muted-foreground">
            {isLoading
              ? "Loading listing details..."
              : errorMessage ?? "Listing is not available."}
          </p>
        </div>
      </div>
    );
  }

  const images =
    listing.photos && listing.photos.length > 0
      ? listing.photos.map((photo) => photo.url)
      : ["https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=1200&q=80"];

  const pricePerDay = Number(listing.daily_price_cad || "0");
  const damageDeposit = Number(listing.damage_deposit_cad || "0");
  const postalCode = listing.postalCode ?? listing.postal_code ?? "";
  const cityName = listing.city ?? "";
  const cityText = cityName || "City not provided";
  const postalCodeText = postalCode || "Postal code not provided";
  const locationDisplay =
    [cityName].filter(Boolean).join(", ") || "Unknown location";
  const categoryName = listing.category_name || "Other";
  const tags = categoryName ? [categoryName] : [];

  const reviews: Review[] = [];
  const averageRating = reviews.length
    ? reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length
    : 5;

  const rawDescription = listing.description ?? "";
  const hasCustomDescription = Boolean(rawDescription.trim().length);
  const descriptionText = hasCustomDescription
    ? rawDescription
    : "No description provided.";
  const descriptionHasManyLines =
    rawDescription.split(/\r?\n/).length > 3;
  const descriptionIsLong = rawDescription.length > 280;
  const allowDescriptionToggle =
    hasCustomDescription && (descriptionHasManyLines || descriptionIsLong);
  const shouldClampDescription = allowDescriptionToggle && !isDescriptionExpanded;

  const ownerFullName = [listing.owner_first_name, listing.owner_last_name]
    .map((part) => part?.trim())
    .filter(Boolean)
    .join(" ");
  const baseOwnerName = ownerFullName || listing.owner_username || "Owner";
  const profileName = [ownerProfile?.first_name, ownerProfile?.last_name]
    .map((part) => part?.trim())
    .filter(Boolean)
    .join(" ");
  const ownerDisplayName = profileName || ownerProfile?.username || baseOwnerName;
  const ownerAvatarUrl = ownerProfile?.avatar_url ?? undefined;
  const ownerInitials =
    ownerDisplayName
      .split(" ")
      .filter(Boolean)
      .map((segment) => segment[0]?.toUpperCase() ?? "")
      .join("")
      .slice(0, 2) || "O";
  const ownerRating =
    typeof ownerProfile?.rating === "number" ? ownerProfile.rating : averageRating;
  const ownerReviewCount =
    typeof ownerProfile?.review_count === "number" ? ownerProfile.review_count : reviews.length;
  const fallbackJoinedDate = (() => {
    const createdAt = listing.created_at ? new Date(listing.created_at) : null;
    if (createdAt && !Number.isNaN(createdAt.getTime())) {
      try {
        return format(createdAt, "MMM yyyy");
      } catch {
        return "2025";
      }
    }
    return "2025";
  })();
  const ownerJoinedDate = (() => {
    if (!ownerProfile?.date_joined) {
      return fallbackJoinedDate;
    }
    const joined = new Date(ownerProfile.date_joined);
    if (Number.isNaN(joined.getTime())) {
      return fallbackJoinedDate;
    }
    try {
      return format(joined, "MMM yyyy");
    } catch {
      return fallbackJoinedDate;
    }
  })();
  const handleViewOwnerProfile = () => {
    navigate(`/users/${listing.owner}`);
  };

  const openLightbox = (index?: number) => {
    if (typeof index === "number") {
      setCurrentImageIndex(index);
    }
    setIsLightboxOpen(true);
  };

  const closeLightbox = () => setIsLightboxOpen(false);
  const handleCloseButtonClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    closeLightbox();
  };

  const nextImage = () => {
    setCurrentImageIndex((prev) => (prev === images.length - 1 ? 0 : prev + 1));
  };

  const previousImage = () => {
    setCurrentImageIndex((prev) => (prev === 0 ? images.length - 1 : prev - 1));
  };

  const numberOfDays =
    dateRange.from && dateRange.to
      ? differenceInDays(dateRange.to, dateRange.from) + 1
      : 0;
  const totalPrice = numberOfDays * pricePerDay;
  const serviceFee = totalPrice * 0.1;
  const totalWithFees = totalPrice + serviceFee;
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const isDateUnavailable = (date: Date) =>
    unavailableDates.some(
      (unavailableDate) =>
        format(unavailableDate, "yyyy-MM-dd") === format(date, "yyyy-MM-dd"),
    );

  const isBeforeToday = (date: Date) => {
    const candidate = new Date(
      date.getFullYear(),
      date.getMonth(),
      date.getDate(),
    );
    return candidate <= today;
  };

  const requireLogin = () => {
    setLoginModalMode("login");
    setLoginModalOpen(true);
  };

  async function handleRequestBooking() {
    if (!listing || !dateRange.from || !dateRange.to) return;

    if (!AuthStore.getTokens()) {
      requireLogin();
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(false);

    try {
      const startDate = format(dateRange.from, "yyyy-MM-dd");
      const endExclusive = addDays(dateRange.to, 1);
      const endDate = format(endExclusive, "yyyy-MM-dd");

      await bookingsAPI.create({
        listing: listing.id,
        start_date: startDate,
        end_date: endDate,
      });

      setSubmitSuccess(true);
    } catch (err: any) {
      let message = "Something went wrong. Please try again.";
      if (err && typeof err === "object" && "data" in err) {
        const data = (err as { data?: any }).data;
        if (data && data.detail) {
          message = String(data.detail);
        }
      }
      setSubmitError(message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <>
      <div
        className="min-h-screen w-full"
        style={{ backgroundColor: "#f9f9f9" }}
      >
        <Header />

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="mb-6">
          <Button variant="ghost" onClick={onBack} className="gap-2">
            <ArrowLeft className="w-4 h-4" />
            Back to Feed
          </Button>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          {/* Left Column - Listing Details */}
          <div className="lg:col-span-2 space-y-6">
            {/* Image Gallery */}
            <div
              className="bg-card rounded-3xl overflow-hidden border border-border"
              style={{
                boxShadow:
                  "0px 51px 21px rgba(0, 0, 0, 0.01), 0px 29px 17px rgba(0, 0, 0, 0.03), 0px 13px 13px rgba(0, 0, 0, 0.05), 0px 3px 7px rgba(0, 0, 0, 0.06)",
              }}
            >
              <div className="relative h-96">
                <button
                  type="button"
                  onClick={() => openLightbox(currentImageIndex)}
                  aria-label="View full-size image"
                  className="block w-full h-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/70"
                >
                  <img
                    src={images[currentImageIndex]}
                    alt={listing.title}
                    className="w-full h-full object-cover cursor-zoom-in"
                  />
                </button>
                {images.length > 1 && (
                  <>
                    <Button
                      variant="secondary"
                      size="icon"
                      className="absolute left-4 top-1/2 -translate-y-1/2 rounded-full"
                      onClick={previousImage}
                    >
                      <ChevronLeft className="w-5 h-5" />
                    </Button>
                    <Button
                      variant="secondary"
                      size="icon"
                      className="absolute right-4 top-1/2 -translate-y-1/2 rounded-full"
                      onClick={nextImage}
                    >
                      <ChevronRight className="w-5 h-5" />
                    </Button>
                  </>
                )}
                {/* Image Counter */}
                <div className="absolute bottom-4 right-4 bg-black/60 text-white px-3 py-1 rounded-full">
                  {currentImageIndex + 1} / {images.length}
                </div>
                {/* Tags */}
                {tags.length > 0 && (
                  <div className="absolute top-4 right-4 flex gap-2">
                    {tags.map((tag) => (
                      <Badge
                        key={tag}
                        variant={tag === "Featured" ? "default" : "secondary"}
                        className="rounded-full"
                      >
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
              </div>

              {/* Thumbnail Strip */}
              {images.length > 1 && (
                <div className="flex gap-2 p-4 overflow-x-auto">
                  {images.map((image, index) => (
                    <button
                      key={index}
                      onClick={() => setCurrentImageIndex(index)}
                      className={`flex-shrink-0 w-20 h-20 rounded-xl overflow-hidden border-2 transition-all ${
                        index === currentImageIndex
                          ? "border-primary"
                          : "border-transparent opacity-60 hover:opacity-100"
                      }`}
                    >
                      <img
                        src={image}
                        alt={`${listing.title} ${index + 1}`}
                        className="w-full h-full object-cover"
                      />
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Listing Info */}
            <div
              className="bg-card rounded-3xl p-6 border border-border"
              style={{
                boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
              }}
            >
              <div className="flex items-start justify-between mb-4">
                <div>
                  <h1
                    className="text-[32px] mb-2"
                    style={{ fontFamily: "Manrope" }}
                  >
                    {listing.title}
                  </h1>
                  <div className="flex items-center gap-4 text-muted-foreground">
                    <div className="flex items-center gap-1">
                      <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                      <span>{averageRating.toFixed(1)}</span>
                      <span>({reviews.length} reviews)</span>
                    </div>
                    <Badge variant="outline" className="rounded-full">
                      {categoryName}
                    </Badge>
                  </div>
                </div>
              </div>

              <Separator className="my-6" />

              <div>
                <h3
                  className="text-[20px] mb-3"
                  style={{ fontFamily: "Manrope" }}
                >
                  Description
                </h3>
                <p
                  className={cn(
                    "text-muted-foreground whitespace-pre-wrap break-words leading-relaxed transition-all",
                    shouldClampDescription && "line-clamp-3",
                  )}
                >
                  {descriptionText}
                </p>
                {allowDescriptionToggle && (
                  <button
                    type="button"
                    className="mt-2 inline-flex items-center gap-1 text-sm font-medium text-primary"
                    onClick={() => setIsDescriptionExpanded((prev) => !prev)}
                    aria-expanded={isDescriptionExpanded}
                  >
                    {isDescriptionExpanded ? "Show less" : "Show more"}
                    {isDescriptionExpanded ? (
                      <ChevronUp className="h-4 w-4" />
                    ) : (
                      <ChevronDown className="h-4 w-4" />
                    )}
                  </button>
                )}
              </div>

              <Separator className="my-6" />

              {/* Location */}
              <div>
                <h3
                  className="text-[20px] mb-3"
                  style={{ fontFamily: "Manrope" }}
                >
                  Location
                </h3>
                <div className="flex items-center gap-2 text-muted-foreground">
                  <MapPin className="w-5 h-5" />
                  <span>
                    City: {cityText} 
                  </span>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="mt-3"
                  type="button"
                  aria-expanded={isMapVisible}
                  aria-controls="booking-location-map"
                  onClick={() => setIsMapVisible((prev) => !prev)}
                >
                  {isMapVisible ? "Hide map" : "Show map"}
                </Button>
                {isMapVisible && (
                  <div
                    id="booking-location-map"
                    className="mt-4 h-48 bg-muted rounded-xl overflow-hidden border border-border"
                  >
                    <BookingMap
                      postalCode={listing.postalCode ?? listing.postal_code ?? ""}
                      city={listing.city ?? "Edmonton"}
                      region="AB, Canada"
                    />
                  </div>
                )}
              </div>

              <Separator className="my-6" />

            </div>

            {/* Calendar Section */}
            <div
              className="bg-card rounded-3xl p-6 border border-border"
              style={{
                boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
              }}
            >
              <h3
                className="text-[20px] mb-4"
                style={{ fontFamily: "Manrope" }}
              >
                Select Your Dates
              </h3>
              <div className="grid gap-8 lg:grid-cols-2">
                <div className="space-y-4">
                  <div className="border border-border rounded-xl p-4 inline-block">
                    <Calendar
                      mode="range"
                      selected={dateRange}
                      onSelect={(range) =>
                        setDateRange({
                          from: range?.from,
                          to: range?.to,
                        })
                      }
                      disabled={(date) =>
                        isDateUnavailable(date) || isBeforeToday(date)
                      }
                      className="rounded-md"
                    />
                  </div>
                </div>

                <div className="space-y-4">
                  <div>
                    <div className="flex items-baseline gap-2 mb-1">
                      <span className="text-[32px] text-primary">
                        ${pricePerDay}
                      </span>
                      <span className="text-muted-foreground">/ day</span>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Choose your rental window to see a full breakdown.
                    </p>
                  </div>

                  <div className="p-4 bg-accent rounded-xl h-fit">
                    {dateRange.from && dateRange.to ? (
                      <>
                        <p className="text-accent-foreground">
                          {format(dateRange.from, "MMM d, yyyy")} -{" "}
                          {format(dateRange.to, "MMM d, yyyy")}
                        </p>
                        <p className="text-accent-foreground/80 mt-1">
                          {numberOfDays}{" "}
                          {numberOfDays === 1 ? "day" : "days"} selected
                        </p>
                      </>
                    ) : (
                      <p className="text-accent-foreground/80">
                        Select a start and end date to preview your rental
                        window.
                      </p>
                    )}
                  </div>

                  <div className="border border-border rounded-xl p-4 space-y-3">
                    {numberOfDays > 0 ? (
                      <>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">
                            ${pricePerDay} x {numberOfDays}{" "}
                            {numberOfDays === 1 ? "day" : "days"}
                          </span>
                          <span>${totalPrice}</span>
                        </div>
                        <div className="flex items-center justify-between">
                          <span className="text-muted-foreground">
                            Service fee
                          </span>
                          <span>${serviceFee.toFixed(2)}</span>
                        </div>
                        <Separator />
                        <div className="flex items-center justify-between text-[18px]">
                          <span style={{ fontFamily: "Manrope" }}>Total</span>
                          <span style={{ fontFamily: "Manrope" }}>
                            ${totalWithFees.toFixed(2)}
                          </span>
                        </div>
                        <div className="flex items-center justify-between text-muted-foreground">
                          <span>Damage Deposit</span>
                          <span>${damageDeposit}</span>
                        </div>
                      </>
                    ) : (
                      <p className="text-muted-foreground text-sm">
                        Choose dates to see a complete cost breakdown.
                      </p>
                    )}
                  </div>

                </div>

                <div className="lg:col-span-2 space-y-4">
                  <Button
                    className="w-full rounded-full"
                    size="lg"
                    disabled={!dateRange.from || !dateRange.to || submitting}
                    onClick={handleRequestBooking}
                  >
                    {submitting
                      ? "Sending request..."
                      : dateRange.from && dateRange.to
                        ? "Request to Book"
                        : "Select dates to book"}
                  </Button>
                  {submitError && (
                    <p className="text-destructive text-sm">{submitError}</p>
                  )}
                  {submitSuccess && (
                    <p className="text-sm text-green-600">
                      Booking request sent. You will see it in your bookings
                      soon.
                    </p>
                  )}
                  {numberOfDays > 0 && (
                    <p className="text-center text-muted-foreground">
                      You won't be charged yet
                    </p>
                  )}
                  <div className="flex items-start gap-3 p-4 bg-accent rounded-xl">
                    <Shield className="w-5 h-5 text-accent-foreground mt-0.5" />
                    <div>
                      <p className="text-accent-foreground mb-1">
                        Refundable Damage Deposit
                      </p>
                      <p className="text-[20px] text-accent-foreground">
                        ${damageDeposit}
                      </p>
                      <p className="text-accent-foreground/80 mt-2">
                        This amount will be held and returned after the rental
                        period, provided there is no damage to the item.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Owner Info */}
            <div
              className="bg-card rounded-3xl p-6 border border-border"
              style={{
                boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
              }}
            >
              <h3
                className="text-[20px] mb-4"
                style={{ fontFamily: "Manrope" }}
              >
                About the Owner
              </h3>
              <div className="flex items-start gap-4">
                <Avatar className="w-16 h-16">
                  <AvatarImage src={ownerAvatarUrl} alt={ownerDisplayName} />
                  <AvatarFallback>{ownerInitials}</AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <p className="text-[18px] mb-1" style={{ fontFamily: "Manrope" }}>
                    {ownerDisplayName}
                  </p>
                  <div className="flex items-center gap-3 text-muted-foreground mb-2">
                    <div className="flex items-center gap-1">
                      <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                      <span>{ownerRating.toFixed(1)}</span>
                    </div>
                    <span>•</span>
                    <span>{ownerReviewCount} reviews</span>
                    <span>•</span>
                    <span>Joined {ownerJoinedDate}</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-3">
                    <Button variant="outline" className="rounded-full">
                      Contact Owner
                    </Button>
                    <Button
                      variant="ghost"
                      className="rounded-full"
                      onClick={handleViewOwnerProfile}
                    >
                      View Profile
                    </Button>
                  </div>
                </div>
              </div>
            </div>

            {/* Reviews */}
            <div
              className="bg-card rounded-3xl p-6 border border-border"
              style={{
                boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
              }}
            >
              <div className="flex items-center justify-between mb-6">
                <h3 className="text-[20px]" style={{ fontFamily: "Manrope" }}>
                  Reviews
                </h3>
                <div className="flex items-center gap-2">
                  <Star className="w-5 h-5 fill-yellow-400 text-yellow-400" />
                  <span className="text-[20px]">{averageRating.toFixed(1)}</span>
                  <span className="text-muted-foreground">
                    ({reviews.length} reviews)
                  </span>
                </div>
              </div>

              <div className="space-y-6">
                {reviews.map((review) => (
                  <div key={review.id}>
                    <div className="flex items-start gap-4">
                      <Avatar className="w-12 h-12">
                        <AvatarImage src={review.userAvatar} />
                        <AvatarFallback>
                          {review.userName
                            .split(" ")
                            .map((n) => n[0])
                            .join("")}
                        </AvatarFallback>
                      </Avatar>
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-1">
                          <p style={{ fontFamily: "Manrope" }}>
                            {review.userName}
                          </p>
                          <span className="text-muted-foreground">
                            {review.date}
                          </span>
                        </div>
                        <div className="flex gap-1 mb-2">
                          {Array.from({ length: 5 }).map((_, i) => (
                            <Star
                              key={i}
                              className={`w-4 h-4 ${
                                i < review.rating
                                  ? "fill-yellow-400 text-yellow-400"
                                  : "text-gray-300"
                              }`}
                            />
                          ))}
                        </div>
                        <p className="text-muted-foreground">{review.comment}</p>
                      </div>
                    </div>
                    {review.id !== reviews[reviews.length - 1].id && (
                      <Separator className="mt-6" />
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Right Column - Booking Card */}
          <div className="lg:col-span-1">
            <div
              className="bg-card rounded-3xl p-6 border border-border sticky top-24"
              style={{
                boxShadow:
                  "0px 51px 21px rgba(0, 0, 0, 0.01), 0px 29px 17px rgba(0, 0, 0, 0.03), 0px 13px 13px rgba(0, 0, 0, 0.05), 0px 3px 7px rgba(0, 0, 0, 0.06)",
              }}
            >
              <h3
                className="text-[20px] mb-4"
                style={{ fontFamily: "Manrope" }}
              >
                Quick Summary
              </h3>
              
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Category</span>
                  <Badge variant="outline" className="rounded-full">
                    {categoryName}
                  </Badge>
                </div>
                
                <Separator />
                
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Price per day</span>
                  <span className="text-primary">${pricePerDay}</span>
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Damage deposit</span>
                  <span>${damageDeposit}</span>
                </div>
                
                <Separator />
                
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Rating</span>
                  <div className="flex items-center gap-1">
                    <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                    <span>{averageRating.toFixed(1)}</span>
                  </div>
                </div>
                
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Reviews</span>
                  <span>{reviews.length}</span>
                </div>
                
                <Separator />
                
                <div className="flex items-center gap-2 text-muted-foreground">
                  <MapPin className="w-4 h-4" />
                  <span className="text-sm">{locationDisplay}</span>
                </div>
              </div>

              {dateRange.from && dateRange.to && (
                <>
                  <Separator className="my-6" />
                  <div className="p-4 bg-primary/10 rounded-xl">
                    <p className="text-sm text-muted-foreground mb-2">Your Selection</p>
                    <p className="mb-1">
                      {format(dateRange.from, "MMM d")} - {format(dateRange.to, "MMM d, yyyy")}
                    </p>
                    <p className="text-[24px] text-primary" style={{ fontFamily: "Manrope" }}>
                      ${totalWithFees.toFixed(2)}
                    </p>
                    <p className="text-sm text-muted-foreground mt-1">
                      Total for {numberOfDays} {numberOfDays === 1 ? "day" : "days"}
                    </p>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {isLightboxOpen && (
        <div
          className="fixed inset-0 bg-black/90 z-50 flex flex-col"
          onClick={closeLightbox}
        >
          <button
            type="button"
            onClick={handleCloseButtonClick}
            aria-label="Close image viewer"
            className="absolute top-6 right-6 text-white z-[1000] bg-black/50 hover:bg-black/70 rounded-full p-2 transition"
          >
            <X className="w-5 h-5" />
          </button>

          <div
            className="flex-1 flex items-center justify-center relative px-6"
            onClick={(event) => event.stopPropagation()}
          >
            <img
              src={images[currentImageIndex]}
              alt={`${listing.title} preview`}
              className="max-h-full max-w-full object-contain"
            />
            {images.length > 1 && (
              <>
                <button
                  type="button"
                  aria-label="View previous image"
                  className="absolute left-6 text-white bg-black/40 hover:bg-black/60 rounded-full p-3 transition"
                  onClick={(event) => {
                    event.stopPropagation();
                    previousImage();
                  }}
                >
                  <ChevronLeft className="w-6 h-6" />
                </button>
                <button
                  type="button"
                  aria-label="View next image"
                  className="absolute right-6 text-white bg-black/40 hover:bg-black/60 rounded-full p-3 transition"
                  onClick={(event) => {
                    event.stopPropagation();
                    nextImage();
                  }}
                >
                  <ChevronRight className="w-6 h-6" />
                </button>
              </>
            )}
          </div>

          {images.length > 1 && (
            <div
              className="p-4 bg-black/70 flex gap-3 overflow-x-auto"
              onClick={(event) => event.stopPropagation()}
            >
              {images.map((image, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => setCurrentImageIndex(index)}
                  className={`flex-shrink-0 w-20 h-20 rounded-xl overflow-hidden border-2 transition-all ${
                    index === currentImageIndex
                      ? "border-white"
                      : "border-transparent opacity-60 hover:opacity-100"
                  }`}
                >
                  <img
                    src={image}
                    alt={`${listing.title} thumbnail ${index + 1}`}
                    className="w-full h-full object-cover"
                  />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      </div>

      <LoginModal
        open={loginModalOpen}
        onOpenChange={setLoginModalOpen}
        defaultMode={loginModalMode}
        onAuthSuccess={() => setLoginModalOpen(false)}
      />
    </>
  );
}
