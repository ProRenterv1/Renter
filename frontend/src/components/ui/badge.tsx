import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide",
  {
    variants: {
      variant: {
        default: "border-transparent bg-muted text-muted-foreground",
        outline: "border-border text-foreground",
        warning:
          "border-[var(--warning-border)] bg-[var(--warning-bg)] text-[var(--warning-text)]",
        info: "border-[var(--info-border)] bg-[var(--info-bg)] text-[var(--info-text)]",
        success:
          "border-[var(--success-border)] bg-[var(--success-bg)] text-[var(--success-text)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
