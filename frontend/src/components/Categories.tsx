import { Drill, HardHat, Sprout, Hammer, PaintRoller, Leaf } from "lucide-react";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";

const categories = [
  {
    name: "Power Tools",
    count: "120+ items",
    icon: Drill,
    accent: "var(--info-bg)",
    iconColor: "var(--info-text)",
    popular: true,
  },
  {
    name: "Ladders & Scaffolding",
    count: "45+ items",
    icon: HardHat,
    accent: "var(--warning-bg)",
    iconColor: "var(--warning-text)",
  },
  {
    name: "Gardening & Lawn",
    count: "80+ items",
    icon: Sprout,
    accent: "var(--success-bg)",
    iconColor: "var(--success-text)",
  },
  {
    name: "Hand Tools",
    count: "200+ items",
    icon: Hammer,
    accent: "var(--muted)",
    iconColor: "var(--foreground)",
  },
  {
    name: "Painting & Finishing",
    count: "60+ items",
    icon: PaintRoller,
    accent: "var(--info-bg)",
    iconColor: "var(--info-text)",
  },
  {
    name: "Outdoor Equipment",
    count: "35+ items",
    icon: Leaf,
    accent: "var(--warning-bg)",
    iconColor: "var(--warning-text)",
  },
];

export function Categories() {
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
        <div className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {categories.map((category, index) => {
            const Icon = category.icon;
            return (
              <FadeIn key={category.name} delay={0.05 * index}>
                <Card className="relative flex items-center gap-4 rounded-3xl border border-border/70 p-5 transition hover:-translate-y-1 hover:shadow-lg">
                  {category.popular && (
                    <Badge
                      className="text-[11px]"
                      variant="outline"
                      position="top-right"
                    >
                      Popular
                    </Badge>
                  )}
                  <div
                    className="rounded-2xl p-3"
                    style={{ background: category.accent }}
                    aria-hidden
                  >
                    <Icon className="h-6 w-6" style={{ color: category.iconColor }} />
                  </div>
                  <div>
                    <p className="text-lg font-semibold">{category.name}</p>
                    <p className="text-sm text-muted-foreground">{category.count}</p>
                  </div>
         
                </Card>
              </FadeIn>
            );
          })}
        </div>
      </div>
    </section>
  );
}
