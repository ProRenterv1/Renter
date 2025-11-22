import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { format } from "date-fns";
import { Star } from "lucide-react";

import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ListingCard } from "@/components/listings/ListingCard";
import { listingsAPI, usersAPI, type Listing, type PublicProfile as PublicProfileType } from "@/lib/api";
import { cn } from "@/lib/utils";
import { VerifiedAvatar } from "@/components/VerifiedAvatar";

const PROFILE_TABS = ["listings", "reviews"] as const;
type ProfileTab = (typeof PROFILE_TABS)[number];

function ProfileHeaderSkeleton() {
  return (
    <div className="rounded-3xl bg-card p-6 shadow-sm">
      <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-4">
          <Skeleton className="h-24 w-24 rounded-full" />
          <div className="space-y-3">
            <Skeleton className="h-6 w-40 rounded-full" />
            <Skeleton className="h-4 w-32 rounded-full" />
          </div>
        </div>
        <Skeleton className="h-10 w-64 rounded-full" />
      </div>
    </div>
  );
}

export default function PublicProfile() {
  const { userId } = useParams<{ userId: string }>();
  const navigate = useNavigate();
  const [profile, setProfile] = useState<PublicProfileType | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<ProfileTab>("listings");
  const [listings, setListings] = useState<Listing[]>([]);
  const [listingsLoading, setListingsLoading] = useState(true);
  const [listingsError, setListingsError] = useState<string | null>(null);

  const numericUserId = Number(userId);
  const isValidUserId = Number.isInteger(numericUserId) && numericUserId > 0;

  useEffect(() => {
    if (!isValidUserId) {
      setProfile(null);
      setProfileError("User profile could not be loaded.");
      setProfileLoading(false);
      return;
    }

    let isActive = true;
    setProfileLoading(true);
    setProfileError(null);

    usersAPI
      .publicProfile(numericUserId)
      .then((data) => {
        if (!isActive) return;
        setProfile(data);
      })
      .catch((error) => {
        console.error("Failed to load public profile", error);
        if (!isActive) return;
        setProfile(null);
        setProfileError("User profile could not be loaded.");
      })
      .finally(() => {
        if (!isActive) return;
        setProfileLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, [isValidUserId, numericUserId]);

  useEffect(() => {
    if (!profile?.id) {
      setListings([]);
      setListingsError(null);
      setListingsLoading(false);
      return;
    }

    let isActive = true;
    setListingsLoading(true);
    setListingsError(null);

    listingsAPI
      .list({ owner_id: profile.id })
      .then((data) => {
        if (!isActive) return;
        setListings(data.results ?? []);
      })
      .catch((error) => {
        console.error("Failed to load listings for profile", error);
        if (!isActive) return;
        setListings([]);
        setListingsError("Unable to load listings for this user.");
      })
      .finally(() => {
        if (!isActive) return;
        setListingsLoading(false);
      });

    return () => {
      isActive = false;
    };
  }, [profile?.id]);

  const displayName = useMemo(() => {
    if (!profile) return "User";
    const fromNames = [profile.first_name, profile.last_name].filter(Boolean).join(" ").trim();
    return fromNames || profile.username || "User";
  }, [profile]);

  const initials = useMemo(() => {
    if (!profile) return "U";
    const first = profile.first_name?.trim().charAt(0) ?? "";
    const last = profile.last_name?.trim().charAt(0) ?? "";
    const fallback = profile.username?.charAt(0) ?? "U";
    return (first + last || fallback).toUpperCase();
  }, [profile]);

  const joinedLabel = useMemo(() => {
    if (!profile?.date_joined) return null;
    const parsed = new Date(profile.date_joined);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    try {
      return format(parsed, "MMMM yyyy");
    } catch {
      return null;
    }
  }, [profile?.date_joined]);

  const ratingValue =
    typeof profile?.rating === "number" ? profile.rating : 5.0;
  const reviewCount =
    typeof profile?.review_count === "number" ? profile.review_count : 0;

  const handleCardClick = (listing: Listing) => {
    navigate(`/listings/${listing.slug}`, { state: { listing } });
  };

  const tabButtons = (
    <div className="inline-flex rounded-full border border-border bg-card p-1">
      {PROFILE_TABS.map((tab) => (
        <Button
          key={tab}
          type="button"
          variant={activeTab === tab ? "default" : "ghost"}
          className={cn(
            "rounded-full px-6 py-2 text-sm font-medium transition-colors",
            activeTab === tab
              ? ""
              : "text-muted-foreground hover:text-foreground",
          )}
          onClick={() => setActiveTab(tab)}
        >
          {tab === "listings" ? "Listings" : "Reviews"}
        </Button>
      ))}
    </div>
  );

  const renderListingsSection = () => {
    if (listingsLoading) {
      return (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="rounded-2xl border border-border bg-card p-4 shadow-sm"
            >
              <Skeleton className="mb-4 h-48 w-full rounded-2xl" />
              <Skeleton className="mb-2 h-4 w-3/4 rounded-full" />
              <Skeleton className="h-4 w-1/3 rounded-full" />
            </div>
          ))}
        </div>
      );
    }

    if (listingsError) {
      return (
        <div className="rounded-2xl border border-destructive/30 bg-destructive/5 p-6 text-destructive">
          {listingsError}
        </div>
      );
    }

    if (!listings.length) {
      return (
        <div className="rounded-2xl border border-dashed border-border bg-card p-10 text-center">
          <p className="text-lg font-semibold" style={{ fontFamily: "Manrope" }}>
            No tools listed yet.
          </p>
          <p className="mt-2 text-muted-foreground">
            Once this user publishes listings, they will appear here.
          </p>
        </div>
      );
    }

    return (
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
        {listings.map((listing) => (
          <ListingCard
            key={listing.id}
            listing={listing}
            onClick={handleCardClick}
          />
        ))}
      </div>
    );
  };

  const renderReviewsSection = () => (
    <div className="rounded-3xl border border-dashed border-border bg-card p-10 text-center">
      <h3 className="text-xl font-semibold" style={{ fontFamily: "Manrope" }}>
        Reviews
      </h3>
      <p className="mt-2 text-muted-foreground">
        No reviews yet. Reviews will appear here once implemented.
      </p>
    </div>
  );

  return (
    <>
      <Header />
      <main className="bg-muted/10 py-10 text-foreground">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-8 px-4 sm:px-6 lg:px-8">
          {profileLoading ? (
            <ProfileHeaderSkeleton />
          ) : profile ? (
            <div className="rounded-3xl bg-card p-6 shadow-sm">
              <div className="flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
                <div className="flex flex-1 items-center gap-4">
                  <VerifiedAvatar
                    isVerified={Boolean(profile.identity_verified)}
                    className="h-24 w-24 border-2 border-primary/10 sm:h-28 sm:w-28"
                  >
                    <AvatarImage src={profile.avatar_url ?? undefined} alt={displayName} />
                    <AvatarFallback className="text-xl font-semibold">
                      {initials}
                    </AvatarFallback>
                  </VerifiedAvatar>
                  <div>
                    <h1 className="text-2xl font-semibold" style={{ fontFamily: "Manrope" }}>
                      {displayName}
                    </h1>
                    {profile.city && (
                      <Badge variant="secondary" className="mt-2 rounded-full px-3 py-1">
                        {profile.city}
                      </Badge>
                    )}
                    <p className="mt-3 flex items-center gap-2 text-sm text-muted-foreground">
                      <Star className="h-5 w-5 text-yellow-500" fill="currentColor" />
                      <span className="text-base font-semibold text-foreground">
                        {ratingValue.toFixed(1)}
                      </span>
                      <span className="text-muted-foreground">
                        ({reviewCount} {reviewCount === 1 ? "review" : "reviews"})
                      </span>
                    </p>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {joinedLabel ? `Joined ${joinedLabel}` : "Joined recently"}
                    </p>
                  </div>
                </div>
                {tabButtons}
              </div>
            </div>
          ) : (
            <div className="rounded-3xl border border-destructive/30 bg-destructive/5 p-6 text-destructive">
              {profileError ?? "User profile could not be loaded."}
            </div>
          )}

          {profile && (
            <>
              {activeTab === "listings" && renderListingsSection()}
              {activeTab === "reviews" && renderReviewsSection()}
            </>
          )}
        </div>
      </main>
      <Footer />
    </>
  );
}
