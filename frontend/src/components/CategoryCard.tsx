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

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export type ListingCategory = {
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

type CategoryCardProps = {
  category: ListingCategory;
  highlight?: boolean;
  onClick?: (slug?: string) => void;
};

export function CategoryCard({ category, highlight = false, onClick }: CategoryCardProps) {
  const Icon = getIconComponent(category.icon);
  const accent = category.accent || FALLBACK_ACCENT;
  const iconColor = category.icon_color || FALLBACK_ICON_COLOR;

  const handleClick = () => {
    if (onClick) {
      onClick(category.slug);
    }
  };

  return (
    <button
      type="button"
      className="w-full text-left focus:outline-none"
      onClick={handleClick}
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
  );
}

export { getIconComponent };
