import { useEffect, useMemo, useState } from "react";
import {
  BadgePercent,
  Boxes,
  Camera,
  Drill,
  Hammer,
  HardHat,
  Leaf,
  Package,
  Paintbrush,
  PenTool,
  Tractor,
  Wrench,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";
import { jsonFetch } from "@/lib/api";

type ListingCategory = {
  id: number;
  name: string;
  slug: string;
  icon?: string | null;
  accent?: string | null;
  icon_color?: string | null;
};

const FALLBACK_ACCENT = "var(--info-bg)";
const FALLBACK_ICON_COLOR = "var(--info-text)";
const FALLBACK_ICON_NAME = "Package";
const MAX_DISPLAYED_CATEGORIES = 6;

const ICON_MAP: Record<string, LucideIcon> = {
  Drill,
  Hammer,
  HardHat,
  Leaf,
  Package,
  Wrench,
  Paintbrush,
  PenTool,
  Camera,
  Boxes,
  Tractor,
  BadgePercent,
};

const getIconComponent = (iconName?: string | null): LucideIcon => {
  if (iconName && ICON_MAP[iconName]) {
    return ICON_MAP[iconName];
  }
  return ICON_MAP[FALLBACK_ICON_NAME];
};

export function Categories() {
  const navigate = useNavigate();
  const [categories, setCategories] = useState<ListingCategory[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    setLoading(true);
    jsonFetch<ListingCategory[]>("/listings/categories/")
      .then((data) => {
        if (!active) return;
        setCategories(Array.isArray(data) ? data : []);
      })
      .catch((err) => {
        if (!active) return;
        console.error("Failed to load categories", err);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const displayedCategories = useMemo(
    () => categories.slice(0, MAX_DISPLAYED_CATEGORIES),
    [categories],
  );

  const handleCategoryClick = (slug: string | undefined) => {
    if (!slug) {
      navigate("/feed");
      return;
    }
    navigate(`/feed?category=${encodeURIComponent(slug)}`); // TODO: include selected city when available
  };

  return (
    <section className="py-5" id="categories" aria-labelledby="categories-heading">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-0">
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <SectionHeading
            title="Browse by category"
            description="Find exactly what you need for your next project."
          />
          <a
            href="#"
            className="text-sm font-semibold text-link hover:text-link-hover"
          >
            View all categories →
          </a>
        </div>
        {displayedCategories.length === 0 ? (
          <div className="mt-10 text-muted-foreground">
            {loading ? "Loading categories..." : "Categories are coming soon."}
          </div>
        ) : (
          <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {displayedCategories.map((category, index) => {
              const Icon = getIconComponent(category.icon);
              const accent = category.accent || FALLBACK_ACCENT;
              const iconColor = category.icon_color || FALLBACK_ICON_COLOR;
              const highlight = index === 0;
              return (
                <FadeIn key={category.id} delay={0.05 * index}>
                  <button
                    type="button"
                    className="w-full text-left focus:outline-none"
                    onClick={() => handleCategoryClick(category.slug)}
                  >
                    <Card className="flex h-full flex-col gap-0 overflow-hidden rounded-3xl border border-border/60 bg-card p-0 text-left shadow-sm transition hover:-translate-y-1 hover:shadow-lg cursor-pointer">
                      <div
                        className="flex flex-1 items-center justify-center border-b border-border/50 px-6 py-14"
                        style={{ background: accent }}
                        aria-hidden
                      >
                        <Icon className="h-14 w-14" style={{ color: iconColor }} />
                      </div>
                      <div className="flex items-start justify-between gap-4 bg-card px-6 py-5">
                        <div>
                          <p className="text-lg font-semibold">{category.name}</p>
                          <p className="text-sm text-muted-foreground">Explore listings</p>
                        </div>
                        {highlight && (
                          <Badge className="rounded-full border-none bg-[#E8C27A] px-3 py-1 text-xs font-semibold text-[#6E4A0C] shadow-sm">
                            Featured
                          </Badge>
                        )}
                      </div>
                    </Card>
                  </button>
                </FadeIn>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
