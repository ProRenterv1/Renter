import type React from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/components/ui/utils";

type BaseSkeletonProps = React.ComponentProps<typeof Skeleton>;

type SkeletonAvatarProps = BaseSkeletonProps & {
  size?: "sm" | "md" | "lg";
};

export function SkeletonLine({ className, ...props }: BaseSkeletonProps) {
  return <Skeleton className={cn("h-4 w-full rounded-full", className)} {...props} />;
}

export function SkeletonBlock({ className, ...props }: BaseSkeletonProps) {
  return <Skeleton className={cn("h-24 w-full rounded-lg", className)} {...props} />;
}

export function SkeletonCard({ className, ...props }: BaseSkeletonProps) {
  return (
    <Skeleton
      variant="muted"
      className={cn("h-32 w-full rounded-xl", className)}
      {...props}
    />
  );
}

export function SkeletonChip({ className, ...props }: BaseSkeletonProps) {
  return (
    <Skeleton
      variant="subtle"
      className={cn("h-6 w-24 rounded-full", className)}
      {...props}
    />
  );
}

export function SkeletonAvatar({
  size = "md",
  className,
  ...props
}: SkeletonAvatarProps) {
  const sizeClass =
    size === "sm" ? "h-8 w-8" : size === "lg" ? "h-16 w-16" : "h-12 w-12";

  return (
    <Skeleton
      className={cn("rounded-full", sizeClass, className)}
      {...props}
    />
  );
}
