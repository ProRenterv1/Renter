import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Switch } from "../../components/ui/switch";
import { Label } from "../../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { Skeleton } from "../../components/ui/skeleton";
import { Search, AlertCircle, ExternalLink } from "lucide-react";
import {
  operatorAPI,
  type OperatorListingListItem,
  type OperatorListingListParams,
} from "../api";
import { useIsOperatorAdmin } from "../session";
import { toast } from "sonner";

export function ListingsList() {
  const navigate = useNavigate();
  const isAdmin = useIsOperatorAdmin();
  const [searchTitle, setSearchTitle] = useState("");
  const [searchOwner, setSearchOwner] = useState("");
  const [cityFilter, setCityFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [activeOnly, setActiveOnly] = useState(false);
  const [needsReviewOnly, setNeedsReviewOnly] = useState(false);
  const [listings, setListings] = useState<OperatorListingListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchListings = async () => {
      setLoading(true);
      setError(null);
      const params: OperatorListingListParams = {};
      if (isAdmin) params.include_deleted = true;
      if (cityFilter !== "all") params.city = cityFilter;
      if (categoryFilter !== "all") params.category = categoryFilter;
      if (activeOnly) {
        params.is_active = true;
        params.include_deleted = false;
      }
      if (needsReviewOnly) params.needs_review = true;

      try {
        const data = await operatorAPI.listings(params);
        if (cancelled) return;
        const results = Array.isArray((data as any)?.results) ? (data as any).results : data;
        setListings(Array.isArray(results) ? results : []);
      } catch (err) {
        console.error("Failed to load listings", err);
        if (!cancelled) setError("Unable to load listings right now.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchListings();
    return () => {
      cancelled = true;
    };
  }, [cityFilter, categoryFilter, activeOnly, needsReviewOnly, isAdmin]);

  const cities = useMemo(() => {
    const uniqueCities = Array.from(new Set(listings.map((l) => l.city || ""))).filter(Boolean);
    return uniqueCities.sort();
  }, [listings]);

  const categories = useMemo(() => {
    const uniqueCategories = Array.from(
      new Set(listings.map((l) => l.category?.slug || l.category?.name || "")),
    ).filter(Boolean);
    return uniqueCategories.sort();
  }, [listings]);

  const filteredListings = useMemo(() => {
    return listings.filter((listing) => {
      if (searchTitle && !listing.title.toLowerCase().includes(searchTitle.toLowerCase())) {
        return false;
      }
      if (
        searchOwner &&
        !((listing.owner?.name || listing.owner?.email || "").toLowerCase().includes(searchOwner.toLowerCase()))
      ) {
        return false;
      }
      return true;
    });
  }, [listings, searchTitle, searchOwner]);

  const handleViewListing = (listingId: number) => {
    navigate(`/operator/listings/${listingId}`);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="mb-2">Listings</h1>
          <p className="text-muted-foreground">Manage and moderate tool listings on the platform</p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="search-title">Search Title</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="search-title"
                  type="text"
                  placeholder="Search listing titles..."
                  value={searchTitle}
                  onChange={(e) => setSearchTitle(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="search-owner">Search Owner</Label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <Input
                  id="search-owner"
                  type="text"
                  placeholder="Search owner name/email..."
                  value={searchOwner}
                  onChange={(e) => setSearchOwner(e.target.value)}
                  className="pl-10"
                />
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-2">
              <Label htmlFor="city-filter">City</Label>
              <Select value={cityFilter} onValueChange={setCityFilter}>
                <SelectTrigger id="city-filter">
                  <SelectValue placeholder="All cities" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Cities</SelectItem>
                  {cities.map((city) => (
                    <SelectItem key={city} value={city}>
                      {city}
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
                  <SelectItem value="all">All Categories</SelectItem>
                  {categories.map((category) => (
                    <SelectItem key={category} value={category}>
                      {category}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="flex flex-wrap gap-6">
            <div className="flex items-center gap-2 px-3 py-1 rounded border border-border bg-muted/40">
              <Switch
                id="active-only"
                checked={activeOnly}
                onCheckedChange={setActiveOnly}
                className="data-[state=unchecked]:bg-background data-[state=unchecked]:border data-[state=unchecked]:border-border"
              />
              <Label htmlFor="active-only">Active Only</Label>
            </div>
            <div className="flex items-center gap-2 px-3 py-1 rounded border border-border bg-muted/40">
              <Switch
                id="needs-review-only"
                checked={needsReviewOnly}
                onCheckedChange={setNeedsReviewOnly}
                className="data-[state=unchecked]:bg-background data-[state=unchecked]:border data-[state=unchecked]:border-border"
              />
              <Label htmlFor="needs-review-only">Needs Review</Label>
            </div>
          </div>

          <div className="pt-4 border-t border-border">
            <p className="text-sm text-muted-foreground">
              Showing {filteredListings.length} of {listings.length} listings
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b border-border">
                <tr>
                  <th className="text-left p-4 font-medium">Listing</th>
                  <th className="text-left p-4 font-medium">Owner</th>
                  <th className="text-left p-4 font-medium">City</th>
                  <th className="text-left p-4 font-medium">Category</th>
                  <th className="text-left p-4 font-medium">Price/Day</th>
                  <th className="text-left p-4 font-medium">Status</th>
                  <th className="text-left p-4 font-medium">Flags</th>
                  <th className="text-left p-4 font-medium">Created</th>
                  <th className="text-left p-4 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={9} className="p-6">
                      <div className="flex gap-3">
                        <Skeleton className="h-12 w-12 rounded" />
                        <Skeleton className="h-12 flex-1" />
                      </div>
                    </td>
                  </tr>
                ) : error ? (
                  <tr>
                    <td colSpan={9} className="p-8 text-center text-muted-foreground">
                      {error}
                    </td>
                  </tr>
                ) : filteredListings.length > 0 ? (
                  filteredListings.map((listing) => (
                    <tr
                      key={listing.id}
                      className="border-b border-border hover:bg-muted/50 transition-colors"
                    >
                      <td className="p-4">
                        <div className="flex items-center gap-3">
                          {listing.thumbnail_url ? (
                            <img
                              src={listing.thumbnail_url}
                              alt={listing.title}
                              className="w-12 h-12 rounded object-cover"
                            />
                          ) : (
                            <div className="w-12 h-12 rounded bg-muted" />
                          )}
                          <div className="flex-1 min-w-0">
                            <div className="font-medium truncate">{listing.title}</div>
                            <div className="text-sm text-muted-foreground">#{listing.id}</div>
                          </div>
                        </div>
                      </td>
                      <td className="p-4">
                        <button
                          onClick={() => {
                            if (!listing.owner?.id) {
                              toast.info("No owner id for this listing yet");
                              return;
                            }
                            navigate(`/operator/users/${listing.owner.id}`);
                          }}
                          className="text-primary hover:underline"
                        >
                          {listing.owner?.name || listing.owner?.email || "Owner"}
                        </button>
                      </td>
                      <td className="p-4">{listing.city || "—"}</td>
                      <td className="p-4">{listing.category?.name || listing.category?.slug || "—"}</td>
                      <td className="p-4">${listing.daily_price_cad}</td>
                      <td className="p-4">
                        <Badge
                          variant={
                            listing.is_deleted
                              ? "destructive"
                              : listing.is_active
                                ? "default"
                                : "secondary"
                          }
                        >
                          {listing.is_deleted
                            ? "Deleted"
                            : listing.is_active
                              ? "Active"
                              : "Inactive"}
                        </Badge>
                      </td>
                      <td className="p-4">
                        <div className="flex gap-2 flex-wrap">
                          {listing.needs_review && (
                            <Badge variant="outline" className="border-orange-500 text-orange-700">
                              <AlertCircle className="w-3 h-3 mr-1" />
                              Needs Review
                            </Badge>
                          )}
                        </div>
                      </td>
                      <td className="p-4 text-sm text-muted-foreground">
                        {listing.created_at ? format(new Date(listing.created_at), "PP") : "—"}
                      </td>
                      <td className="p-4">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleViewListing(listing.id)}
                          className="text-primary"
                        >
                          View <ExternalLink className="w-4 h-4 ml-2" />
                        </Button>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={9} className="p-8 text-center text-muted-foreground">
                      <div className="flex flex-col items-center gap-2">
                        <AlertCircle className="w-5 h-5" />
                        <p className="m-0">No listings match your filters.</p>
                      </div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
