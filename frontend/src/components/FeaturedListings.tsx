import { Sparkles, MapPin, Star } from "lucide-react";
import { motion } from "framer-motion";

import { listings } from "@/data/listings.mock";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/SectionHeading";
import { formatCurrency } from "@/lib/utils";

export function FeaturedListings() {
  const highlighted = listings.slice(0, 4);

  return (
    <section className="py-16" aria-labelledby="featured-heading">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <SectionHeading
            title="Top picks near you"
            description="Hand-selected rentals trending in the Edmonton community."
          />
          <button className="inline-flex items-center gap-2 text-sm font-semibold text-link hover:text-link-hover">
            <Sparkles className="h-4 w-4" aria-hidden />
            View marketplace
          </button>
        </div>

        <div
          className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4"
          role="list"
          aria-label="Featured listings"
        >
          {highlighted.map((listing, index) => (
            <motion.div
              key={listing.id}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ duration: 0.4, delay: index * 0.05 }}
            >
              <Card className="flex h-full flex-col overflow-hidden rounded-3xl border border-border/60 shadow-lg shadow-slate-900/5">
                <div className="relative">
                  <img
                    src={listing.imageUrl}
                    alt={listing.title}
                    className="h-48 w-full object-cover"
                    loading={index > 2 ? "lazy" : "eager"}
                  />
                  {listing.promoted && (
                    <Badge
                      className="absolute left-4 top-4 bg-[var(--promoted)] text-[var(--warning-text)]"
                      variant="outline"
                    >
                      Promoted
                    </Badge>
                  )}
                </div>
                <div className="flex flex-1 flex-col gap-3 p-5">
                  <div className="flex items-center justify-between text-sm text-muted-foreground">
                    <span>{listing.category}</span>
                    <span>{listing.availability}</span>
                  </div>
                  <h3 className="text-lg font-semibold">{listing.title}</h3>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <MapPin className="h-4 w-4" aria-hidden />
                    {listing.location}
                  </div>
                  <div className="mt-auto flex items-center justify-between">
                    <div>
                      <p className="text-sm text-muted-foreground">per day</p>
                      <p className="text-2xl font-semibold">{formatCurrency(listing.pricePerDay)}</p>
                    </div>
                    <div className="flex items-center gap-1 text-sm font-semibold">
                      <Star className="h-4 w-4 fill-[var(--warning-strong)] text-[var(--warning-strong)]" />
                      {listing.rating.toFixed(1)}
                      <span className="text-muted-foreground">({listing.reviews})</span>
                    </div>
                  </div>
                </div>
              </Card>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}
