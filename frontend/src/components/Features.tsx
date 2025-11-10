import { ShieldCheck, Users, Clock3, MapPin } from "lucide-react";

import { Card } from "@/components/ui/card";
import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";

const features = [
  {
    title: "Fully insured rentals",
    description: "Every transaction is backed by Renter Protect for up to $2M in coverage.",
    icon: ShieldCheck,
    accent: "var(--success-bg)",
    iconColor: "var(--success-text)",
  },
  {
    title: "Verified neighbours",
    description: "Gov ID + address checks keep the marketplace accountable and safe.",
    icon: Users,
    accent: "var(--info-bg)",
    iconColor: "var(--info-text)",
  },
  {
    title: "Flexible pick-up windows",
    description: "Reserve tools in minutes and coordinate pickups that match your schedule.",
    icon: Clock3,
    accent: "var(--warning-bg)",
    iconColor: "var(--warning-text)",
  },
  {
    title: "Local to Edmonton",
    description: "Chat directly with owners based in your neighbourhood and avoid shipping.",
    icon: MapPin,
    accent: "var(--muted)",
    iconColor: "var(--foreground)",
  },
];

export function Features() {
  return (
    <section className="bg-subtle/60 py-20" id="features">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <SectionHeading
          title="Trust & safety built in"
          description="Modern protection, transparent owners, and an insurance layer designed for real-world rentals."
          align="center"
        />
        <div className="mt-12 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((feature, index) => {
            const Icon = feature.icon;
            return (
              <FadeIn key={feature.title} delay={0.1 * index}>
                <Card className="relative h-full rounded-3xl border border-border/70 p-6">
                  <div
                    className="absolute -top-4 left-6 rounded-2xl p-3 shadow-lg"
                    style={{ background: feature.accent }}
                    aria-hidden
                  >
                    <Icon className="h-6 w-6" style={{ color: feature.iconColor }} />
                  </div>
                  <h3 className="mt-6 text-xl font-semibold">{feature.title}</h3>
                  <p className="mt-3 text-sm text-muted-foreground">{feature.description}</p>
                </Card>
              </FadeIn>
            );
          })}
        </div>
      </div>
    </section>
  );
}
