import type React from "react";
import { useEffect, useMemo, useState } from "react";
import type { DateRange } from "react-day-picker";
import { addDays, endOfDay, format, startOfDay } from "date-fns";
import { Check, ChevronsUpDown, CalendarRange } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button, buttonVariants } from "@/components/ui/button";
import { Calendar } from "@/components/ui/calendar";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/components/ui/utils";
import {
  operatorAPI,
  type OperatorListingListItem,
  type OperatorPromotionGrantPayload,
} from "@/operator/api";

const PLACEMENT_OPTIONS = [
  { value: "feed", label: "Feed" },
  { value: "search", label: "Search" },
  { value: "category", label: "Category spotlight" },
] as const;

type GrantPromotionModalProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: OperatorPromotionGrantPayload) => Promise<boolean>;
};

export function GrantPromotionModal({ open, onOpenChange, onSubmit }: GrantPromotionModalProps) {
  const [listingOpen, setListingOpen] = useState(false);
  const [listings, setListings] = useState<OperatorListingListItem[]>([]);
  const [listingsLoading, setListingsLoading] = useState(false);
  const [listingsError, setListingsError] = useState<string | null>(null);
  const [selectedListing, setSelectedListing] = useState<OperatorListingListItem | null>(null);
  const [placement, setPlacement] = useState(PLACEMENT_OPTIONS[0].value);
  const [comped, setComped] = useState(true);
  const [dateRange, setDateRange] = useState<DateRange | undefined>(undefined);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    const today = startOfDay(new Date());
    setSelectedListing(null);
    setListingOpen(false);
    setPlacement(PLACEMENT_OPTIONS[0].value);
    setComped(true);
    setDateRange({ from: today, to: addDays(today, 6) });
    setReason("");
    setErrors({});
  }, [open]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const loadListings = async () => {
      setListingsLoading(true);
      setListingsError(null);
      try {
        const data = await operatorAPI.listings();
        if (cancelled) return;
        const results = Array.isArray((data as any)?.results) ? (data as any).results : data;
        setListings(Array.isArray(results) ? results : []);
      } catch (err) {
        if (cancelled) return;
        console.error("Failed to load listings", err);
        setListings([]);
        setListingsError("Unable to load listings.");
      } finally {
        if (!cancelled) setListingsLoading(false);
      }
    };

    loadListings();

    return () => {
      cancelled = true;
    };
  }, [open]);

  const listingLabel = useMemo(() => {
    if (!selectedListing) return "Select a listing";
    const ownerLabel = selectedListing.owner?.email || selectedListing.owner?.name || "Unknown owner";
    return `${selectedListing.title} (#${selectedListing.id}) - ${ownerLabel}`;
  }, [selectedListing]);

  const handleSubmit = async () => {
    const validation = validateForm({ selectedListing, dateRange, reason, comped });
    setErrors(validation.errors);
    if (!validation.valid) return;

    const startsAt = startOfDay(validation.range.from!);
    const endsAt = endOfDay(validation.range.to!);

    const payload: OperatorPromotionGrantPayload = {
      listing_id: validation.listingId,
      starts_at: startsAt.toISOString(),
      ends_at: endsAt.toISOString(),
      reason: reason.trim(),
      placement,
      comped,
    };

    setSubmitting(true);
    const ok = await onSubmit(payload);
    setSubmitting(false);
    if (ok) {
      onOpenChange(false);
    }
  };

  const listingEmptyLabel = listingsLoading
    ? "Loading listings..."
    : "No listings found.";

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Grant promotion</DialogTitle>
          <DialogDescription>
            Schedule a comped promotion window and record the reason.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Listing</Label>
              <Popover open={listingOpen} onOpenChange={setListingOpen}>
                <PopoverTrigger asChild>
                  <button
                    type="button"
                    role="combobox"
                    aria-expanded={listingOpen}
                    className={cn(
                      buttonVariants({ variant: "outline" }),
                      "w-full justify-between text-left",
                    )}
                  >
                    <span className="truncate">{listingLabel}</span>
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </button>
                </PopoverTrigger>
                <PopoverContent className="z-[9999] p-0" align="start" sideOffset={4}>
                  <Command>
                    <CommandInput placeholder="Search listings..." />
                    <CommandList>
                      <CommandEmpty>{listingEmptyLabel}</CommandEmpty>
                      <CommandGroup>
                        {listings.map((listing) => {
                          const ownerLabel =
                            listing.owner?.email || listing.owner?.name || "Unknown owner";
                          return (
                            <CommandItem
                              key={listing.id}
                              value={`${listing.title} ${listing.id} ${ownerLabel}`}
                              onSelect={() => {
                                setSelectedListing(listing);
                                setListingOpen(false);
                                clearError("listing", setErrors);
                              }}
                            >
                              <Check
                                className={cn(
                                  "mr-2 h-4 w-4",
                                  selectedListing?.id === listing.id
                                    ? "opacity-100"
                                    : "opacity-0",
                                )}
                              />
                              <div className="flex flex-1 flex-col">
                                <span className="text-sm">{listing.title}</span>
                                <span className="text-xs text-muted-foreground">
                                  #{listing.id} • {ownerLabel}
                                </span>
                              </div>
                            </CommandItem>
                          );
                        })}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
              {errors.listing ? <ErrorText>{errors.listing}</ErrorText> : null}
              {listingsError ? <ErrorText>{listingsError}</ErrorText> : null}
            </div>

            <div className="space-y-2">
              <Label>Placement</Label>
              <Select value={placement} onValueChange={setPlacement}>
                <SelectTrigger>
                  <SelectValue placeholder="Select placement" />
                </SelectTrigger>
                <SelectContent>
                  {PLACEMENT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <CalendarRange className="h-4 w-4" />
              Promotion window
            </div>
            <div className="grid gap-4 md:grid-cols-[auto_1fr]">
              <Calendar
                mode="range"
                selected={dateRange}
                onSelect={(range) => {
                  setDateRange(range);
                  clearError("dateRange", setErrors);
                }}
                numberOfMonths={1}
              />
              <div className="space-y-3 text-sm text-muted-foreground">
                <div>
                  <Label className="text-xs uppercase text-muted-foreground">Start date</Label>
                  <div className="text-sm font-semibold text-foreground">
                    {dateRange?.from ? format(dateRange.from, "MMM d, yyyy") : "Select start date"}
                  </div>
                </div>
                <div>
                  <Label className="text-xs uppercase text-muted-foreground">End date</Label>
                  <div className="text-sm font-semibold text-foreground">
                    {dateRange?.to ? format(dateRange.to, "MMM d, yyyy") : "Select end date"}
                  </div>
                </div>
                {errors.dateRange ? <ErrorText>{errors.dateRange}</ErrorText> : null}
              </div>
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Comped promotion</Label>
              <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                <span className="text-sm">Comped</span>
                <Switch
                  checked={comped}
                  onCheckedChange={(value) => {
                    setComped(value);
                    clearError("comped", setErrors);
                  }}
                />
              </div>
              {errors.comped ? <ErrorText>{errors.comped}</ErrorText> : null}
            </div>
            <div className="space-y-2">
              <Label>Reason</Label>
              <Textarea
                rows={3}
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  clearError("reason", setErrors);
                }}
                placeholder="Required for audit trail"
              />
              {errors.reason ? <ErrorText>{errors.reason}</ErrorText> : null}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Granting..." : "Grant promotion"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function validateForm({
  selectedListing,
  dateRange,
  reason,
  comped,
}: {
  selectedListing: OperatorListingListItem | null;
  dateRange: DateRange | undefined;
  reason: string;
  comped: boolean;
}) {
  const errors: Record<string, string> = {};
  if (!selectedListing) errors.listing = "Select a listing.";
  if (!dateRange?.from || !dateRange?.to) {
    errors.dateRange = "Select a start and end date.";
  }
  if (dateRange?.from && dateRange?.to && dateRange.to < dateRange.from) {
    errors.dateRange = "End date must be on or after the start date.";
  }
  if (!reason.trim()) errors.reason = "Reason is required.";
  if (!comped) errors.comped = "Only comped promotions can be granted here.";

  return {
    valid: Object.keys(errors).length === 0,
    errors,
    listingId: selectedListing?.id ?? 0,
    range: dateRange ?? { from: new Date(), to: new Date() },
  };
}

function clearError(
  key: string,
  setErrors: React.Dispatch<React.SetStateAction<Record<string, string>>>,
) {
  setErrors((prev) => {
    if (!prev[key]) return prev;
    const next = { ...prev };
    delete next[key];
    return next;
  });
}

function ErrorText({ children }: { children: string }) {
  return <p className={cn("text-xs text-destructive", "mt-1")}>{children}</p>;
}
