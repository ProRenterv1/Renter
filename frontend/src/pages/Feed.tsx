import { useEffect, useState, type KeyboardEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { Search, SlidersHorizontal, X, MapPin } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { jsonFetch, type JsonError } from "@/lib/api";
import { AuthStore } from "@/lib/auth";
import { Slider } from "../components/ui/slider";

interface FeedPageProps {
  onNavigateToMessages?: () => void;
  onNavigateToProfile?: () => void;
  onLogout?: () => void;
}

type Listing = {
  id: number;
  slug: string;
  title: string;
  description: string;
  daily_price_cad: string | number;
  city: string;
  category_name: string | null;
  photos?: { id: number; url: string }[];
};

type ListingCategory = {
  id: number;
  name: string;
  slug: string;
  icon?: string | null;
  accent?: string | null;
  icon_color?: string | null;
};

const PRICE_SLIDER_MIN = 0;
const PRICE_SLIDER_MAX = 1000;

const clampPrice = (value: number) =>
  Math.min(Math.max(value, PRICE_SLIDER_MIN), PRICE_SLIDER_MAX);

const normalizePriceValues = (values: [number, number]): [number, number] => {
  const [rawMin, rawMax] = values;
  const clampedMin = clampPrice(rawMin);
  const clampedMax = clampPrice(rawMax);
  return clampedMin <= clampedMax ? [clampedMin, clampedMax] : [clampedMax, clampedMin];
};

export default function Feed({
  onNavigateToMessages,
  onNavigateToProfile,
  onLogout,
}: FeedPageProps) {
  const [searchParams, setSearchParams] = useSearchParams();

  const q = searchParams.get("q") || "";
  const category = searchParams.get("category") || "";
  const city = searchParams.get("city") || "";
  const priceMin = searchParams.get("price_min") || "";
  const priceMax = searchParams.get("price_max") || "";

  const parsePriceParam = (value: string, fallback: number) => {
    if (!value) return fallback;
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  };

  const priceParamsToValues = () =>
    normalizePriceValues([
      parsePriceParam(priceMin, PRICE_SLIDER_MIN),
      parsePriceParam(priceMax, PRICE_SLIDER_MAX),
    ]);

  const [searchText, setSearchText] = useState(q);
  const [cityText, setCityText] = useState(city);
  const [priceValues, setPriceValues] = useState<[number, number]>(priceParamsToValues());
  const [priceInputValues, setPriceInputValues] = useState<[string, string]>([
    priceMin || "",
    priceMax || "",
  ]);
  const [listings, setListings] = useState<Listing[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [availableCategories, setAvailableCategories] = useState<ListingCategory[]>([]);

  useEffect(() => {
    setSearchText(q);
  }, [q]);

  useEffect(() => {
    setCityText(city);
  }, [city]);

  useEffect(() => {
    setPriceValues(priceParamsToValues());
    setPriceInputValues([priceMin || "", priceMax || ""]);
  }, [priceMin, priceMax]);

  useEffect(() => {
    let isMounted = true;
    jsonFetch<ListingCategory[]>("/listings/categories/")
      .then((data) => {
        if (!isMounted) return;
        setAvailableCategories(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        if (!isMounted) return;
        console.error("Failed to load categories", err);
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const hasActiveFilters = Boolean(q.trim() || category || priceMin || priceMax);

  const updateSearchParams = (updates: Record<string, string | null | undefined>) => {
    const params = new URLSearchParams(searchParams.toString());
    Object.entries(updates).forEach(([key, value]) => {
      if (value === null || value === undefined) {
        params.delete(key);
        return;
      }
      const trimmed = value.trim();
      if (trimmed) {
        params.set(key, trimmed);
      } else {
        params.delete(key);
      }
    });
    setSearchParams(params);
  };

  const handleSearchInputChange = (value: string) => {
    setSearchText(value);
  };

  const applySearch = () => {
    const trimmed = searchText.trim();
    updateSearchParams({ q: trimmed || null });
  };

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applySearch();
    }
  };

  const handleCityInputChange = (value: string) => {
    setCityText(value);
  };

  const applyCity = () => {
    const trimmed = cityText.trim();
    updateSearchParams({ city: trimmed || null });
  };

  const handleCityKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      applyCity();
    }
  };

  const handleCategoryClick = (slug: string) => {
    updateSearchParams({ category: slug || null });
  };

  const formatPriceInputFromValue = (value: number, isMin: boolean) => {
    if (isMin && value <= PRICE_SLIDER_MIN) return "";
    if (!isMin && value >= PRICE_SLIDER_MAX) return "";
    return String(value);
  };

  const inputStringsToValues = () =>
    normalizePriceValues([
      priceInputValues[0] ? Number(priceInputValues[0]) : PRICE_SLIDER_MIN,
      priceInputValues[1] ? Number(priceInputValues[1]) : PRICE_SLIDER_MAX,
    ]);

  const commitPriceValues = (values: [number, number]) => {
    const normalized = normalizePriceValues(values);
    setPriceValues(normalized);
    setPriceInputValues([
      formatPriceInputFromValue(normalized[0], true),
      formatPriceInputFromValue(normalized[1], false),
    ]);
    updateSearchParams({
      price_min: normalized[0] > PRICE_SLIDER_MIN ? String(normalized[0]) : null,
      price_max: normalized[1] < PRICE_SLIDER_MAX ? String(normalized[1]) : null,
    });
  };

  const handlePriceSliderChange = (values: number[]) => {
    if (!Array.isArray(values) || values.length < 2) return;
    const normalized = normalizePriceValues([values[0], values[1]]);
    setPriceValues(normalized);
    setPriceInputValues([
      formatPriceInputFromValue(normalized[0], true),
      formatPriceInputFromValue(normalized[1], false),
    ]);
  };

  const handlePriceSliderCommit = (values: number[]) => {
    if (!Array.isArray(values) || values.length < 2) return;
    commitPriceValues([values[0], values[1]]);
  };

  const handlePriceInputChange = (index: 0 | 1, rawValue: string) => {
    const sanitized = rawValue.replace(/[^\d]/g, "");
    setPriceInputValues((prev) => {
      const next = [...prev] as [string, string];
      next[index] = sanitized;
      return next;
    });
    const fallback = index === 0 ? PRICE_SLIDER_MIN : PRICE_SLIDER_MAX;
    const numeric = sanitized ? clampPrice(Number(sanitized)) : fallback;
    setPriceValues((prev) => {
      const next = [...prev] as [number, number];
      next[index] = numeric;
      if (next[0] > next[1]) {
        if (index === 0) {
          next[1] = numeric;
        } else {
          next[0] = numeric;
        }
      }
      return next as [number, number];
    });
  };

  const handlePriceInputBlur = () => {
    commitPriceValues(inputStringsToValues());
  };

  const handlePriceInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault();
      commitPriceValues(inputStringsToValues());
    }
  };

  const clearFilters = () => {
    setSearchText("");
    setPriceValues([PRICE_SLIDER_MIN, PRICE_SLIDER_MAX]);
    setPriceInputValues(["", ""]);
    updateSearchParams({
      q: null,
      category: null,
      price_min: null,
      price_max: null,
    });
  };

  useEffect(() => {
    const controller = new AbortController();
    let isCancelled = false;

    const fetchListings = async () => {
      setLoading(true);
      setError(null);
      let attemptedAnonymousFallback = false;

      const buildParams = () => {
        const params = new URLSearchParams();
        if (q.trim()) params.set("q", q.trim());
        if (category.trim()) params.set("category", category.trim());
        if (city.trim()) params.set("city", city.trim());
        if (priceMin.trim()) params.set("price_min", priceMin.trim());
        if (priceMax.trim()) params.set("price_max", priceMax.trim());
        return params;
      };

      while (true) {
        try {
          const params = buildParams();
          const queryString = params.toString();
          const path = `/listings/${queryString ? `?${queryString}` : ""}`;
          const response = await jsonFetch<Listing[] | { results?: Listing[] }>(path, {
            method: "GET",
            signal: controller.signal,
          });
          const items = Array.isArray(response)
            ? response
            : Array.isArray(response?.results)
              ? response.results
              : [];
          if (!isCancelled) {
            setListings(items);
          }
          break;
        } catch (err) {
          if ((err as DOMException)?.name === "AbortError") {
            if (!isCancelled) {
              setLoading(false);
            }
            return;
          }

          const status =
            typeof (err as JsonError)?.status === "number" ? (err as JsonError).status : null;
          const canRetryAnonymously =
            !attemptedAnonymousFallback && status && (status === 401 || status === 403);

          if (canRetryAnonymously) {
            attemptedAnonymousFallback = true;
            AuthStore.clearTokens();
            continue;
          }

          console.error("Failed to load listings", err);
          if (!isCancelled) {
            setError("Unable to load listings right now. Please try again.");
            setListings([]);
          }
          break;
        }
      }

      if (!isCancelled) {
        setLoading(false);
      }
    };

    fetchListings();

    return () => {
      isCancelled = true;
      controller.abort();
    };
  }, [q, category, city, priceMin, priceMax]);

  const formatPrice = (price: Listing["daily_price_cad"]) => {
    if (typeof price === "number") {
      return `$${price.toLocaleString("en-US")}/day`;
    }
    if (!price) {
      return "Contact for price";
    }
    const trimmed = price.trim();
    return trimmed.includes("/day") ? trimmed : `${trimmed}/day`;
  };

  const showingCount = listings.length;
  const isEmptyState = !loading && showingCount === 0;

  return (
    <div className="min-h-screen bg-background text-foreground">
  

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Search and Filters Section */}
        <div className="mb-8">
          {/* Search Bar */}
          <div className="mb-4 flex flex-col gap-3 md:flex-row">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Search for spaces, equipment, venues..."
                value={searchText}
                onChange={(e) => handleSearchInputChange(e.target.value)}
                onKeyDown={handleSearchKeyDown}
                className="pl-12 pr-4 h-14 rounded-3xl border-border bg-card"
                style={{
                  boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
                }}
              />
            </div>
            <div className="relative md:w-64">
              <MapPin className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-muted-foreground" />
              <Input
                type="text"
                placeholder="Select city"
                value={cityText}
                onChange={(e) => handleCityInputChange(e.target.value)}
                onKeyDown={handleCityKeyDown}
                onBlur={applyCity}
                className="pl-12 pr-4 h-14 rounded-3xl border-border bg-card"
                style={{
                  boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
                }}
              />
            </div>
          </div>

          {/* Filters Bar */}
          <div className="flex items-center gap-3 flex-wrap">
            <Button
              variant={showFilters ? "default" : "outline"}
              onClick={() => setShowFilters(!showFilters)}
              className="rounded-full gap-2"
            >
              <SlidersHorizontal className="w-4 h-4" />
              Filters
            </Button>

            <Button
              key="all"
              variant={category === "" ? "default" : "outline"}
              onClick={() => handleCategoryClick("")}
              className="rounded-full capitalize"
            >
              All
            </Button>

            {availableCategories.map((filter) => (
              <Button
                key={filter.slug}
                variant={category === filter.slug ? "default" : "outline"}
                onClick={() => handleCategoryClick(filter.slug)}
                className="rounded-full capitalize"
              >
                {filter.name}
              </Button>
            ))}

            {hasActiveFilters && (
              <Button
                variant="ghost"
                onClick={clearFilters}
                className="rounded-full gap-2"
              >
                <X className="w-4 h-4" />
                Clear all
              </Button>
            )}
          </div>

          {/* Extended Filters Panel */}
          {showFilters && (
            <div
              className="mt-4 p-6 bg-card rounded-3xl border border-border"
              style={{
                boxShadow: "0px 4px 12px rgba(0, 0, 0, 0.05)",
              }}
            >
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div>
                  <label className="block mb-2 text-foreground">
                    Price Range
                  </label>
                  <div className="mb-4 grid grid-cols-2 gap-4">
                    <div>
                      <p className="mb-1 text-xs text-muted-foreground">Min ($)</p>
                      <Input
                        type="text"
                        inputMode="numeric"
                        placeholder="0"
                        value={priceInputValues[0]}
                        onChange={(e) => handlePriceInputChange(0, e.target.value)}
                        onBlur={handlePriceInputBlur}
                        onKeyDown={handlePriceInputKeyDown}
                        className="rounded-xl"
                      />
                    </div>
                    <div>
                      <p className="mb-1 text-xs text-muted-foreground">Max ($)</p>
                      <Input
                        type="text"
                        inputMode="numeric"
                        placeholder="No max"
                        value={priceInputValues[1]}
                        onChange={(e) => handlePriceInputChange(1, e.target.value)}
                        onBlur={handlePriceInputBlur}
                        onKeyDown={handlePriceInputKeyDown}
                        className="rounded-xl"
                      />
                    </div>
                  </div>
                  <Slider
                    value={priceValues}
                    onValueChange={handlePriceSliderChange}
                    onValueCommit={handlePriceSliderCommit}
                    min={PRICE_SLIDER_MIN}
                    max={PRICE_SLIDER_MAX}
                    step={10}
                    className="py-4"
                  />
                  <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                    <span>${PRICE_SLIDER_MIN}</span>
                    <span>${PRICE_SLIDER_MAX}+</span>
                  </div>
                </div>

                <div>
                  <label className="block mb-2 text-foreground">
                    Sort By
                  </label>
                  <Select defaultValue="popular">
                    <SelectTrigger className="rounded-xl">
                      <SelectValue placeholder="Sort by" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="popular">Most Popular</SelectItem>
                      <SelectItem value="newest">Newest First</SelectItem>
                      <SelectItem value="price-low">Price: Low to High</SelectItem>
                      <SelectItem value="price-high">Price: High to Low</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <label className="block mb-2 text-foreground">
                    Availability
                  </label>
                  <Select defaultValue="all">
                    <SelectTrigger className="rounded-xl">
                      <SelectValue placeholder="Availability" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">All Items</SelectItem>
                      <SelectItem value="today">Available Today</SelectItem>
                      <SelectItem value="week">Available This Week</SelectItem>
                      <SelectItem value="instant">Instant Booking</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </div>
          )}
        </div>

        {city && (
          <p className="mb-4 text-sm text-muted-foreground">
            City: {city}
          </p>
        )}

        {error && (
          <div className="mb-6 rounded-2xl border border-destructive/30 bg-destructive/10 px-4 py-3 text-destructive">
            {error}
          </div>
        )}

        {/* Results Count */}
        <div className="mb-6">
          <p className="text-muted-foreground">
            Showing {showingCount} results
          </p>
        </div>

        {loading && (
          <div className="py-10 text-center text-muted-foreground">
            Loading listings...
          </div>
        )}

        {/* Feed Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {listings.map((listing) => {
            const imageUrl = listing.photos?.[0]?.url;
            const categoryLabel = listing.category_name || "Uncategorized";
            return (
              <div
                key={listing.id}
                className="bg-card rounded-3xl overflow-hidden border border-border transition-all duration-300 hover:scale-[1.02] cursor-pointer"
                style={{
                  boxShadow:
                    "0px 51px 21px rgba(0, 0, 0, 0.01), 0px 29px 17px rgba(0, 0, 0, 0.03), 0px 13px 13px rgba(0, 0, 0, 0.05), 0px 3px 7px rgba(0, 0, 0, 0.06)",
                }}
              >
                {/* Image */}
                <div className="relative h-48 overflow-hidden bg-muted">
                  {imageUrl ? (
                    <img
                      src={imageUrl}
                      alt={listing.title}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                      No photo
                    </div>
                  )}
                </div>

                {/* Content */}
                <div className="p-5">
                  <div className="flex items-start justify-between mb-2">
                    <h3
                      className="text-[18px] text-foreground"
                      style={{ fontFamily: "Manrope" }}
                    >
                      {listing.title}
                    </h3>
                  </div>

                  <p className="text-muted-foreground mb-4 line-clamp-2">
                    {listing.description}
                  </p>

                  <div className="flex items-center justify-between">
                    <span className="text-primary">
                      {formatPrice(listing.daily_price_cad)}
                    </span>
                    <Badge variant="outline" className="rounded-full">
                      {categoryLabel}
                    </Badge>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Empty State */}
        {isEmptyState && (
          <div className="text-center py-16">
            <p className="text-muted-foreground mb-4">
              No items found matching your criteria
            </p>
            <Button onClick={clearFilters} variant="outline" className="rounded-full">
              Clear Filters
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
