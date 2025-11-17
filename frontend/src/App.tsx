import { useEffect, useState, type ReactNode } from "react";
import { Routes, Route, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
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
import AllCategoriesPage from "@/pages/AllCategories";
import PublicProfile from "@/pages/PublicProfile";
import { AuthStore } from "@/lib/auth";
import { listingsAPI, type Listing as ApiListing } from "@/lib/api";

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
  const navigate = useNavigate();

  const handleOpenBooking = (listing: ApiListing) => {
    navigate(`/listings/${listing.slug}`, { state: { listing } });
  };

  return (
    <>
      <Header />
      <main>
        <Feed onOpenBooking={handleOpenBooking} />
      </main>
      <Footer />
    </>
  );
}

type BookingLocationState = {
  listing?: ApiListing;
} | null;

function BookingRoutePage() {
  const navigate = useNavigate();
  const location = useLocation();
  const { slug } = useParams<{ slug: string }>();
  const initialListing =
    (location.state as BookingLocationState)?.listing ?? null;
  const [listing, setListing] = useState<ApiListing | null>(initialListing);
  const [loading, setLoading] = useState(!initialListing);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) {
      setListing(null);
      setLoading(false);
      setError("Listing not found.");
      return;
    }
    setListing((current) =>
      current && current.slug === slug ? current : null,
    );
    setLoading(true);
    setError(null);
    let isMounted = true;
    listingsAPI
      .retrieve(slug)
      .then((data) => {
        if (!isMounted) return;
        setListing(data);
      })
      .catch((err) => {
        console.error("Failed to load listing", err);
        if (!isMounted) return;
        setError("Listing could not be found.");
        setListing(null);
      })
      .finally(() => {
        if (!isMounted) return;
        setLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [slug]);

  return (
    <Booking
      listing={listing}
      onBack={() => navigate("/feed")}
      isLoading={loading}
      errorMessage={error ?? undefined}
    />
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
  const location = useLocation();

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    if (location.hash) {
      const sectionId = location.hash.replace("#", "");
      const element = document.getElementById(sectionId);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return;
    }
    window.scrollTo({ top: 0 });
  }, [location.pathname, location.hash]);

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route path="/feed" element={<FeedPage />} />
        <Route path="/categories" element={<AllCategoriesPage />} />
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
        <Route path="/listings/:slug" element={<BookingRoutePage />} />
        <Route path="/users/:userId" element={<PublicProfile />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <Toaster richColors expand position="top-center" />
    </div>
  );
}
