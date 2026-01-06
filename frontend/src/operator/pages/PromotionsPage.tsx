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
import { CancelPromotionModal } from "../components/promotions/modals/CancelPromotionModal";
import { GrantPromotionModal } from "../components/promotions/modals/GrantPromotionModal";
import { formatCadCents } from "../utils/money";
import {
  operatorAPI,
  type OperatorPromotionCancelPayload,
  type OperatorPromotionGrantPayload,
  type OperatorPromotionListItem,
  type OperatorPromotionListParams,
} from "../api";

const STATUS_OPTIONS = [
  { value: "all", label: "All" },
  { value: "active", label: "Active" },
  { value: "inactive", label: "Inactive" },
] as const;

export function PromotionsPage() {
  const [promotions, setPromotions] = useState<OperatorPromotionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState("all");
  const [ownerFilter, setOwnerFilter] = useState("");
  const [listingFilter, setListingFilter] = useState("");

  const [grantOpen, setGrantOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [selectedPromotion, setSelectedPromotion] = useState<OperatorPromotionListItem | null>(null);

  const debouncedOwner = useDebouncedValue(ownerFilter.trim());
  const debouncedListing = useDebouncedValue(listingFilter.trim());
  const ownerId = parseNumericQuery(debouncedOwner);
  const listingId = parseNumericQuery(debouncedListing);

  useEffect(() => {
    if (!cancelOpen) {
      setSelectedPromotion(null);
    }
  }, [cancelOpen]);

  const loadPromotions = useCallback(
    async (showLoading = true) => {
      if (showLoading) {
        setLoading(true);
        setPromotions([]);
      }
      setError(null);

      const params: OperatorPromotionListParams = {};
      if (statusFilter !== "all") {
        params.active = statusFilter === "active";
      }
      if (ownerId !== null) {
        params.owner_id = ownerId;
      }
      if (listingId !== null) {
        params.listing_id = listingId;
      }

      try {
        const data = await operatorAPI.promotions(params);
        const results = Array.isArray((data as any)?.results) ? (data as any).results : data;
        const items = Array.isArray(results) ? results : [];
        setPromotions(items);
      } catch (err) {
        console.error("Failed to load promotions", err);
        setError("Unable to load promotions right now.");
        setPromotions([]);
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [listingId, ownerId, statusFilter],
  );

  useEffect(() => {
    loadPromotions(true);
  }, [loadPromotions, debouncedOwner, debouncedListing]);

  const filteredPromotions = useMemo(() => {
    let items = promotions;
    if (debouncedOwner && ownerId === null) {
      const needle = debouncedOwner.toLowerCase();
      items = items.filter((promo) => {
        const ownerEmail = promo.owner_email?.toLowerCase() ?? "";
        const ownerName = promo.owner_name?.toLowerCase() ?? "";
        return ownerEmail.includes(needle) || ownerName.includes(needle);
      });
    }
    if (debouncedListing && listingId === null) {
      const needle = debouncedListing.toLowerCase();
      items = items.filter((promo) => {
        const title = promo.listing_title?.toLowerCase() ?? "";
        return title.includes(needle) || String(promo.listing).includes(needle);
      });
    }
    return items;
  }, [promotions, debouncedOwner, debouncedListing, ownerId, listingId]);

  const handleGrantPromotion = async (payload: OperatorPromotionGrantPayload) => {
    try {
      await operatorAPI.grantCompedPromotion(payload);
      toast.success("Promotion granted.");
      await loadPromotions(false);
      return true;
    } catch (err: any) {
      toast.error(extractErrorMessage(err, "Unable to grant promotion."));
      return false;
    }
  };

  const handleCancelPromotion = async (payload: OperatorPromotionCancelPayload) => {
    if (!selectedPromotion) return false;
    try {
      await operatorAPI.cancelPromotionEarly(selectedPromotion.id, payload);
      toast.success("Promotion canceled.");
      await loadPromotions(false);
      return true;
    } catch (err: any) {
      toast.error(extractErrorMessage(err, "Unable to cancel promotion."));
      return false;
    }
  };

  const columns = [
    {
      key: "listing",
      header: "Listing",
      cell: (promo: OperatorPromotionListItem) => (
        <div className="space-y-1">
          <div className="font-medium text-sm">
            {promo.listing_title || `Listing #${promo.listing}`}
          </div>
          <div className="text-xs text-muted-foreground">#{promo.listing}</div>
        </div>
      ),
    },
    {
      key: "owner",
      header: "Owner",
      cell: (promo: OperatorPromotionListItem) => (
        <div className="space-y-1 text-sm">
          <div>{promo.owner_name || promo.owner_email || "--"}</div>
          <div className="text-xs text-muted-foreground">{promo.owner_email || "--"}</div>
        </div>
      ),
    },
    {
      key: "placement",
      header: "Placement",
      cell: (promo: OperatorPromotionListItem) => (
        <span className="text-sm">{formatPlacement(promo.placement)}</span>
      ),
    },
    {
      key: "dates",
      header: "Start/End",
      cell: (promo: OperatorPromotionListItem) => (
        <div className="text-sm text-muted-foreground">
          {formatDateRange(promo.starts_at, promo.ends_at)}
        </div>
      ),
    },
    {
      key: "status",
      header: "Status",
      cell: (promo: OperatorPromotionListItem) => {
        const status = getPromotionStatus(promo);
        return (
          <Badge variant="outline" className={status.className}>
            {status.label}
          </Badge>
        );
      },
    },
    {
      key: "payment",
      header: "Paid/Comped",
      cell: (promo: OperatorPromotionListItem) => {
        const comped = isCompedPromotion(promo);
        return (
          <div className="space-y-1 text-sm">
            <Badge
              variant="outline"
              className={
                comped
                  ? "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning-text)]"
                  : "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success-text)]"
              }
            >
              {comped ? "Comped" : "Paid"}
            </Badge>
            {!comped ? (
              <div className="text-xs text-muted-foreground">
                {formatCadCents(promo.total_price_cents)}
              </div>
            ) : null}
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      cell: (promo: OperatorPromotionListItem) => (
        <Button
          variant="outline"
          size="sm"
          disabled={!promo.active}
          onClick={() => {
            setSelectedPromotion(promo);
            setCancelOpen(true);
          }}
        >
          Cancel Promotion
        </Button>
      ),
    },
  ];

  const tableEmptyMessage = error ?? "No promotions found.";

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="mb-2">Promotions</h1>
          <p className="text-muted-foreground">
            Grant and manage promoted listing placements.
          </p>
        </div>
        <Button onClick={() => setGrantOpen(true)}>Grant Promotion</Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label>Status</Label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger>
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                {STATUS_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>Owner</Label>
            <Input
              value={ownerFilter}
              onChange={(e) => setOwnerFilter(e.target.value)}
              placeholder="Owner email or id"
            />
          </div>
          <div className="space-y-2">
            <Label>Listing</Label>
            <Input
              value={listingFilter}
              onChange={(e) => setListingFilter(e.target.value)}
              placeholder="Listing title or id"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <DataTable
            columns={columns}
            data={filteredPromotions}
            isLoading={loading}
            emptyMessage={tableEmptyMessage}
            getRowId={(promo) => promo.id}
            footerContent={
              <div className="text-sm text-muted-foreground">
                Showing {filteredPromotions.length} promotion
                {filteredPromotions.length === 1 ? "" : "s"}
              </div>
            }
          />
        </CardContent>
      </Card>

      <GrantPromotionModal
        open={grantOpen}
        onOpenChange={setGrantOpen}
        onSubmit={handleGrantPromotion}
      />
      <CancelPromotionModal
        open={cancelOpen}
        promotion={selectedPromotion}
        onOpenChange={setCancelOpen}
        onSubmit={handleCancelPromotion}
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

function parseNumericQuery(value: string) {
  if (!value) return null;
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatPlacement(value?: string | null) {
  if (!value) return "Feed";
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
}

function formatDateRange(start?: string | null, end?: string | null) {
  const startLabel = formatDate(start);
  const endLabel = formatDate(end);
  if (!startLabel && !endLabel) return "--";
  if (startLabel && endLabel) return `${startLabel} - ${endLabel}`;
  return startLabel || endLabel || "--";
}

function formatDate(value?: string | null) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  try {
    return format(parsed, "MMM d, yyyy");
  } catch {
    return parsed.toLocaleDateString();
  }
}

function getPromotionStatus(promo: OperatorPromotionListItem) {
  const now = Date.now();
  const start = promo.starts_at ? new Date(promo.starts_at) : null;
  const end = promo.ends_at ? new Date(promo.ends_at) : null;

  if (promo.active) {
    if (start && start.getTime() > now) {
      return {
        label: "Scheduled",
        className:
          "border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--info-text)]",
      };
    }
    if (end && end.getTime() < now) {
      return {
        label: "Ended",
        className: "border-border bg-muted/40 text-muted-foreground",
      };
    }
    return {
      label: "Active",
      className:
        "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success-text)]",
    };
  }

  return {
    label: "Ended",
    className: "border-border bg-muted/40 text-muted-foreground",
  };
}

function isCompedPromotion(promo: OperatorPromotionListItem) {
  if (promo.stripe_session_id === "comped") return true;
  const total = promo.total_price_cents ?? 0;
  return total <= 0;
}

function extractErrorMessage(err: any, fallback: string) {
  return err?.data?.detail || fallback;
}
