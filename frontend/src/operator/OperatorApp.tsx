import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthStore } from "@/lib/auth";
import { OperatorLayout } from "./OperatorLayout";
import { Dashboard } from "./pages/Dashboard";
import { AccessDeniedPage } from "./pages/AccessDeniedPage";
import { UsersList } from "./pages/UsersList";
import { UserDetail } from "./pages/UserDetail";
import { ListingsList } from "./pages/ListingsList";
import { ListingDetail } from "./pages/ListingDetail";
import { BookingsList } from "./pages/BookingsList";
import { BookingDetail } from "./pages/BookingDetail";
import { TransactionsPage } from "./pages/TransactionsPage";
import { BookingFinancePage } from "./pages/BookingFinancePage";
import { ExportsPage } from "./pages/ExportsPage";
import { OwnerEarningsPage } from "./pages/OwnerEarningsPage";
import { FinancePage } from "./pages/FinancePage";
import { DisputesListPage } from "./pages/DisputesListPage";
import { DisputeDetailPage } from "./pages/DisputeDetailPage";
import { PromotionsPage } from "./pages/PromotionsPage";
import { AuditLogPage } from "./pages/AuditLogPage";
import { Comms } from "./pages/Comms";
import { OperatorSessionProvider } from "./session";
import { SettingsPage } from "./pages/settings/SettingsPage";
import { PlatformRulesPage } from "./pages/settings/PlatformRulesPage";
import { FeesPage } from "./pages/settings/FeesPage";
import { FeatureFlagsPage } from "./pages/settings/FeatureFlagsPage";
import { MaintenanceModePage } from "./pages/settings/MaintenanceModePage";
import { HealthPage } from "./pages/health/HealthPage";
import { SystemHealthPage } from "./pages/health/SystemHealthPage";
import { JobsPage } from "./pages/health/JobsPage";

interface OperatorAppProps {
  darkMode: boolean;
  onToggleTheme: () => void;
}

export function OperatorApp({ darkMode, onToggleTheme }: OperatorAppProps) {
  const [isLoading, setIsLoading] = useState(true);
  const [isDenied, setIsDenied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [operator, setOperator] = useState<{
    id: number;
    email: string;
    name: string;
    is_staff: boolean;
    roles: string[];
    avatarUrl?: string | null;
  } | null>(null);

  const operatorRoleLabel = useMemo(() => {
    if (!operator?.roles?.length) return "Operator";
    const primary = operator.roles[0];
    return primary.replace(/_/g, " ");
  }, [operator]);

  const displayName = useMemo(() => {
    if (operator?.name?.trim()) return operator.name.trim();
    if (operator?.email?.trim()) return operator.email.trim();
    return "Operator";
  }, [operator]);

  useEffect(() => {
    let cancelled = false;
    const token = AuthStore.getAccess();
    if (!token) {
      setIsDenied(true);
      setIsLoading(false);
      return;
    }

    const loadOperator = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const resp = await fetch("/api/operator/me/", {
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/json",
          },
        });
        if (!resp.ok) {
          if (resp.status === 401 || resp.status === 403) {
            if (!cancelled) {
              setIsDenied(true);
            }
            return;
          }
          throw new Error(`Unexpected status ${resp.status}`);
        }
        const data = await resp.json();
        if (cancelled) return;
        if (!data?.is_staff) {
          setIsDenied(true);
          return;
        }
        setOperator({
          id: data.id,
          email: data.email,
          name: data.name,
          is_staff: data.is_staff,
          roles: Array.isArray(data.roles) ? data.roles : [],
          avatarUrl: data.avatar_url ?? AuthStore.getCurrentUser()?.avatar_url ?? null,
        });
      } catch (err) {
        if (!cancelled) {
          setError("Unable to load operator profile.");
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadOperator();

    return () => {
      cancelled = true;
    };
  }, []);

  const handleLogout = () => {
    AuthStore.clearTokens();
    window.location.href = "/";
  };

  if (isDenied) {
    return <AccessDeniedPage />;
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground">
        Loading operator console...
      </div>
    );
  }

  if (error || !operator) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground text-center px-6">
        <div>
          <p className="text-sm uppercase tracking-wide text-red-500">Error</p>
          <h1 className="text-2xl font-semibold mt-2 mb-2">Cannot load operator console</h1>
          <p className="max-w-lg">
            {error ?? "Unknown error loading operator profile."}
          </p>
        </div>
      </div>
    );
  }

  return (
    <OperatorSessionProvider
      value={{ id: operator.id, email: operator.email, name: displayName, roles: operator.roles || [] }}
    >
      <OperatorLayout
        darkMode={darkMode}
        onToggleTheme={onToggleTheme}
        operatorName={displayName}
        operatorRole={operatorRoleLabel}
        operatorEmail={operator.email}
        operatorAvatarUrl={operator.avatarUrl}
        onLogout={handleLogout}
      >
        <Routes>
          <Route index element={<Navigate to="dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="users" element={<UsersList />} />
          <Route path="users/:userId" element={<UserDetail />} />
          <Route path="listings" element={<ListingsList />} />
          <Route path="listings/:listingId" element={<ListingDetail />} />
          <Route path="bookings" element={<BookingsList />} />
          <Route path="bookings/:bookingId" element={<BookingDetail />} />
          <Route path="finance/bookings/:bookingId" element={<BookingFinancePage />} />
          <Route path="finance" element={<FinancePage />}>
            <Route index element={<Navigate to="general" replace />} />
            <Route path="general" element={<TransactionsPage />} />
            <Route path="transactions" element={<Navigate to="../general" replace />} />
            <Route path="exports" element={<ExportsPage />} />
            <Route path="owners" element={<OwnerEarningsPage />} />
            <Route path="owners/:ownerId" element={<OwnerEarningsPage />} />
          </Route>
          <Route path="disputes" element={<DisputesListPage />} />
          <Route path="disputes/:disputeId" element={<DisputeDetailPage />} />
          <Route path="promotions" element={<PromotionsPage />} />
          <Route path="audit" element={<AuditLogPage />} />
          <Route path="comms" element={<Comms />} />

          <Route path="settings" element={<SettingsPage />}>
            <Route index element={<Navigate to="platform-rules" replace />} />
            <Route path="platform-rules" element={<PlatformRulesPage />} />
            <Route path="fees" element={<FeesPage />} />
            <Route path="feature-flags" element={<FeatureFlagsPage />} />
            <Route path="maintenance" element={<MaintenanceModePage />} />
          </Route>

          <Route path="health" element={<HealthPage />}>
            <Route index element={<Navigate to="system" replace />} />
            <Route path="system" element={<SystemHealthPage />} />
            <Route path="jobs" element={<JobsPage />} />
          </Route>
        </Routes>
      </OperatorLayout>
    </OperatorSessionProvider>
  );
}

export default OperatorApp;
