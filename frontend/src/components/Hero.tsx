import { useMemo } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { CalendarDays, MapPin, Search } from "lucide-react";
import { toast } from "sonner";
import { motion } from "framer-motion";

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FadeIn } from "@/components/FadeIn";

const heroSchema = z.object({
  tool: z.string().min(2, "Describe what you need"),
  location: z.string().min(2, "Enter a neighbourhood"),
  date: z.string().min(1, "Pick a date"),
});

type HeroFormValues = z.infer<typeof heroSchema>;

const quickChips = ["Drills", "Pressure Washers", "Ladders", "Cement Mixers", "Generators"];

export function Hero() {
  const defaultDate = useMemo(() => new Date().toISOString().split("T")[0], []);

  const form = useForm<HeroFormValues>({
    resolver: zodResolver(heroSchema),
    defaultValues: {
      tool: "",
      location: "Edmonton, AB",
      date: defaultDate,
    },
  });

  const {
    formState: { errors },
  } = form;

  const onSubmit = (values: HeroFormValues) => {
    toast.success("Search ready!", {
      description: `Finding ${values.tool} near ${values.location} for ${new Date(
        values.date
      ).toLocaleDateString()}.`,
    });
  };

  return (
    <section
      className="relative overflow-hidden bg-background pb-10 pt-16 sm:pt-24"
      aria-labelledby="hero-heading"
    >
      <div className="absolute inset-x-0 top-10 -z-10 h-96 bg-gradient-to-b from-[#deebf5]/60 via-transparent to-transparent blur-2xl dark:from-[#112431]" />
      <div className="mx-auto flex max-w-5xl flex-col gap-12 px-4 text-center sm:px-6 lg:px-8">
        <FadeIn className="space-y-6">
          <p className="text-sm font-semibold uppercase tracking-[0.28em] text-muted-foreground">
            Edmonton · Local & insured
          </p>
          <h1
            id="hero-heading"
            className="text-4xl font-heading font-semibold leading-tight sm:text-5xl lg:text-[64px]"
          >
            Rent tools from neighbours —{" "}
            <span className="inline-block text-primary">insured &amp; verified</span>
          </h1>
          <p className="text-xl text-muted-foreground sm:text-2xl">
            Same-day pickups, backed by Renter Protect coverage.
          </p>
        </FadeIn>

        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="space-y-4 rounded-3xl border border-border/70 bg-card/90 p-4 shadow-xl shadow-slate-900/5 sm:p-6"
          aria-label="Search for tools"
        >
          <div className="flex flex-col gap-3 sm:flex-row">
            <label className="relative flex-1">
              <span className="sr-only">Search tools</span>
              <Search className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                {...form.register("tool")}
                placeholder="Search for drills, saws, lawn care..."
                className="h-14 rounded-2xl pl-12 text-base sm:text-lg"
                aria-invalid={Boolean(errors.tool)}
              />
              {errors.tool && (
                <p className="mt-2 text-left text-sm text-destructive">{errors.tool.message}</p>
              )}
            </label>
            <label className="relative flex-1 sm:max-w-xs">
              <span className="sr-only">Location</span>
              <MapPin className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                {...form.register("location")}
                className="h-14 rounded-2xl pl-12 text-base sm:text-lg"
                aria-invalid={Boolean(errors.location)}
              />
              {errors.location && (
                <p className="mt-2 text-left text-sm text-destructive">{errors.location.message}</p>
              )}
            </label>
          </div>
          <div className="flex flex-col items-stretch gap-3 sm:flex-row">
            <label className="relative flex-1 sm:max-w-[220px]">
              <span className="sr-only">Pickup date</span>
              <CalendarDays className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                {...form.register("date")}
                type="date"
                className="h-14 rounded-2xl pl-12 text-base"
                aria-invalid={Boolean(errors.date)}
              />
              {errors.date && (
                <p className="mt-2 text-left text-sm text-destructive">{errors.date.message}</p>
              )}
            </label>
            <Button className="h-14 rounded-2xl text-base font-semibold">Search tools</Button>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-3">
            {quickChips.map((chip) => (
              <motion.button
                type="button"
                key={chip}
                className="chip border-border bg-muted/80 hover:border-primary"
                onClick={() => form.setValue("tool", chip)}
                whileTap={{ scale: 0.96 }}
              >
                {chip}
              </motion.button>
            ))}
          </div>
        </form>

        <div className="grid gap-4 sm:grid-cols-3" role="list" aria-label="Community stats">
          {[
            { value: "1,200+", label: "Active items in Edmonton" },
            { value: "4.9/5", label: "Average owner rating" },
            { value: "$2M", label: "Coverage via Renter Protect" },
          ].map((stat, index) => (
            <FadeIn
              key={stat.label}
              delay={0.1 * (index + 1)}
              className="rounded-2xl border border-border/70 bg-card/80 px-5 py-6"
            >
              <p className="text-3xl font-semibold">{stat.value}</p>
              <p className="text-sm text-muted-foreground">{stat.label}</p>
            </FadeIn>
          ))}
        </div>
      </div>
    </section>
  );
}
