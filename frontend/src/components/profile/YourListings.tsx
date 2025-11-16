import { useEffect, useState, useMemo } from "react";
import { PlusCircle, MapPin } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import { listingsAPI, type Listing, type JsonError } from "../../lib/api";
import { formatCurrency } from "../../lib/utils";

interface YourListingsProps {
  onAddListingClick?: () => void;
  onListingSelect?: (listing: Listing) => void;
  refreshToken?: number;
}

type StatusFilter = "all" | "active" | "rented" | "inactive";

function computeStatus(listing: Listing): "Active" | "Rented" | "Inactive" {
  if (!listing.is_active) {
    return "Inactive";
  }
  if (!listing.is_available) {
    return "Rented";
  }
  return "Active";
}

function isJsonError(error: unknown): error is JsonError {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    typeof (error as { status?: unknown }).status === "number"
  );
}

export function YourListings({ onAddListingClick, onListingSelect, refreshToken = 0 }: YourListingsProps) {
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  useEffect(() => {
    let active = true;
    setLoading(true);
    const loadListings = async () => {
      try {
        const data = await listingsAPI.mine();
        if (!active) return;
        setListings(data.results ?? []);
        setError(null);
      } catch (err) {
        if (!active) return;
        if (isJsonError(err) && err.status === 401) {
          setError("Please log in to see your listings.");
        } else {
          setError("Could not load your listings. Please try again.");
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadListings();
    return () => {
      active = false;
    };
  }, [refreshToken]);

  const filteredListings = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    return listings.filter((listing) => {
      const title = (listing.title || "").toLowerCase();
      const city = (listing.city || "").toLowerCase();
      const matchesQuery =
        !normalizedQuery || title.includes(normalizedQuery) || city.includes(normalizedQuery);
      const listingStatus = computeStatus(listing).toLowerCase() as StatusFilter;
      const matchesStatus = statusFilter === "all" || listingStatus === statusFilter;
      return matchesQuery && matchesStatus;
    });
  }, [listings, searchQuery, statusFilter]);

  const content = useMemo(() => {
    if (loading) {
      return <p className="text-sm text-muted-foreground">Loading your listings…</p>;
    }
    if (error) {
      return <p className="text-sm text-destructive">{error}</p>;
    }
    if (listings.length === 0) {
      return (
        <p className="text-sm text-muted-foreground">
          You have not created any listings yet.
        </p>
      );
    }
    if (filteredListings.length === 0) {
      return (
        <p className="text-sm text-muted-foreground">
          No listings match your search or filters.
        </p>
      );
    }
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredListings.map((listing) => {
          const priceNumber = Number(listing.daily_price_cad);
          const priceLabel = Number.isFinite(priceNumber)
            ? formatCurrency(priceNumber, "CAD")
            : `$${listing.daily_price_cad}`;
          const imageUrl =
            listing.photos[0]?.url ??
            "https://placehold.co/600x400?text=Listing";
          const rentalLabel = listing.is_available ? "Not rented" : "Rented";
          return (
            <div
              key={listing.id}
              role={onListingSelect ? "button" : undefined}
              tabIndex={onListingSelect ? 0 : undefined}
              className={`bg-card rounded-2xl overflow-hidden border border-border transition-all duration-300 hover:scale-[1.02] ${
                onListingSelect ? "cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)] focus-visible:ring-offset-2" : ""
              }`}
              style={{
                boxShadow:
                  "0px 51px 21px rgba(0, 0, 0, 0.01), 0px 29px 17px rgba(0, 0, 0, 0.03), 0px 13px 13px rgba(0, 0, 0, 0.05), 0px 3px 7px rgba(0, 0, 0, 0.06)",
              }}
              onClick={() => onListingSelect?.(listing)}
              onKeyDown={(event) => {
                if (!onListingSelect) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onListingSelect(listing);
                }
              }}
            >
              <div className="relative h-48 overflow-hidden bg-muted">
                {imageUrl ? (
                  <img src={imageUrl} alt={listing.title} className="w-full h-full object-cover" />
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                    No photo
                  </div>
                )}
              </div>
              <div className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-[18px] text-foreground font-semibold" style={{ fontFamily: "Manrope" }}>
                    {listing.title}
                  </p>
                  <p className="text-sm text-muted-foreground whitespace-nowrap font-medium">
                    {rentalLabel}
                  </p>
                </div>
                <p className="text-muted-foreground text-sm flex items-center gap-1">
                  <MapPin className="h-4 w-4" />
                  <span>{listing.city}</span>
                </p>
                <div className="mt-3 flex items-center justify-between text-sm">
                  <span className="text-primary text-base">
                    {priceLabel}
                    <span className="text-muted-foreground text-sm">/day</span>
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    );
  }, [loading, error, listings, filteredListings, onListingSelect]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Your Listings</h1>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>
            Manage your tool listings
          </p>
        </div>
        <Button
          onClick={() => onAddListingClick?.()}
          className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
          style={{ color: "var(--primary-foreground)" }}
        >
          <PlusCircle className="w-4 h-4 mr-2" />
          Add New Listing
        </Button>
      </div>

      <div className="flex flex-col gap-4 md:flex-row">
        <div className="flex-1">
          <label className="mb-2 block text-sm font-medium text-foreground">Search</label>
          <Input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search by title or city"
          />
        </div>
        <div className="md:w-64">
          <label className="mb-2 block text-sm font-medium text-foreground">Status</label>
          <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="All statuses" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All statuses</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="rented">Rented</SelectItem>
              <SelectItem value="inactive">Inactive</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {content}
    </div>
  );
}
