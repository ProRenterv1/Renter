import { useState, type ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { Header } from "@/components/Header";
import { Hero } from "@/components/Hero";
import { Categories } from "@/components/Categories";
import { Features } from "@/components/Features";
import { HowItWorks } from "@/components/HowItWorks";
import { CallToAction } from "@/components/CallToAction";
import { Footer } from "@/components/Footer";
import { Toaster } from "sonner";
import UserProfile from "@/pages/UserProfile";
import Messages from "@/pages/Messages";
import Feed from "@/pages/Feed";
import Booking from "@/pages/Booking";
import { AuthStore } from "@/lib/auth";
import type { Listing as ApiListing } from "@/lib/api";

function LandingPage() {
  return (
    <>
      <Header />
      <main>
        <Hero />
        {/* <FeaturedListings /> */}
        <Categories />
        <Features />
        <HowItWorks />
        <CallToAction />
      </main>
      <Footer />
    </>
  );
}

function FeedPage() {
  const [page, setPage] = useState<"feed" | "booking">("feed");
  const [selectedListing, setSelectedListing] = useState<ApiListing | null>(null);

  const handleOpenBooking = (listing: ApiListing) => {
    setSelectedListing(listing);
    setPage("booking");
  };

  const handleBackToFeed = () => {
    setSelectedListing(null);
    setPage("feed");
  };

  return (
    <>
      <Header />
      <main>
        {page === "feed" ? (
          <Feed onOpenBooking={handleOpenBooking} />
        ) : (
          <Booking listing={selectedListing} onBack={handleBackToFeed} />
        )}
      </main>
      <Footer />
    </>
  );
}

function UnauthorizedPage() {
  return (
    <>
      <Header />
      <main className="flex min-h-[60vh] items-center justify-center px-6 text-center">
        <div>
          <p className="text-sm uppercase tracking-wide text-muted-foreground">Error 403</p>
          <h1 className="mt-2 text-3xl font-semibold">Unauthorized</h1>
          <p className="mt-2 text-muted-foreground">
            You must be logged in to view this page. Please sign in and try again.
          </p>
        </div>
      </main>
      <Footer />
    </>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = Boolean(AuthStore.getTokens());
  if (!isAuthenticated) {
    return <UnauthorizedPage />;
  }
  return <>{children}</>;
}

export default function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/feed" element={<FeedPage />} />
        <Route
          path="/profile"
          element={
            <RequireAuth>
              <UserProfile />
            </RequireAuth>
          }
        />
        <Route
          path="/messages"
          element={
            <RequireAuth>
              <Messages />
            </RequireAuth>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toaster richColors expand position="top-center" />
    </div>
  );
}
