import { Header } from "@/components/Header";
import { Footer } from "@/components/Footer";
import { SectionHeading } from "@/components/SectionHeading";
import { FadeIn } from "@/components/FadeIn";
import { Card } from "@/components/ui/card";
import { AlertTriangle, Camera, CheckCircle2, ClipboardCheck, Shield } from "lucide-react";

const renterTips = [
  {
    title: "Confirm the details",
    description:
      "Review the pickup time, address, and ID requirements before you leave. Message the owner in-app if anything is unclear.",
    icon: ClipboardCheck,
  },
  {
    title: "Inspect before leaving",
    description:
      "Walk through basic functionality with the owner. If something seems unsafe or damaged, pause the booking and contact support.",
    icon: Shield,
  },
  {
    title: "Document condition",
    description:
      "Take a few quick photos at pickup and return so everyone agrees on the tool's state.",
    icon: Camera,
  },
];

const ownerTips = [
  {
    title: "Prep the tool",
    description:
      "Test the item before handoff, top up fluids if needed, and gather any safety gear that should go with it.",
    icon: CheckCircle2,
  },
  {
    title: "Share the basics",
    description:
      "Explain how to start, stop, and store the tool. Note any quirks or must-do steps (e.g. chain tension, fuel type).",
    icon: ClipboardCheck,
  },
  {
    title: "Align on return expectations",
    description:
      "Confirm the return time, cleanliness expectations, and where the renter should meet you to drop the tool off.",
    icon: AlertTriangle,
  },
];

const reminders = [
  "Keep all messaging inside Rentino so our team can step in if needed.",
  "Meet in a well-lit, public location when possible.",
  "Require ID if you do not recognize the renter picking up the tool.",
  "Stop using equipment immediately if it becomes unsafe and let the owner know.",
];

export default function SafetyPage() {
  return (
    <>
      <Header />
      <main className="bg-background">
        <section className="mx-auto max-w-5xl px-4 py-12 sm:px-6 lg:px-8">
          <SectionHeading
            title="Safety tips"
            description="Practical steps renters and owners can follow to keep every handoff smooth and safe."
          />
          <div className="mt-8 grid gap-6 md:grid-cols-2">
            <Card className="p-6">
              <h3 className="text-lg font-semibold">For renters</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Arrive on time, ask questions, and take a minute to confirm the tool works before you
                leave.
              </p>
              <div className="mt-6 space-y-4">
                {renterTips.map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.title} className="flex gap-3">
                      <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="font-medium">{item.title}</p>
                        <p className="text-sm text-muted-foreground">{item.description}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
            <Card className="p-6">
              <h3 className="text-lg font-semibold">For owners</h3>
              <p className="mt-2 text-sm text-muted-foreground">
                Good prep and clear instructions reduce surprises and protect your gear.
              </p>
              <div className="mt-6 space-y-4">
                {ownerTips.map((item) => {
                  const Icon = item.icon;
                  return (
                    <div key={item.title} className="flex gap-3">
                      <div className="mt-1 flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                        <Icon className="h-5 w-5" />
                      </div>
                      <div>
                        <p className="font-medium">{item.title}</p>
                        <p className="text-sm text-muted-foreground">{item.description}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
          <FadeIn delay={0.1}>
            <Card className="mt-8 p-6">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-muted">
                    <Shield className="h-5 w-5" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold">Quick reminders</h3>
                    <p className="text-sm text-muted-foreground">
                      Simple steps that keep everyone safe and aligned.
                    </p>
                  </div>
                </div>
                <ul className="space-y-2 text-sm text-muted-foreground sm:max-w-xl">
                  {reminders.map((item) => (
                    <li key={item} className="flex items-start gap-2">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 text-[var(--primary)]" />
                      <span>{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <p className="mt-6 text-sm text-muted-foreground">
                Need help during a rental? Email{" "}
                <a
                  className="text-foreground underline underline-offset-4"
                  href="mailto:support@rentino.org"
                >
                  support@rentino.org
                </a>{" "}
                and include your booking ID so we can prioritize your request.
              </p>
            </Card>
          </FadeIn>
        </section>
      </main>
      <Footer />
    </>
  );
}
