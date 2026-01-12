import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { SectionHeading } from "@/components/SectionHeading";
import { Card } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { platformAPI, type PlatformPricing } from "@/lib/api";
import { Badge } from "@/components/ui/badge";

const formatPercent = (value?: number | null) => {
  if (value === null || value === undefined) return "—";
  const normalized = Number(value);
  if (Number.isNaN(normalized)) return "—";
  const fixed = normalized % 1 === 0 ? normalized.toFixed(0) : normalized.toFixed(2);
  return `${fixed.replace(/\.00$/, "")}%`;
};

const formatMoney = (value: number | null, currency: string) => {
  if (value === null || Number.isNaN(value)) return "—";
  return new Intl.NumberFormat("en-CA", { style: "currency", currency }).format(value);
};

export default function PricingPage() {
  const [pricing, setPricing] = useState<PlatformPricing | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    platformAPI
      .pricing()
      .then((data) => {
        if (!active) return;
        setPricing(data);
        setError(null);
      })
      .catch(() => {
        if (!active) return;
        setError("Unable to load pricing right now. Please refresh to try again.");
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

  const currency = pricing?.currency ?? "CAD";
  const exampleSubtotal = 150; // 3 days at $50/day
  const renterFeeAmount =
    pricing && typeof pricing.renter_fee_rate === "number"
      ? (pricing.renter_fee_rate / 100) * exampleSubtotal
      : null;
  const ownerFeeAmount =
    pricing && typeof pricing.owner_fee_rate === "number"
      ? (pricing.owner_fee_rate / 100) * exampleSubtotal
      : null;
  const ownerPayout =
    pricing && ownerFeeAmount !== null ? exampleSubtotal - ownerFeeAmount : null;
  const instantPayoutCost =
    pricing && ownerPayout !== null
      ? (pricing.instant_payout_fee_rate / 100) * ownerPayout
      : null;
  const totalCharge =
    pricing && renterFeeAmount !== null ? exampleSubtotal + renterFeeAmount : null;

  const feeCards = [
    {
      title: "Renter service fee",
      rate: pricing?.renter_fee_rate,
      description:
        "Applied to the rental subtotal at checkout. Helps cover payment processing and customer support.",
    },
    {
      title: "Owner payout fee",
      rate: pricing?.owner_fee_rate,
      description:
        "Deducted from the subtotal before payouts. Keeps the platform running while you earn on your tools.",
    },
    {
      title: "Instant payout fee",
      rate: pricing?.instant_payout_fee_rate,
      description:
        "Optional charge only when you choose to cash out instantly instead of waiting for the normal payout window.",
    },
  ];

  return (
    <>
      <Header />
      <main className="bg-background">
        <section className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
          <SectionHeading
            title="Pricing and commissions"
            description="Live platform fees for renters and owners. These numbers are pulled directly from the backend configuration."
          />
          <p className="mt-4 text-sm text-muted-foreground">
            All fees are displayed in {currency}. If the platform changes, the rates shown here update
            automatically.
          </p>

          {error ? (
            <Alert variant="destructive" className="mt-6">
              <AlertTitle>Unable to load pricing</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          <div className="mt-8 grid gap-6 md:grid-cols-3">
            {feeCards.map((card) => (
              <Card key={card.title} className="p-6">
                <div className="flex items-center justify-between gap-2">
                  <h3 className="text-lg font-semibold">{card.title}</h3>
                  {loading ? (
                    <Badge variant="secondary">Loading...</Badge>
                  ) : (
                    <Badge variant="outline">{formatPercent(card.rate)}</Badge>
                  )}
                </div>
                <p className="mt-3 text-sm text-muted-foreground">{card.description}</p>
              </Card>
            ))}
          </div>

          <Card className="mt-8 p-6">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="text-lg font-semibold">Example rental</h3>
                <p className="text-sm text-muted-foreground">
                  3-day rental at $50/day. Damage deposits are separate and fully refunded when the tool
                  is returned in good shape.
                </p>
              </div>
              <Badge variant="secondary">Live rates</Badge>
            </div>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Rental subtotal</span>
                  <span className="font-semibold">
                    {formatMoney(exampleSubtotal, currency)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Renter service fee</span>
                  <span className="font-semibold">
                    {formatMoney(renterFeeAmount, currency)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Total charge to renter</span>
                  <span className="font-semibold">
                    {formatMoney(totalCharge, currency)}
                  </span>
                </div>
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Owner payout after fee</span>
                  <span className="font-semibold">
                    {formatMoney(ownerPayout, currency)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Owner fee withheld</span>
                  <span className="font-semibold">
                    {formatMoney(ownerFeeAmount, currency)}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Instant payout cost (optional)</span>
                  <span className="font-semibold">
                    {formatMoney(instantPayoutCost, currency)}
                  </span>
                </div>
              </div>
            </div>
            <p className="mt-4 text-xs text-muted-foreground">
              Numbers above are examples using the live platform rates. Actual totals depend on rental
              length, deposits, and any promotions applied to a listing.
            </p>
          </Card>

          <p className="mt-6 text-sm text-muted-foreground">
            Questions about fees or payouts? Reach the team at{" "}
            <a
              className="text-foreground underline underline-offset-4"
              href="mailto:support@kitoro.com"
            >
              support@kitoro.com
            </a>
            .
          </p>
        </section>
      </main>
      <Footer />
    </>
  );
}
