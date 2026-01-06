import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "./utils";

const skeletonVariants = cva(
  "relative overflow-hidden rounded-md bg-gradient-to-r from-[var(--skeleton-from)] via-[var(--skeleton-to)] to-[var(--skeleton-from)] bg-[length:200%_100%] animate-[skeleton-shimmer_1.6s_ease-in-out_infinite]",
  {
    variants: {
      variant: {
        default: "",
        muted:
          "from-[var(--muted)] via-[var(--skeleton-from)] to-[var(--muted)]",
        subtle:
          "from-[var(--subtle)] via-[var(--skeleton-from)] to-[var(--subtle)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

function Skeleton({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof skeletonVariants>) {
  return (
    <div
      data-slot="skeleton"
      className={cn(skeletonVariants({ variant }), className)}
      {...props}
    />
  );
}

export { Skeleton };
