import { type ComponentProps } from "react";
import { Shield } from "lucide-react";

import { Avatar } from "./ui/avatar";
import { cn } from "@/lib/utils";

type VerifiedAvatarProps = ComponentProps<typeof Avatar> & {
  isVerified?: boolean;
  badgeClassName?: string;
};

export function VerifiedAvatar({
  isVerified = false,
  badgeClassName,
  className,
  children,
  ...avatarProps
}: VerifiedAvatarProps) {
  return (
    <div className="relative inline-block">
      <Avatar {...avatarProps} className={className}>
        {children}
      </Avatar>
      {isVerified && (
        <span
          className={cn(
            "absolute -bottom-1 -right-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-[var(--primary)] text-[var(--primary-foreground)] shadow-sm ring-2 ring-background",
            badgeClassName,
          )}
        >
          <Shield className="h-3 w-3" />
        </span>
      )}
    </div>
  );
}
