import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CalendarRange, Download, Users } from "lucide-react";
import { ExportModal } from "../components/modals/ExportModal";
import { operatorAPI } from "../api";
import { toast } from "sonner";

export function ExportsPage() {
  const [platformOpen, setPlatformOpen] = useState(false);
  const [ownerOpen, setOwnerOpen] = useState(false);

  const triggerDownload = async (blobPromise: Promise<Blob>, filename: string) => {
    const blob = await blobPromise;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-1">Finance Exports</h1>
        <p className="text-muted-foreground">Download CSV snapshots for platform revenue and owner ledgers.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Platform Revenue</CardTitle>
              <CardDescription>Platform fees and promotion charges</CardDescription>
            </div>
            <CalendarRange className="w-5 h-5 text-muted-foreground" />
          </CardHeader>
          <CardContent className="flex justify-between items-end">
            <p className="text-sm text-muted-foreground max-w-xs">
              Export platform revenue ledger rows for a date range. Includes platform fees and promotion charges. Missing fees will include approximations.
            </p>
            <Button variant="outline" onClick={() => setPlatformOpen(true)}>
              <Download className="w-4 h-4 mr-2" />
              Export
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Owner Ledger</CardTitle>
              <CardDescription>Ledger for a specific owner</CardDescription>
            </div>
            <Users className="w-5 h-5 text-muted-foreground" />
          </CardHeader>
          <CardContent className="flex justify-between items-end">
            <p className="text-sm text-muted-foreground max-w-xs">
              Export all ledger entries for a given owner and date range. Useful for reconciliation.
            </p>
            <Button variant="outline" onClick={() => setOwnerOpen(true)}>
              <Download className="w-4 h-4 mr-2" />
              Export
            </Button>
          </CardContent>
        </Card>
      </div>

      <ExportModal
        open={platformOpen}
        title="Platform revenue export"
        onClose={() => setPlatformOpen(false)}
        onDownload={async ({ from, to }) => {
          await triggerDownload(
            operatorAPI.downloadPlatformRevenue({ from, to }),
            "platform-revenue.csv",
          );
          toast.success("Platform revenue export started");
        }}
      />

      <ExportModal
        open={ownerOpen}
        title="Owner ledger export"
        requireOwner
        onClose={() => setOwnerOpen(false)}
        onDownload={async ({ from, to, owner_id }) => {
          await triggerDownload(
            operatorAPI.downloadOwnerLedger({ from, to, owner_id }),
            "owner-ledger.csv",
          );
          toast.success("Owner ledger export started");
        }}
      />
    </div>
  );
}
