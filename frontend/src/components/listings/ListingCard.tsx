import { MapPin } from "lucide-react";
import type { Listing } from "@/lib/api";
import { cn } from "@/lib/utils";

const FALLBACK_IMAGE =
  "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=800&q=80";

export interface ListingCardProps {
  listing: Listing;
  onClick?: (listing: Listing) => void;
  className?: string;
}

const cardShadow =
  "0px 51px 21px rgba(0, 0, 0, 0.01), 0px 29px 17px rgba(0, 0, 0, 0.03), 0px 13px 13px rgba(0, 0, 0, 0.05), 0px 3px 7px rgba(0, 0, 0, 0.06)";

export function ListingCard({ listing, onClick, className }: ListingCardProps) {
  const priceNumber = Number(listing.daily_price_cad ?? "0");
  const hasValidPrice = Number.isFinite(priceNumber) && priceNumber > 0;
  const price = hasValidPrice ? `$${priceNumber}/day` : "On request";
  const primaryPhoto = listing.photos?.[0]?.url ?? FALLBACK_IMAGE;

  const handleClick = () => {
    onClick?.(listing);
  };

  return (
    <div
      className={cn(
        "bg-card rounded-2xl overflow-hidden border border-border transition-all duration-300 hover:scale-[1.02] cursor-pointer",
        className,
      )}
      style={{ boxShadow: cardShadow }}
      onClick={handleClick}
    >
      <div className="relative h-48 overflow-hidden bg-muted">
        <img
          src={primaryPhoto}
          alt={listing.title}
          className="h-full w-full object-cover"
        />
      </div>

      <div className="px-4 py-3">
        <div className="mb-1 flex items-start justify-between">
          <h3 className="text-[18px] text-foreground" style={{ fontFamily: "Manrope" }}>
            {listing.title}
          </h3>
        </div>

        <div className="flex items-center justify-between text-sm">
          <span className="text-base text-primary">{price}</span>
          <div className="flex items-center gap-1 text-muted-foreground">
            <MapPin className="h-4 w-4" />
            <span>{listing.city || "N/A"}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
