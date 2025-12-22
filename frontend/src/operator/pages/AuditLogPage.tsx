import { useCallback, useEffect, useMemo, useState } from "react";
import { format } from "date-fns";
import { toast } from "sonner";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Label } from "../../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { DataTable } from "../components/DataTable";
import { AuditJsonDiffDrawer } from "../components/audit/JsonDiffDrawer";
import {
  operatorAPI,
  type OperatorAuditEvent,
  type OperatorAuditLogParams,
} from "../api";

const ENTITY_OPTIONS = [
  { value: "all", label: "All entities" },
  { value: "user", label: "User" },
  { value: "listing", label: "Listing" },
  { value: "booking", label: "Booking" },
  { value: "dispute_case", label: "Dispute case" },
  { value: "dispute_message", label: "Dispute message" },
  { value: "dispute_evidence", label: "Dispute evidence" },
  { value: "operator_note", label: "Operator note" },
] as const;

export function AuditLogPage() {
  const [events, setEvents] = useState<OperatorAuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [operatorFilter, setOperatorFilter] = useState("");
  const [entityTypeFilter, setEntityTypeFilter] = useState("all");
  const [actionFilter, setActionFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<OperatorAuditEvent | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const debouncedOperator = useDebouncedValue(operatorFilter.trim());
  const debouncedAction = useDebouncedValue(actionFilter.trim());

  useEffect(() => {
    setPage(1);
  }, [debouncedOperator, debouncedAction, entityTypeFilter, dateFrom, dateTo]);

  const loadAuditLog = useCallback(async () => {
    setLoading(true);
    setError(null);

    const params: OperatorAuditLogParams = {
      page,
      page_size: pageSize,
    };

    if (entityTypeFilter !== "all") {
      params.entity_type = entityTypeFilter;
    }
    if (debouncedAction) {
      params.action = debouncedAction;
    }
    if (debouncedOperator) {
      const numericId = parseNumeric(debouncedOperator);
      if (numericId !== null) {
        params.actor_id = numericId;
      } else {
        params.actor = debouncedOperator;
      }
    }
    const createdAfter = toStartOfDayISO(dateFrom);
    const createdBefore = toEndOfDayISO(dateTo);
    if (createdAfter) params.created_at_after = createdAfter;
    if (createdBefore) params.created_at_before = createdBefore;

    try {
      const data = await operatorAPI.auditLog(params);
      const results = Array.isArray((data as any)?.results) ? (data as any).results : data;
      const items = Array.isArray(results) ? results : [];
      setEvents(items);
      setTotal(typeof (data as any)?.count === "number" ? (data as any).count : items.length);
    } catch (err) {
      console.error("Failed to load audit log", err);
      setEvents([]);
      setTotal(0);
      setError("Unable to load audit log.");
    } finally {
      setLoading(false);
    }
  }, [debouncedAction, debouncedOperator, entityTypeFilter, dateFrom, dateTo, page]);

  useEffect(() => {
    loadAuditLog();
  }, [loadAuditLog]);

  useEffect(() => {
    if (!drawerOpen || !selectedEvent) return;
    let cancelled = false;

    const needsDetail =
      selectedEvent.before_json === undefined &&
      selectedEvent.after_json === undefined;
    if (!needsDetail) return;

    const loadDetail = async () => {
      setDetailLoading(true);
      try {
        const detail = await operatorAPI.auditDetail(selectedEvent.id);
        if (cancelled) return;
        setSelectedEvent((prev) => (prev?.id === detail.id ? { ...prev, ...detail } : prev));
      } catch (err: any) {
        if (cancelled) return;
        toast.error(extractErrorMessage(err, "Unable to load audit detail."));
      } finally {
        if (!cancelled) setDetailLoading(false);
      }
    };

    loadDetail();

    return () => {
      cancelled = true;
    };
  }, [drawerOpen, selectedEvent?.id]);

  useEffect(() => {
    if (drawerOpen) return;
    setSelectedEvent(null);
    setDetailLoading(false);
  }, [drawerOpen]);

  const tableEmptyMessage = error ?? "No audit events found.";

  const columns = useMemo(
    () => [
      {
        key: "action",
        header: "Action",
        cell: (event: OperatorAuditEvent) => (
          <Badge variant="outline" className="text-xs font-mono">
            {event.action}
          </Badge>
        ),
      },
      {
        key: "entity",
        header: "Entity",
        cell: (event: OperatorAuditEvent) => (
          <div className="text-sm">{formatEntity(event.entity_type, event.entity_id)}</div>
        ),
      },
      {
        key: "reason",
        header: "Reason",
        cell: (event: OperatorAuditEvent) => {
          const preview = formatReasonPreview(event.reason);
          return (
            <span className="text-sm text-muted-foreground" title={event.reason}>
              {preview}
            </span>
          );
        },
      },
      {
        key: "timestamp",
        header: "Timestamp",
        cell: (event: OperatorAuditEvent) => (
          <span className="text-sm text-muted-foreground">
            {formatDateTime(event.created_at)}
          </span>
        ),
      },
    ],
    [],
  );

  const handleRowClick = (event: OperatorAuditEvent) => {
    setSelectedEvent(event);
    setDrawerOpen(true);
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="mb-2">Audit Log</h1>
          <p className="text-muted-foreground">
            Track operator actions across listings, bookings, disputes, and settings.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={() => {
            setOperatorFilter("");
            setEntityTypeFilter("all");
            setActionFilter("");
            setDateFrom("");
            setDateTo("");
          }}
        >
          Reset filters
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <div className="space-y-2">
            <Label>Operator</Label>
            <Input
              placeholder="Operator id or email"
              value={operatorFilter}
              onChange={(e) => setOperatorFilter(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label>Entity type</Label>
            <Select value={entityTypeFilter} onValueChange={setEntityTypeFilter}>
              <SelectTrigger>
                <SelectValue placeholder="All entities" />
              </SelectTrigger>
              <SelectContent>
                {ENTITY_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Action</Label>
            <Input
              placeholder="operator.*"
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value)}
            />
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label>From</Label>
              <Input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>To</Label>
              <Input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <DataTable
            columns={columns}
            data={events}
            isLoading={loading}
            emptyMessage={tableEmptyMessage}
            getRowId={(event) => event.id}
            onRowClick={handleRowClick}
            page={page}
            pageSize={pageSize}
            total={total}
            onPageChange={setPage}
            footerContent={
              <div className="text-sm text-muted-foreground">
                Showing {events.length} of {total} events
              </div>
            }
          />
        </CardContent>
      </Card>

      <AuditJsonDiffDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        event={selectedEvent}
        loading={detailLoading}
      />
    </div>
  );
}

function useDebouncedValue(value: string, delay = 300) {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const handle = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(handle);
  }, [value, delay]);

  return debounced;
}

function parseNumeric(value: string) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatEntity(entityType: string, entityId: string) {
  if (!entityType) return "--";
  const label = formatLabel(entityType);
  return entityId ? `${label} #${entityId}` : label;
}

function formatLabel(value: string) {
  if (!value) return "--";
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
}

function formatReasonPreview(value?: string | null) {
  if (!value) return "--";
  const trimmed = value.replace(/\s+/g, " ").trim();
  if (trimmed.length <= 80) return trimmed;
  return `${trimmed.slice(0, 77)}...`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  try {
    return format(parsed, "MMM d, yyyy p");
  } catch {
    return parsed.toLocaleString();
  }
}

function toStartOfDayISO(value: string) {
  if (!value) return null;
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function toEndOfDayISO(value: string) {
  if (!value) return null;
  const parsed = new Date(`${value}T23:59:59.999`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function extractErrorMessage(err: any, fallback: string) {
  return err?.data?.detail || fallback;
}
