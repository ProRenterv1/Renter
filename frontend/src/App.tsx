import { Suspense, lazy, useEffect, useMemo, useState, type ReactNode } from "react";
import { Routes, Route, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { MaintenanceBanner } from "@/components/MaintenanceBanner";
import { Toaster } from "sonner";
import { AuthStore } from "@/lib/auth";
import { listingsAPI, maintenanceAPI, type Listing as ApiListing, type MaintenanceBanner as MaintenanceBannerType } from "@/lib/api";

const LandingPage = lazy(() => import("@/pages/LandingPage"));
const Feed = lazy(() => import("@/pages/Feed"));
const Booking = lazy(() => import("@/pages/Booking"));
const UserProfile = lazy(() => import("@/pages/UserProfile"));
const Messages = lazy(() => import("@/pages/Messages"));
const AllCategoriesPage = lazy(() => import("@/pages/AllCategories"));
const PublicProfile = lazy(() => import("@/pages/PublicProfile"));

const isOpsBuildEnv = import.meta.env.VITE_OPS_BUILD === "1";
const OperatorApp = isOpsBuildEnv ? lazy(() => import("@/operator/OperatorApp")) : null;

function FeedPage() {
  const navigate = useNavigate();

  const handleOpenBooking = (listing: ApiListing) => {
    navigate(`/listings/${listing.slug}`, { state: { listing } });
  };

  return (
    <>
      <Header />
      <main>
        <Suspense fallback={<SectionFallback message="Loading listings..." />}>
          <Feed onOpenBooking={handleOpenBooking} />
        </Suspense>
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
    <Suspense fallback={<SectionFallback message="Loading listing..." />}>
      <Booking
        listing={listing}
        onBack={() => navigate("/feed")}
        isLoading={loading}
        errorMessage={error ?? undefined}
      />
    </Suspense>
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

function PageLoader() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <p className="text-sm text-muted-foreground">Loading...</p>
    </div>
  );
}

function SectionFallback({ message }: { message: string }) {
  return (
    <div className="py-16 text-center text-muted-foreground">{message}</div>
  );
}

type AppProps = {
  opsBuild?: boolean;
};

export default function App({ opsBuild }: AppProps) {
  const isOpsBuild = useMemo(() => opsBuild ?? isOpsBuildEnv, [opsBuild]);
  const location = useLocation();
  const [darkMode, setDarkMode] = useState(false);
  const isOperatorRoute = location.pathname.startsWith("/operator");
  const [maintenance, setMaintenance] = useState<MaintenanceBannerType | null>(null);
  const [maintenanceFetched, setMaintenanceFetched] = useState(false);

  useEffect(() => {
    if (isOperatorRoute) return;
    let cancelled = false;
    const load = async () => {
      try {
        const data = await maintenanceAPI.banner();
        if (!cancelled) setMaintenance(data);
      } catch {
        if (!cancelled) setMaintenance(null);
      } finally {
        if (!cancelled) setMaintenanceFetched(true);
      }
    };
    void load();
    const id = window.setInterval(load, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [isOperatorRoute]);

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

  useEffect(() => {
    if (typeof document === "undefined") return;
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  if (!isOperatorRoute && (!maintenanceFetched || maintenance?.enabled)) {
    return (
      <div className="min-h-screen bg-background text-foreground">
        <MaintenanceBanner
          severity={(maintenance?.severity as MaintenanceBannerType["severity"]) || "info"}
          message={maintenance?.message || "We’re performing maintenance. Please check back soon."}
          showRetry
        />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Suspense fallback={<PageLoader />}>
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
          {isOpsBuild && OperatorApp ? (
            <Route
              path="/operator/*"
              element={
                <RequireAuth>
                  <Suspense fallback={<PageLoader />}>
                    <OperatorApp
                      darkMode={darkMode}
                      onToggleTheme={() => setDarkMode((v) => !v)}
                    />
                  </Suspense>
                </RequireAuth>
              }
            />
          ) : null}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
      <Toaster richColors expand position="top-center" />
    </div>
  );
}
