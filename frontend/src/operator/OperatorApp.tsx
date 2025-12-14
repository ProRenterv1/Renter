import { useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AuthStore } from "@/lib/auth";
import { OperatorLayout } from "./OperatorLayout";
import { Dashboard } from "./pages/Dashboard";
import { AccessDeniedPage } from "./pages/AccessDeniedPage";
import { UsersList } from "./pages/UsersList";
import { UserDetail } from "./pages/UserDetail";

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
    <OperatorLayout
      darkMode={darkMode}
      onToggleTheme={onToggleTheme}
      operatorName={operator.name}
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
        <Route path="listings" element={<div>Listings page coming soon...</div>} />
        <Route path="bookings" element={<div>Bookings page coming soon...</div>} />
        <Route path="finance" element={<div>Finance page coming soon...</div>} />
        <Route path="disputes" element={<div>Disputes page coming soon...</div>} />
        <Route path="promotions" element={<div>Promotions page coming soon...</div>} />
        <Route path="comms" element={<div>Communications page coming soon...</div>} />
        <Route path="settings" element={<div>Settings page coming soon...</div>} />
        <Route path="health" element={<div>System Health page coming soon...</div>} />
      </Routes>
    </OperatorLayout>
  );
}

export default OperatorApp;
