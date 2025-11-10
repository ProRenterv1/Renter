import { ShieldCheck, Star } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { FadeIn } from "@/components/FadeIn";

export function CallToAction() {
  return (
    <section className="py-20" id="cta" aria-labelledby="cta-heading">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <FadeIn>
          <Card
            className="flex flex-col gap-10 rounded-[32px] border-0 bg-gradient-to-br from-primary to-[#43718a] px-6 py-10 text-primary-foreground sm:px-12 lg:flex-row"
          >
            <div className="flex-1 space-y-5">
              <p className="text-xs font-semibold uppercase tracking-[0.4em] text-primary-foreground/70">
                Renter Protect
              </p>
              <h2
                id="cta-heading"
                className="text-3xl font-heading font-semibold leading-tight sm:text-4xl"
              >
                Insurance designed for neighbour-to-neighbour rentals.
              </h2>
              <p className="text-lg text-primary-foreground/80">
                Every booking ships with coverage, responsive support, and fraud monitoring so you
                can rent out tools or borrow them with confidence.
              </p>
              <div className="flex flex-wrap gap-3">
                <Button size="lg" className="rounded-2xl bg-card text-foreground hover:bg-card/90">
                  List your tool
                </Button>
                <Button
                  size="lg"
                  variant="ghost"
                  className="rounded-2xl border border-primary-foreground/30 text-primary-foreground hover:bg-primary-foreground/10"
                >
                  View coverage
                </Button>
              </div>
            </div>

            <div className="w-full max-w-sm space-y-4 text-sm lg:w-80">
              <div className="rounded-3xl bg-primary-foreground/10 p-4">
                <div className="flex items-center gap-3">
                  <ShieldCheck className="h-6 w-6" />
                  <div>
                    <p className="text-lg font-semibold">Zero-deductible payouts</p>
                    <p className="text-sm text-primary-foreground/80">Instant damage tracking</p>
                  </div>
                </div>
                <ul className="mt-4 space-y-2 text-sm text-primary-foreground/80">
                  <li>• Coverage follows the tool, not the user</li>
                  <li>• 24/7 concierge for owners and renters</li>
                  <li>• Up to $2M liability protection</li>
                </ul>
              </div>
              <Card className="rounded-3xl border-0 bg-card/90 p-5 text-foreground">
                <div className="flex items-center gap-3">
                  {[...Array(5)].map((_, index) => (
                    <Star key={index} className="h-5 w-5 fill-[var(--warning-strong)] text-[var(--warning-strong)]" />
                  ))}
                </div>
                <p className="mt-3 text-lg font-semibold">“Renter paid for all damage within 48h.”</p>
                <p className="text-sm text-muted-foreground">
                  Kelsey · Ladder owner in Strathearn
                </p>
              </Card>
            </div>
          </Card>
        </FadeIn>
      </div>
    </section>
  );
}
