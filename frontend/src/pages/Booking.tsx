import { useState } from "react";
import {
  ArrowLeft,
  Star,
  MapPin,
  Shield,
  ChevronLeft,
  ChevronRight,
  Calendar as CalendarIcon,
} from "lucide-react";
import { Button } from "../components/ui/button";
import { Calendar } from "../components/ui/calendar";
import { Badge } from "../components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Separator } from "../components/ui/separator";
import { addDays, differenceInDays, format } from "date-fns";
import { bookingsAPI, type Listing as ApiListing } from "@/lib/api";

interface BookingPageProps {
  listing: ApiListing | null;
  onBack: () => void;
  onNavigateToMessages?: () => void;
  onNavigateToProfile?: () => void;
  onLogout?: () => void;
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
  onNavigateToMessages,
  onNavigateToProfile,
  onLogout,
}: BookingPageProps) {
  const [currentImageIndex, setCurrentImageIndex] = useState(0);
  const [dateRange, setDateRange] = useState<{
    from: Date | undefined;
    to: Date | undefined;
  }>({
    from: undefined,
    to: undefined,
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState(false);

  if (!listing) {
    return (
      <div className="min-h-screen w-full" style={{ backgroundColor: "#f9f9f9" }}>
        <div className="border-b border-border bg-card sticky top-0 z-10">
          <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
            <Button variant="ghost" onClick={onBack} className="gap-2">
              <ArrowLeft className="w-4 h-4" />
              Back to Feed
            </Button>
          </div>
        </div>
        <div className="max-w-7xl mx-auto px-6 py-8">
          <p className="text-muted-foreground">Listing is not available.</p>
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
  const postalCodeOrCity = listing.city || "Unknown";
  const categoryName = listing.category_name || "Other";
  const tags = categoryName ? [categoryName] : [];

  const reviews: Review[] = [];
  const averageRating = reviews.length
    ? reviews.reduce((sum, review) => sum + review.rating, 0) / reviews.length
    : 5;

  const owner = {
    name: listing.owner_username ?? "Owner",
    avatar: "",
    rating: averageRating,
    reviewCount: reviews.length,
    joinedDate: "2025",
  };

  const unavailableDates: Date[] = [];

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

  const isDateUnavailable = (date: Date) =>
    unavailableDates.some(
      (unavailableDate) =>
        format(unavailableDate, "yyyy-MM-dd") === format(date, "yyyy-MM-dd"),
    );

  async function handleRequestBooking() {
    if (!listing || !dateRange.from || !dateRange.to) return;
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
    <div
      className="min-h-screen w-full"
      style={{ backgroundColor: "#f9f9f9" }}
    >
      {/* Header */}
      <div className="border-b border-border bg-card sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button variant="ghost" onClick={onBack} className="gap-2">
              <ArrowLeft className="w-4 h-4" />
              Back to Feed
            </Button>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="ghost" onClick={onNavigateToMessages}>
              Messages
            </Button>
            <Button variant="ghost" onClick={onNavigateToProfile}>
              Profile
            </Button>
            <Button variant="outline" onClick={onLogout}>
              Logout
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
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
                <img
                  src={images[currentImageIndex]}
                  alt={listing.title}
                  className="w-full h-full object-cover"
                />
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
                <p className="text-muted-foreground leading-relaxed">
                  {listing.description}
                </p>
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
                  <span>Postal Code: {postalCodeOrCity}</span>
                </div>
                <div className="mt-4 h-48 bg-muted rounded-xl overflow-hidden border border-border">
                  {/* Simple placeholder map - in production, use Google Maps or similar */}
                  <div className="w-full h-full flex items-center justify-center text-muted-foreground">
                    <div className="text-center">
                      <MapPin className="w-8 h-8 mx-auto mb-2" />
                      <p>Approximate location based on {postalCodeOrCity}</p>
                    </div>
                  </div>
                </div>
              </div>

              <Separator className="my-6" />

              {/* Damage Deposit */}
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

            {/* Calendar Section */}
            <div
              className="bg-card rounded-3xl p-6 border border-border"
              style={{
                boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
              }}
            >
              <div className="mb-6">
                <div className="flex items-baseline gap-2 mb-1">
                  <span className="text-[32px] text-primary">
                    ${pricePerDay}
                  </span>
                  <span className="text-muted-foreground">/ day</span>
                </div>
              </div>

              <Separator className="my-6" />

              <h3
                className="text-[20px] mb-4"
                style={{ fontFamily: "Manrope" }}
              >
                Select Your Dates
              </h3>
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
                    isDateUnavailable(date) || date < new Date()
                  }
                  className="rounded-md"
                />
              </div>
              {dateRange.from && dateRange.to && (
                <div className="mt-4 p-4 bg-accent rounded-xl">
                  <p className="text-accent-foreground">
                    {format(dateRange.from, "MMM d, yyyy")} -{" "}
                    {format(dateRange.to, "MMM d, yyyy")}
                  </p>
                  <p className="text-accent-foreground/80 mt-1">
                    {numberOfDays} {numberOfDays === 1 ? "day" : "days"}
                  </p>
                </div>
              )}

              {/* Price Breakdown */}
              {numberOfDays > 0 && (
                <>
                  <Separator className="my-6" />
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">
                        ${pricePerDay} x {numberOfDays}{" "}
                        {numberOfDays === 1 ? "day" : "days"}
                      </span>
                      <span>${totalPrice}</span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">Service fee</span>
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
                  </div>
                </>
              )}

              <Button
                className="w-full mt-6 rounded-full"
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
                <p className="text-destructive text-sm mt-3">{submitError}</p>
              )}
              {submitSuccess && (
                <p className="text-sm mt-3 text-green-600">
                  Booking request sent. You will see it in your bookings soon.
                </p>
              )}

              {numberOfDays > 0 && (
                <p className="text-center text-muted-foreground mt-4">
                  You won't be charged yet
                </p>
              )}
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
                  <AvatarImage src={owner.avatar} />
                  <AvatarFallback>
                    {owner.name
                      .split(" ")
                      .map((n) => n[0])
                      .join("")}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <p className="text-[18px] mb-1" style={{ fontFamily: "Manrope" }}>
                    {owner.name}
                  </p>
                  <div className="flex items-center gap-3 text-muted-foreground mb-2">
                    <div className="flex items-center gap-1">
                      <Star className="w-4 h-4 fill-yellow-400 text-yellow-400" />
                      <span>{owner.rating}</span>
                    </div>
                    <span>•</span>
                    <span>{owner.reviewCount} reviews</span>
                    <span>•</span>
                    <span>Joined {owner.joinedDate}</span>
                  </div>
                  <Button variant="outline" className="rounded-full mt-2">
                    Contact Owner
                  </Button>
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
                  <span className="text-sm">{postalCodeOrCity}</span>
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
    </div>
  );
}
