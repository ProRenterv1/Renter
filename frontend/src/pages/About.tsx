import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";
import { Card } from "@/components/ui/card";
import { CheckCircle2, MapPin, Shield, Users } from "lucide-react";

const pillars = [
  {
    icon: MapPin,
    title: "Built for Edmonton",
    description:
      "We focus on neighbourhood-level lending so pickups are quick, returns are easy, and the dollars stay in the community.",
  },
  {
    icon: Shield,
    title: "Protected by design",
    description:
      "Identity checks, dispute tooling, and clear policies help renters and owners feel confident before, during, and after a booking.",
  },
  {
    icon: Users,
    title: "Community powered",
    description:
      "Rentino is powered by the people who list their tools and the neighbours who keep them in use, not by warehouses.",
  },
  {
    icon: CheckCircle2,
    title: "Straightforward to use",
    description:
      "From browsing to pickup, every flow is built to be quick, mobile-friendly, and transparent about what happens next.",
  },
];

const commitments = [
  "Clear communication and reminders for every booking.",
  "Transparent pricing—no surprise platform fees mid-checkout.",
  "Fast payouts for owners so you can reinvest in your toolkit.",
  "Responsive support when something doesn't go as planned.",
];

export default function AboutPage() {
  return (
    <>
      <Header />
      <main className="bg-background">
        <section className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
          <SectionHeading
            title="About Rentino"
            description="We connect neighbours in Edmonton so the right tool is always nearby, protected, and easy to book."
          />
          <div className="mt-6 space-y-4 text-muted-foreground">
            <p>
              Renting the right tool should be simple. Rentino was created to make sure anyone can find
              reliable equipment minutes from home, while owners earn more from the tools they already
              trust. Every feature we ship is built to keep both sides safe, informed, and supported.
            </p>
            <p>
              We're continually improving safety features, payout speed, and onboarding so more people
              can tackle projects without expensive purchases or long drives to big box stores.
            </p>
          </div>
          <div className="mt-10 grid gap-6 sm:grid-cols-2">
            {pillars.map((item, index) => {
              const Icon = item.icon;
              return (
                <FadeIn key={item.title} delay={index * 0.05}>
                  <Card className="h-full p-6">
                    <div className="flex items-center gap-3">
                      <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-muted">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="text-lg font-semibold">{item.title}</h3>
                        <p className="text-sm text-muted-foreground">{item.description}</p>
                      </div>
                    </div>
                  </Card>
                </FadeIn>
              );
            })}
          </div>
          <FadeIn delay={0.2}>
            <Card className="mt-10 p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <h3 className="text-xl font-semibold">Our commitment to users</h3>
                  <p className="mt-2 text-muted-foreground">
                    Your projects and your tools matter. We hold ourselves accountable to the same
                    standards we expect from the community.
                  </p>
                </div>
                <div className="space-y-2">
                  {commitments.map((item) => (
                    <div
                      key={item}
                      className="flex items-start gap-3 text-sm text-muted-foreground"
                    >
                      <CheckCircle2 className="mt-0.5 h-5 w-5 text-[var(--primary)]" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
              <p className="mt-6 text-sm text-muted-foreground">
                Questions or feedback? Reach us anytime at{" "}
                <a
                  className="text-foreground underline underline-offset-4"
                  href="mailto:support@rentino.org"
                >
                  support@rentino.org
                </a>
                .
              </p>
            </Card>
          </FadeIn>
        </section>
      </main>
      <Footer />
    </>
  );
}
