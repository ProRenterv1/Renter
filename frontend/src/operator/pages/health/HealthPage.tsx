import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Activity, Wrench } from "lucide-react";

function _activeHealthTab(pathname: string) {
  const parts = pathname.split("/").filter(Boolean);
  // /operator/health/<tab>
  const tab = parts[2] || "system";
  if (tab === "system" || tab === "jobs") return tab;
  return "system";
}

export function HealthPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeTab = _activeHealthTab(location.pathname);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2">Health</h1>
        <p className="text-muted-foreground m-0">
          Deep checks for critical dependencies and background workers.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={(value) => navigate(`/operator/health/${value}`)}>
        <div className="flex justify-center">
          <TabsList className="h-11 w-full max-w-xl border border-border bg-muted/60 shadow-sm">
            <TabsTrigger value="system" className="px-5 py-2 text-base font-semibold">
              <Activity className="w-4 h-4" />
              System
            </TabsTrigger>
            <TabsTrigger value="jobs" className="px-5 py-2 text-base font-semibold">
              <Wrench className="w-4 h-4" />
              Jobs
            </TabsTrigger>
          </TabsList>
        </div>
      </Tabs>

      <Outlet />
    </div>
  );
}

