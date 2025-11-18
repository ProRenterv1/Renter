import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { useLocation } from "react-router-dom";
import { Header } from "../components/Header";
import { 
  User, 
  Lock, 
  Package, 
  PlusCircle, 
  History, 
  BarChart3, 
  CreditCard,
  Shield,
  Inbox
} from "lucide-react";
import { PersonalInfo } from "../components/profile/PersonalInfo";
import { Security } from "../components/profile/Security";
import { YourListings } from "../components/profile/YourListings";
import { AddListing } from "../components/profile/AddListing";
import { RecentRentals } from "../components/profile/RecentRentals";
import { Statistics } from "../components/profile/Statistics";
import { Payments } from "../components/profile/Payments";
import { EditListing } from "../components/profile/EditListing";
import { BookingRequests } from "../components/profile/BookingRequests";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { toast } from "sonner";
import { AuthStore, type Profile } from "@/lib/auth";
import { authAPI, bookingsAPI, type Listing } from "@/lib/api";

const TAB_KEYS = [
  "personal",
  "security",
  "listings",
  "add-listing",
  "rentals",
  "statistics",
  "payments",
  "booking-requests",
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
      return;
    }

    let subscribed = true;
    const POLL_INTERVAL_MS = 15000;

    const fetchPendingCount = async () => {
      try {
        const response = await bookingsAPI.pendingRequestsCount();
        if (!subscribed) {
          return;
        }
        const nextCount = Number(response.pending_requests ?? 0);
        setPendingBookingCount((current) => (current === nextCount ? current : nextCount));
      } catch (error) {
        if (import.meta.env.DEV) {
          console.warn("Failed to fetch pending booking count", error);
        }
      }
    };

    fetchPendingCount();
    const intervalId = window.setInterval(fetchPendingCount, POLL_INTERVAL_MS);

    return () => {
      subscribed = false;
      window.clearInterval(intervalId);
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

  const triggerAvatarPicker = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setAvatarUploading(true);
    try {
      const updatedProfile = await authAPI.uploadAvatar(file);
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

  const tabs = [
    { id: "personal" as Tab, label: "Personal Info", icon: User },
    { id: "security" as Tab, label: "Security", icon: Lock },
    { id: "listings" as Tab, label: "Your Listings", icon: Package },
    { id: "add-listing" as Tab, label: "Add Listing", icon: PlusCircle },
    { id: "booking-requests" as Tab, label: "Booking Requests", icon: Inbox },
    { id: "rentals" as Tab, label: "Recent Rentals", icon: History },
    { id: "statistics" as Tab, label: "Statistics", icon: BarChart3 },
    { id: "payments" as Tab, label: "Payments", icon: CreditCard },
  ];

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header />
      
      <div className="flex-1 lg:flex">
        {/* Sidebar */}
        <aside className="hidden lg:flex lg:flex-col lg:w-64 lg:fixed lg:top-16 lg:bottom-0 lg:border-r bg-card lg:overflow-y-auto">
          <div className="p-6 border-b">
            <div className="flex items-center gap-3">
                <Avatar className="w-16 h-16">
                <AvatarImage
                  src={hasCustomAvatar ? profile?.avatar_url ?? "" : undefined}
                  alt={displayName}
                />
                <AvatarFallback className="bg-[var(--primary)]" style={{ color: "var(--primary-foreground)" }}>
                  {initials}
                </AvatarFallback>
              </Avatar>
              <div>
                <h3 className="font-medium">{displayName}</h3>
                <div className="flex items-center gap-1 mt-1">
                  <Badge variant="secondary" className="text-xs">
                    <Shield className="w-3 h-3 mr-1" />
                    Verified
                  </Badge>
                </div>
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
                        <span className="ml-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--error-solid)] text-[10px] font-semibold leading-none text-white">
                          {pendingBookingCount > 99 ? "99+" : pendingBookingCount}
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
            {activeTab === "personal" && <PersonalInfo onProfileUpdate={setProfile} />}
            {activeTab === "security" && <Security />}
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
            {activeTab === "rentals" && <RecentRentals />}
            {activeTab === "statistics" && <Statistics />}
            {activeTab === "payments" && <Payments />}
            {activeTab === "booking-requests" && (
              <BookingRequests onPendingCountChange={setPendingBookingCount} />
            )}
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
