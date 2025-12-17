import { Outlet, useLocation, useNavigate } from "react-router-dom";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Download, List, Users } from "lucide-react";

function _activeFinanceTab(pathname: string) {
  const parts = pathname.split("/").filter(Boolean);
  // /operator/finance/<tab>/...
  const tab = parts[2] || "general";
  if (tab === "exports" || tab === "owners") return tab;
  return "general";
}

export function FinancePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const activeTab = _activeFinanceTab(location.pathname);

  return (
    <div className="space-y-6">
      <Tabs
        value={activeTab}
        onValueChange={(value) => navigate(`/operator/finance/${value}`)}
      >
        <div className="flex justify-center">
          <TabsList className="h-11 w-full max-w-xl border border-border bg-muted/60 shadow-sm">
            <TabsTrigger value="general" className="px-5 py-2 text-base font-semibold">
              <List className="w-4 h-4" />
              General
            </TabsTrigger>
            <TabsTrigger value="exports" className="px-5 py-2 text-base font-semibold">
              <Download className="w-4 h-4" />
              Exports
            </TabsTrigger>
            <TabsTrigger value="owners" className="px-5 py-2 text-base font-semibold">
              <Users className="w-4 h-4" />
              Owners
            </TabsTrigger>
          </TabsList>
        </div>
      </Tabs>
      <Outlet />
    </div>
  );
}
