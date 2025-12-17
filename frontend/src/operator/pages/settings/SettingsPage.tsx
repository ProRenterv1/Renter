import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Flag, Gavel, Percent, ShieldAlert } from "lucide-react";

function _activeSettingsTab(pathname: string) {
  const parts = pathname.split("/").filter(Boolean);
  // /operator/settings/<tab>
  const tab = parts[2] || "platform-rules";
  if (
    tab === "platform-rules" ||
    tab === "fees" ||
    tab === "feature-flags" ||
    tab === "maintenance"
  ) {
    return tab;
  }
  return "platform-rules";
}

export function SettingsPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeTab = _activeSettingsTab(location.pathname);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2">Settings</h1>
        <p className="text-muted-foreground m-0">
          Manage platform rules, fees, feature flags, and maintenance mode.
        </p>
      </div>

      <Tabs
        value={activeTab}
        onValueChange={(value) => navigate(`/operator/settings/${value}`)}
      >
        <div className="flex justify-center">
          <TabsList className="h-11 w-full max-w-2xl border border-border bg-muted/60 shadow-sm">
            <TabsTrigger value="platform-rules" className="px-5 py-2 text-base font-semibold">
              <Gavel className="w-4 h-4" />
              Platform Rules
            </TabsTrigger>
            <TabsTrigger value="fees" className="px-5 py-2 text-base font-semibold">
              <Percent className="w-4 h-4" />
              Fees
            </TabsTrigger>
            <TabsTrigger value="feature-flags" className="px-5 py-2 text-base font-semibold">
              <Flag className="w-4 h-4" />
              Feature Flags
            </TabsTrigger>
            <TabsTrigger value="maintenance" className="px-5 py-2 text-base font-semibold">
              <ShieldAlert className="w-4 h-4" />
              Maintenance
            </TabsTrigger>
          </TabsList>
        </div>
      </Tabs>

      <Outlet />
    </div>
  );
}

