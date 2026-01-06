import type React from "react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Label } from "../../components/ui/label";
import { Switch } from "../../components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../../components/ui/table";
import { LoadingSkeletonTable } from "../components/LoadingSkeletonTable";
import { EmptyState } from "../components/EmptyState";
import { CountdownChip, StageBadge } from "../components/StatusChips";
import {
  operatorAPI,
  type OperatorDashboardMetrics,
  type OperatorDisputeListItem,
  type OperatorDisputeListParams,
} from "../api";

const DEFAULT_STAGE_OPTIONS = [
  "intake",
  "awaiting_rebuttal",
  "under_review",
  "resolved",
];

export function DisputesListPage() {
  const navigate = useNavigate();
  const [disputes, setDisputes] = useState<OperatorDisputeListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<OperatorDashboardMetrics | null>(null);

  const [statusFilter, setStatusFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [flowFilter, setFlowFilter] = useState("all");
  const [stageFilter, setStageFilter] = useState("all");
  const [evidenceMissingOnly, setEvidenceMissingOnly] = useState(false);
  const [rebuttalOverdueOnly, setRebuttalOverdueOnly] = useState(false);
  const [safetyFlagOnly, setSafetyFlagOnly] = useState(false);
  const [ownerEmail, setOwnerEmail] = useState("");
  const [renterEmail, setRenterEmail] = useState("");
  const [bookingId, setBookingId] = useState("");

  const debouncedOwnerEmail = useDebouncedValue(ownerEmail.trim());
  const debouncedRenterEmail = useDebouncedValue(renterEmail.trim());
  const debouncedBookingId = useDebouncedValue(bookingId.trim());

  useEffect(() => {
    let cancelled = false;
    const loadMetrics = async () => {
      try {
        const data = await operatorAPI.dashboard();
        if (!cancelled) {
          setMetrics(data);
        }
      } catch {
        if (!cancelled) {
          setMetrics(null);
        }
      }
    };

    loadMetrics();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadDisputes = async () => {
      setLoading(true);
      setError(null);

      const params: OperatorDisputeListParams = {};
      if (statusFilter !== "all") params.status = statusFilter;
      if (categoryFilter !== "all") params.category = categoryFilter;
      if (flowFilter !== "all") params.flow = flowFilter;
      if (stageFilter !== "all") params.stage = stageFilter;
      if (evidenceMissingOnly) params.evidence_missing = true;
      if (rebuttalOverdueOnly) params.rebuttal_overdue = true;
      if (safetyFlagOnly) params.safety_flag = true;
      if (debouncedOwnerEmail) params.owner_email = debouncedOwnerEmail;
      if (debouncedRenterEmail) params.renter_email = debouncedRenterEmail;
      if (debouncedBookingId) params.booking_id = debouncedBookingId;

      try {
        const data = await operatorAPI.disputesList(params);
        if (cancelled) return;
        const results = Array.isArray((data as any)?.results) ? (data as any).results : data;
        setDisputes(Array.isArray(results) ? results : []);
      } catch (err) {
        console.error("Failed to load disputes", err);
        if (!cancelled) {
          setError("Unable to load disputes right now.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadDisputes();

    return () => {
      cancelled = true;
    };
  }, [
    statusFilter,
    categoryFilter,
    flowFilter,
    stageFilter,
    evidenceMissingOnly,
    rebuttalOverdueOnly,
    safetyFlagOnly,
    debouncedOwnerEmail,
    debouncedRenterEmail,
    debouncedBookingId,
  ]);

  const statusOptions = useMemo(
    () =>
      buildOptions(
        disputes.map((dispute) => dispute.status),
        statusFilter !== "all" ? [statusFilter] : [],
      ),
    [disputes, statusFilter],
  );

  const categoryOptions = useMemo(
    () =>
      buildOptions(
        disputes.map((dispute) => dispute.category),
        categoryFilter !== "all" ? [categoryFilter] : [],
      ),
    [disputes, categoryFilter],
  );

  const flowOptions = useMemo(
    () =>
      buildOptions(
        disputes.map((dispute) => dispute.flow),
        flowFilter !== "all" ? [flowFilter] : [],
      ),
    [disputes, flowFilter],
  );

  const stageOptions = useMemo(() => {
    const dynamicStages = buildOptions(
      disputes.map((dispute) => dispute.stage),
      stageFilter !== "all" ? [stageFilter] : [],
    );
    const base = DEFAULT_STAGE_OPTIONS;
    return [...new Set([...base, ...dynamicStages])];
  }, [disputes, stageFilter]);

  const openCount = metrics?.open_disputes_count;
  const rebuttalsDueSoon = metrics?.rebuttals_due_soon_count;

  const handleResetFilters = () => {
    setStatusFilter("all");
    setCategoryFilter("all");
    setFlowFilter("all");
    setStageFilter("all");
    setEvidenceMissingOnly(false);
    setRebuttalOverdueOnly(false);
    setSafetyFlagOnly(false);
    setOwnerEmail("");
    setRenterEmail("");
    setBookingId("");
  };

  const handleRowClick = (disputeId: number) => {
    navigate(`/operator/disputes/${disputeId}`);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="mb-2">Disputes</h1>
          <p className="text-muted-foreground">
            Review dispute intake, evidence, and rebuttal timelines.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {typeof openCount === "number" ? (
            <Badge
              variant="outline"
              className="rounded-full border-[var(--info-border)] bg-[var(--info-bg)] px-3 py-1 text-xs text-[var(--info-text)]"
            >
              {openCount} open
            </Badge>
          ) : null}
          {typeof rebuttalsDueSoon === "number" ? (
            <Badge
              variant="outline"
              className="rounded-full border-[var(--warning-border)] bg-[var(--warning-bg)] px-3 py-1 text-xs text-[var(--warning-text)]"
            >
              {rebuttalsDueSoon} rebuttals due soon
            </Badge>
          ) : null}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="status-filter">Status</Label>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger id="status-filter">
                  <SelectValue placeholder="All statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All statuses</SelectItem>
                  {statusOptions.map((status) => (
                    <SelectItem key={status} value={status}>
                      {formatLabel(status)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="category-filter">Category</Label>
              <Select value={categoryFilter} onValueChange={setCategoryFilter}>
                <SelectTrigger id="category-filter">
                  <SelectValue placeholder="All categories" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All categories</SelectItem>
                  {categoryOptions.map((category) => (
                    <SelectItem key={category} value={category}>
                      {formatLabel(category)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="flow-filter">Flow</Label>
              <Select value={flowFilter} onValueChange={setFlowFilter}>
                <SelectTrigger id="flow-filter">
                  <SelectValue placeholder="All flows" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All flows</SelectItem>
                  {flowOptions.map((flow) => (
                    <SelectItem key={flow} value={flow}>
                      {formatLabel(flow)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="stage-filter">Stage</Label>
              <Select value={stageFilter} onValueChange={setStageFilter}>
                <SelectTrigger id="stage-filter">
                  <SelectValue placeholder="All stages" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All stages</SelectItem>
                  {stageOptions.map((stage) => (
                    <SelectItem key={stage} value={stage}>
                      {formatLabel(stage)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="owner-email">Owner email</Label>
              <Input
                id="owner-email"
                type="text"
                placeholder="owner@email.com"
                value={ownerEmail}
                onChange={(e) => setOwnerEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="renter-email">Renter email</Label>
              <Input
                id="renter-email"
                type="text"
                placeholder="renter@email.com"
                value={renterEmail}
                onChange={(e) => setRenterEmail(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="booking-id">Booking ID</Label>
              <Input
                id="booking-id"
                type="text"
                placeholder="Booking #"
                value={bookingId}
                onChange={(e) => setBookingId(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-4">
            <ToggleRow
              id="evidence-missing"
              label="Evidence missing"
              checked={evidenceMissingOnly}
              onCheckedChange={setEvidenceMissingOnly}
            />
            <ToggleRow
              id="rebuttal-overdue"
              label="Rebuttal overdue"
              checked={rebuttalOverdueOnly}
              onCheckedChange={setRebuttalOverdueOnly}
            />
            <ToggleRow
              id="safety-flag"
              label="Safety flag"
              checked={safetyFlagOnly}
              onCheckedChange={setSafetyFlagOnly}
            />
            <Button variant="ghost" onClick={handleResetFilters} className="ml-auto">
              Reset filters
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          {loading ? (
            <LoadingSkeletonTable columns={12} rows={8} />
          ) : error ? (
            <div className="p-8 text-center text-muted-foreground">{error}</div>
          ) : disputes.length === 0 ? (
            <div className="p-8">
              <EmptyState
                title="No disputes match your filters"
                description="Try loosening filters or resetting them to see more results."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow className="border-b border-border bg-muted/40">
                    <TableHead className="whitespace-nowrap">Dispute ID</TableHead>
                    <TableHead className="whitespace-nowrap">Booking ID</TableHead>
                    <TableHead>Listing</TableHead>
                    <TableHead className="whitespace-nowrap">Opened By</TableHead>
                    <TableHead>Category</TableHead>
                    <TableHead>Flow</TableHead>
                    <TableHead>Stage</TableHead>
                    <TableHead className="whitespace-nowrap">Filed At</TableHead>
                    <TableHead className="whitespace-nowrap">Evidence Due</TableHead>
                    <TableHead className="whitespace-nowrap">Rebuttal Due</TableHead>
                    <TableHead>Flags</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {disputes.map((dispute) => (
                    <TableRow
                      key={dispute.id}
                      className="cursor-pointer border-b border-border transition-colors hover:bg-muted/40"
                      onClick={() => handleRowClick(dispute.id)}
                    >
                      <TableCell className="font-mono text-sm">#{dispute.id}</TableCell>
                      <TableCell className="font-mono text-sm">#{dispute.booking_id}</TableCell>
                      <TableCell>
                        <div className="font-medium">
                          {dispute.listing_title || "Listing"}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">
                        {formatOpenedBy(dispute)}
                      </TableCell>
                      <TableCell className="text-sm">{formatLabel(dispute.category)}</TableCell>
                      <TableCell className="text-sm">{formatLabel(dispute.flow)}</TableCell>
                      <TableCell>
                        <StageBadge stage={dispute.stage} />
                      </TableCell>
                      <TableCell className="text-sm">{formatDateTime(dispute.filed_at)}</TableCell>
                      <TableCell>
                        {dispute.evidence_due_at ? (
                          <CountdownChip dueAt={dispute.evidence_due_at} kind="evidence" />
                        ) : (
                          <span className="text-xs text-muted-foreground">--</span>
                        )}
                      </TableCell>
                      <TableCell>
                        {dispute.rebuttal_due_at ? (
                          <CountdownChip dueAt={dispute.rebuttal_due_at} kind="rebuttal" />
                        ) : (
                          <span className="text-xs text-muted-foreground">--</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-wrap items-center gap-2">
                          {renderFlags(dispute)}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={statusBadgeClass(dispute.status)}
                        >
                          {formatLabel(dispute.status)}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function ToggleRow({
  id,
  label,
  checked,
  onCheckedChange,
}: {
  id: string;
  label: string;
  checked: boolean;
  onCheckedChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}

function buildOptions(values: Array<string | null | undefined>, extraValues: string[] = []) {
  const normalized = values
    .map((value) => (value ?? "").trim())
    .filter(Boolean);
  const extras = extraValues.map((value) => value.trim()).filter(Boolean);
  return Array.from(new Set([...normalized, ...extras])).sort((a, b) => a.localeCompare(b));
}

function formatLabel(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function renderFlags(dispute: OperatorDisputeListItem) {
  const flags: React.ReactNode[] = [];
  const safety = dispute.safety_flag || dispute.flags?.includes("safety");
  const suspend = dispute.suspend_flag || dispute.flags?.includes("suspend");

  if (safety) {
    flags.push(
      <Badge
        key="safety"
        variant="outline"
        className="rounded-full border-[var(--warning-border)] bg-[var(--warning-bg)] px-2 py-0.5 text-[0.65rem] text-[var(--warning-text)]"
      >
        Safety
      </Badge>,
    );
  }

  if (suspend) {
    flags.push(
      <Badge
        key="suspend"
        variant="outline"
        className="rounded-full border-[var(--error-border)] bg-[var(--error-bg)] px-2 py-0.5 text-[0.65rem] text-[var(--error-text)]"
      >
        Suspend
      </Badge>,
    );
  }

  if (flags.length === 0) {
    flags.push(
      <span key="none" className="text-xs text-muted-foreground">
        --
      </span>,
    );
  }

  return flags;
}

function formatOpenedBy(dispute: OperatorDisputeListItem) {
  if (dispute.opened_by_label) return dispute.opened_by_label;
  if (dispute.opened_by === "owner") {
    return dispute.owner_email || "Owner";
  }
  if (dispute.opened_by === "renter") {
    return dispute.renter_email || "Renter";
  }
  return formatLabel(dispute.opened_by || "Unknown");
}

function statusBadgeClass(status: string) {
  const normalized = status.toLowerCase();
  if (normalized.includes("resolved") || normalized.includes("closed")) {
    return "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success-text)]";
  }
  if (
    normalized.includes("pending") ||
    normalized.includes("await") ||
    normalized.includes("review")
  ) {
    return "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning-text)]";
  }
  if (normalized.includes("denied") || normalized.includes("rejected")) {
    return "border-[var(--error-border)] bg-[var(--error-bg)] text-[var(--error-text)]";
  }
  return "border-border bg-muted/50 text-foreground";
}

function useDebouncedValue<T>(value: T, delay = 300) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedValue(value), delay);
    return () => window.clearTimeout(handle);
  }, [value, delay]);

  return debouncedValue;
}
