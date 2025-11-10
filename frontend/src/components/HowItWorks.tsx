import { ArrowRight, ClipboardCheck, Boxes, Handshake } from "lucide-react";

import { Card } from "@/components/ui/card";
import { FadeIn } from "@/components/FadeIn";
import { SectionHeading } from "@/components/SectionHeading";

const steps = [
  {
    title: "1. Browse verified tools",
    description: "Filter by neighborhood, availability, or tool type. Every item is vetted.",
    icon: Boxes,
  },
  {
    title: "2. Reserve & verify",
    description: "Secure your dates, add optional delivery, and verify identity in a minute.",
    icon: ClipboardCheck,
  },
  {
    title: "3. Pick up confidently",
    description: "Coordinate safe pickup with in-app messaging and coverage that follows you.",
    icon: Handshake,
  },
];

export function HowItWorks() {
  return (
    <section className="py-20" id="how-it-works" aria-labelledby="how-heading">
      <div className="mx-auto max-w-6xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col items-start gap-6 md:flex-row md:items-end md:justify-between">
          <SectionHeading
            title="How Renter works"
            description="From browse to pickup, everything is built to be intuitive on mobile and desktop."
          />
          <a
            href="#"
            className="inline-flex items-center gap-2 text-sm font-semibold text-link hover:text-link-hover"
          >
            Explore the guide <ArrowRight className="h-4 w-4" aria-hidden />
          </a>
        </div>
        <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
          {steps.map((step, index) => {
            const Icon = step.icon;
            return (
              <FadeIn key={step.title} delay={0.1 * index}>
                <Card className="h-full rounded-3xl border border-border/70 p-6">
                  <div className="flex items-center gap-4">
                    <span className="rounded-2xl bg-muted px-4 py-2 text-sm font-semibold text-muted-foreground">
                      Step {index + 1}
                    </span>
                    <Icon className="h-5 w-5 text-primary" aria-hidden />
                  </div>
                  <h3 className="mt-4 text-xl font-semibold">{step.title}</h3>
                  <p className="mt-3 text-base text-muted-foreground">{step.description}</p>
                </Card>
              </FadeIn>
            );
          })}
        </div>
      </div>
    </section>
  );
}
