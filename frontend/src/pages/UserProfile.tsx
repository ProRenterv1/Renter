import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useLocation } from "react-router-dom";
import { Header } from "../components/Header";
import {
  User,
  Package,
  PlusCircle,
  BarChart3,
  CreditCard,
  Shield,
  Inbox,
  Briefcase,
  History,
} from "lucide-react";
import { PersonalInfo } from "../components/profile/PersonalInfo";
import { Security } from "../components/profile/Security";
import { YourListings } from "../components/profile/YourListings";
import { AddListing } from "../components/profile/AddListing";
import { YourRentals } from "../components/profile/YourRentals";
import { RecentRentals } from "../components/profile/RecentRentals";
import { Statistics } from "../components/profile/Statistics";
import { Payments } from "../components/profile/Payments";
import { EditListing } from "../components/profile/EditListing";
import { BookingRequests } from "../components/profile/BookingRequests";
import { AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import { AuthStore, type Profile } from "@/lib/auth";
import {
  authAPI,
  bookingsAPI,
  identityAPI,
  disputesAPI,
  type IdentityVerificationStatus,
  type Listing,
} from "@/lib/api";
import { VerifiedAvatar } from "@/components/VerifiedAvatar";
import { DisputesPanel, countActiveDisputes } from "@/components/disputes/DisputesPanel";
import { Separator } from "@/components/ui/separator";
import { compressImageFile } from "@/lib/imageCompression";

const TAB_KEYS = [
  "personal",
  "listings",
  "add-listing",
  "rentals",
  "rental-history",
  "statistics",
  "payments",
  "booking-requests",
  "disputes",
] as const;

type Tab = (typeof TAB_KEYS)[number];

const DEFAULT_TAB: Tab = "personal";

const isValidTab = (value: string | null): value is Tab => {
  return typeof value === "string" && (TAB_KEYS as readonly string[]).includes(value);
};

export default function UserProfile() {
  const location = useLocation();
  const [activeTab, setActiveTab] = useState<Tab>(() => {
    const params = new URLSearchParams(location.search);
    const requestedTab = params.get("tab");
    return isValidTab(requestedTab) ? requestedTab : DEFAULT_TAB;
  });
  const [profile, setProfile] = useState<Profile | null>(() => AuthStore.getCurrentUser());
  const [listingBeingEdited, setListingBeingEdited] = useState<Listing | null>(null);
  const [listingsRefreshToken, setListingsRefreshToken] = useState(0);
  const [avatarUploading, setAvatarUploading] = useState(false);
  const [pendingBookingCount, setPendingBookingCount] = useState(0);
  const [unpaidRentalsCount, setUnpaidRentalsCount] = useState(0);
  const [activeDisputeCount, setActiveDisputeCount] = useState(0);
  const [identityStatus, setIdentityStatus] = useState<IdentityVerificationStatus | "none">(
    "none",
  );
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (activeTab !== "listings") {
      setListingBeingEdited(null);
    }
  }, [activeTab]);

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const requestedTab = params.get("tab");
    if (isValidTab(requestedTab)) {
      setActiveTab((current) => (current === requestedTab ? current : requestedTab));
      return;
    }
    if (!requestedTab) {
      setActiveTab((current) => (current === DEFAULT_TAB ? current : DEFAULT_TAB));
    }
  }, [location.search]);

  useEffect(() => {
    if (!profile?.id) {
      setPendingBookingCount(0);
      setUnpaidRentalsCount(0);
      return;
    }

    let subscribed = true;
    const POLL_INTERVAL_MS = 15000;

    const fetchSidebarCounters = async () => {
      try {
        const response = await bookingsAPI.pendingRequestsCount();
        if (!subscribed) {
          return;
        }
        const nextPendingCount = Number(response.pending_requests ?? 0);
        const nextUnpaidCount = Number(
          response.renter_unpaid_bookings ?? response.unpaid_bookings ?? 0,
        );
        setPendingBookingCount((current) =>
          current === nextPendingCount ? current : nextPendingCount,
        );
        setUnpaidRentalsCount((current) =>
          current === nextUnpaidCount ? current : nextUnpaidCount,
        );
      } catch (error) {
        if (import.meta.env.DEV) {
          console.warn("Failed to fetch booking sidebar counters", error);
        }
      }
    };

    fetchSidebarCounters();
    const intervalId = window.setInterval(fetchSidebarCounters, POLL_INTERVAL_MS);

    return () => {
      subscribed = false;
      window.clearInterval(intervalId);
    };
  }, [profile?.id]);

  useEffect(() => {
    if (!profile?.id) {
      setActiveDisputeCount(0);
      return;
    }

    let cancelled = false;
    const POLL_INTERVAL_MS = 15000;

    const fetchActiveDisputes = async () => {
      try {
        const data = await disputesAPI.list();
        if (cancelled) return;
        const nextCount = countActiveDisputes(data || []);
        setActiveDisputeCount((current) => (current === nextCount ? current : nextCount));
      } catch (error) {
        if (import.meta.env.DEV) {
          console.warn("Failed to fetch dispute sidebar counter", error);
        }
      }
    };

    void fetchActiveDisputes();
    const intervalId = window.setInterval(fetchActiveDisputes, POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [profile?.id]);

  useEffect(() => {
    if (!profile?.id) {
      setIdentityStatus("none");
      return;
    }

    let cancelled = false;
    const loadIdentityStatus = async () => {
      try {
        const res = await identityAPI.status();
        if (cancelled) return;
        const nextStatus: IdentityVerificationStatus | "none" = res.verified
          ? "verified"
          : res.latest?.status
            ? (res.latest.status as IdentityVerificationStatus)
            : "none";
        setIdentityStatus((current) => (current === nextStatus ? current : nextStatus));
      } catch (error) {
        if (!cancelled) {
          setIdentityStatus((current) => (current === "none" ? current : "none"));
        }
      }
    };

    void loadIdentityStatus();

    return () => {
      cancelled = true;
    };
  }, [profile?.id]);

  const handleListingSelected = (listing: Listing) => {
    setListingBeingEdited(listing);
  };

  const handleListingUpdated = (updatedListing: Listing) => {
    setListingBeingEdited(updatedListing);
    setListingsRefreshToken((token) => token + 1);
  };

  const handleListingDeleted = () => {
    setListingBeingEdited(null);
    setListingsRefreshToken((token) => token + 1);
  };

  const handleBackToListings = () => {
    setListingBeingEdited(null);
  };

  const firstName = profile?.first_name?.trim() ?? "";
  const lastName = profile?.last_name?.trim() ?? "";
  const displayName = `${firstName} ${lastName}`.trim() || profile?.username || "Your Profile";
  const firstInitial = firstName ? firstName[0] : "";
  const lastInitial = lastName ? lastName[0] : "";
  const initialsSource = (firstInitial + lastInitial) || firstInitial || lastInitial || "";
  const fallbackInitial = displayName ? displayName[0] : "U";
  const initials = (initialsSource || fallbackInitial).toUpperCase();
  const hasCustomAvatar = Boolean(profile?.avatar_uploaded);
  const isIdentityVerified = identityStatus === "verified";

  const triggerAvatarPicker = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setAvatarUploading(true);
    try {
      const compressed = await compressImageFile(file);
      const updatedProfile = await authAPI.uploadAvatar(compressed.file);
      setProfile(updatedProfile);
      AuthStore.setCurrentUser(updatedProfile);
      toast.success("Profile photo updated.");
    } catch (error) {
      console.error("Failed to upload avatar", error);
      toast.error("Unable to upload photo. Please try again.");
    } finally {
      setAvatarUploading(false);
      if (event.target) {
        event.target.value = "";
      }
    }
  };

  const handleAvatarDelete = async () => {
    if (!hasCustomAvatar) {
      return;
    }
    setAvatarUploading(true);
    try {
      const updatedProfile = await authAPI.deleteAvatar();
      setProfile(updatedProfile);
      AuthStore.setCurrentUser(updatedProfile);
      toast.success("Profile photo removed.");
    } catch (error) {
      console.error("Failed to delete avatar", error);
      toast.error("Unable to delete photo. Please try again.");
    } finally {
      setAvatarUploading(false);
    }
  };

  const handleIdentityStatusChange = (status: IdentityVerificationStatus | "none") => {
    setIdentityStatus((current) => (current === status ? current : status));
  };

  const tabs = [
    { id: "personal" as Tab, label: "Personal Info", icon: User },
    { id: "listings" as Tab, label: "Your Listings", icon: Package },
    { id: "add-listing" as Tab, label: "Add Listing", icon: PlusCircle },
    { id: "booking-requests" as Tab, label: "Booking Requests", icon: Inbox },
    { id: "rentals" as Tab, label: "Your rentals", icon: Briefcase },
    { id: "rental-history" as Tab, label: "Recent Rentals", icon: History },
    { id: "statistics" as Tab, label: "Statistics", icon: BarChart3 },
    { id: "payments" as Tab, label: "Payments", icon: CreditCard },
    { id: "disputes" as Tab, label: "Disputes", icon: Shield },
  ];

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />
      
      <div className="flex-1 lg:flex">
        {/* Sidebar */}
        <aside className="hidden lg:flex lg:flex-col lg:w-64 lg:fixed lg:top-16 lg:bottom-0 lg:border-r bg-card lg:overflow-y-auto">
          <div className="p-6 border-b">
            <div className="flex items-center gap-3">
                <VerifiedAvatar isVerified={isIdentityVerified} className="w-16 h-16">
                <AvatarImage
                  src={hasCustomAvatar ? profile?.avatar_url ?? "" : undefined}
                  alt={displayName}
                />
                <AvatarFallback className="bg-[var(--primary)]" style={{ color: "var(--primary-foreground)" }}>
                  {initials}
                </AvatarFallback>
              </VerifiedAvatar>
              <div>
                <h3 className="font-medium">{displayName}</h3>
                {isIdentityVerified && (
                  <div className="flex items-center gap-1 mt-1">
                    <Badge variant="secondary" className="text-xs">
                      <Shield className="w-3 h-3 mr-1" />
                      Verified
                    </Badge>
                  </div>
                )}
                <div className="mt-2 space-y-1">
                  <button
                    type="button"
                    onClick={triggerAvatarPicker}
                    className="text-xs font-medium text-[var(--primary)] hover:underline disabled:opacity-60"
                    disabled={avatarUploading}
                  >
                    {avatarUploading ? "Processing..." : "Change Photo"}
                  </button>
                  {hasCustomAvatar && (
                    <button
                      type="button"
                      onClick={handleAvatarDelete}
                      className="text-xs font-medium text-destructive hover:underline disabled:opacity-60"
                      disabled={avatarUploading}
                    >
                      Delete Photo
                    </button>
                  )}
                  <input
                    type="file"
                    accept="image/*"
                    ref={fileInputRef}
                    className="hidden"
                    onChange={handleAvatarChange}
                  />
                </div>
              </div>
            </div>
          </div>

          <nav className="p-4">
            <ul className="space-y-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <li key={tab.id}>
                    <button
                      onClick={() => setActiveTab(tab.id)}
                      className={`w-full flex items-center gap-3 px-4 py-3 rounded-lg text-sm transition-colors ${
                        activeTab === tab.id
                          ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                          : "hover:bg-muted"
                      }`}
                    >
                      <Icon className="w-4 h-4" />
                      <span className="flex-1 text-left">{tab.label}</span>
                      {tab.id === "booking-requests" && pendingBookingCount > 0 && (
                        <span
                          className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold leading-none text-white"
                          style={{ backgroundColor: "#5B8CA6" }}
                        >
                          {pendingBookingCount > 99 ? "99+" : pendingBookingCount}
                        </span>
                      )}
                      {tab.id === "rentals" && unpaidRentalsCount > 0 && (
                        <span
                          className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold leading-none text-white"
                          style={{ backgroundColor: "#5B8CA6" }}
                        >
                          {unpaidRentalsCount > 99 ? "99+" : unpaidRentalsCount}
                        </span>
                      )}
                      {tab.id === "disputes" && activeDisputeCount > 0 && (
                        <span
                          className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold leading-none text-white"
                          style={{ backgroundColor: "#5B8CA6" }}
                        >
                          {activeDisputeCount > 99 ? "99+" : activeDisputeCount}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-6 lg:p-8 lg:ml-64">
          <div className="max-w-5xl mx-auto">
            {activeTab === "personal" && (
              <div className="space-y-8">
                <PersonalInfo onProfileUpdate={setProfile} />
                <Separator />
                {/* Security settings relocated into Personal Info tab */}
                <Security onIdentityStatusChange={handleIdentityStatusChange} />
              </div>
            )}
            {activeTab === "listings" &&
              (listingBeingEdited ? (
                <EditListing
                  listing={listingBeingEdited}
                  onBackToListings={handleBackToListings}
                  onListingUpdated={handleListingUpdated}
                  onListingDeleted={handleListingDeleted}
                />
              ) : (
                <YourListings
                  onAddListingClick={() => {
                    setListingBeingEdited(null);
                    setActiveTab("add-listing");
                  }}
                  onListingSelect={handleListingSelected}
                  refreshToken={listingsRefreshToken}
                />
              ))}
            {activeTab === "add-listing" && <AddListing />}
            {activeTab === "rentals" && (
              <YourRentals onUnpaidRentalsChange={setUnpaidRentalsCount} />
            )}
            {activeTab === "rental-history" && <RecentRentals />}
            {activeTab === "statistics" && <Statistics />}
            {activeTab === "payments" && <Payments />}
            {activeTab === "booking-requests" && (
              <BookingRequests onPendingCountChange={setPendingBookingCount} />
            )}
            {activeTab === "disputes" && <DisputesPanel onCountChange={setActiveDisputeCount} />}
          </div>
        </main>
      </div>

      {/* Footer */}
      <footer className="border-t py-6 text-center text-sm" style={{ color: "var(--text-muted)" }}>
        © 2025 Renter. All rights reserved.
      </footer>
    </div>
  );
}
