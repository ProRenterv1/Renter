import { useState } from "react";
import { Header } from "../components/Header";
import { 
  User, 
  Lock, 
  Package, 
  PlusCircle, 
  History, 
  BarChart3, 
  CreditCard,
  Shield
} from "lucide-react";
import { PersonalInfo } from "../components/profile/PersonalInfo";
import { Security } from "../components/profile/Security";
import { YourListings } from "../components/profile/YourListings";
import { AddListing } from "../components/profile/AddListing";
import { RecentRentals } from "../components/profile/RecentRentals";
import { Statistics } from "../components/profile/Statistics";
import { Payments } from "../components/profile/Payments";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Badge } from "../components/ui/badge";
import { AuthStore, type Profile } from "@/lib/auth";

type Tab = "personal" | "security" | "listings" | "add-listing" | "rentals" | "statistics" | "payments";

interface UserProfileProps {
  onNavigateToMessages?: () => void;
  onNavigateToProfile?: () => void;
  onLogout?: () => void;
}

export default function UserProfile({ onNavigateToMessages, onNavigateToProfile, onLogout }: UserProfileProps) {
  const [activeTab, setActiveTab] = useState<Tab>("personal");
  const [profile, setProfile] = useState<Profile | null>(() => AuthStore.getCurrentUser());

  const firstName = profile?.first_name?.trim() ?? "";
  const lastName = profile?.last_name?.trim() ?? "";
  const displayName = `${firstName} ${lastName}`.trim() || profile?.username || "Your Profile";
  const firstInitial = firstName ? firstName[0] : "";
  const lastInitial = lastName ? lastName[0] : "";
  const initialsSource = (firstInitial + lastInitial) || firstInitial || lastInitial || "";
  const fallbackInitial = displayName ? displayName[0] : "U";
  const initials = (initialsSource || fallbackInitial).toUpperCase();

  const tabs = [
    { id: "personal" as Tab, label: "Personal Info", icon: User },
    { id: "security" as Tab, label: "Security", icon: Lock },
    { id: "listings" as Tab, label: "Your Listings", icon: Package },
    { id: "add-listing" as Tab, label: "Add Listing", icon: PlusCircle },
    { id: "rentals" as Tab, label: "Recent Rentals", icon: History },
    { id: "statistics" as Tab, label: "Statistics", icon: BarChart3 },
    { id: "payments" as Tab, label: "Payments", icon: CreditCard },
  ];

  return (
    <div className="min-h-screen bg-background">
      <Header 
        isProfilePage={true} 
        onNavigateToMessages={onNavigateToMessages}
        onNavigateToProfile={onNavigateToProfile}
        onLogout={onLogout}
      />
      
      <div className="flex">
        {/* Sidebar */}
        <aside className="w-64 min-h-[calc(100vh-64px)] border-r bg-card hidden lg:block sticky top-16">
          <div className="p-6 border-b">
            <div className="flex items-center gap-3">
              <Avatar className="w-16 h-16">
                <AvatarImage src="" alt={displayName} />
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
                      {tab.label}
                    </button>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 p-6 lg:p-8">
          <div className="max-w-5xl mx-auto">
            {activeTab === "personal" && <PersonalInfo onProfileUpdate={setProfile} />}
            {activeTab === "security" && <Security />}
            {activeTab === "listings" && <YourListings />}
            {activeTab === "add-listing" && <AddListing />}
            {activeTab === "rentals" && <RecentRentals />}
            {activeTab === "statistics" && <Statistics />}
            {activeTab === "payments" && <Payments />}
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
