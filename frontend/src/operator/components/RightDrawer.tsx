import { ReactNode } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

type RightDrawerProps = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function RightDrawer({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
}: RightDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader className="pb-2 px-2 sm:px-4">
          {title ? <SheetTitle>{title}</SheetTitle> : null}
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>
        <div className="flex h-full flex-col gap-4 overflow-y-auto pb-6 pt-2 px-2 sm:px-4">
          {children}
        </div>
        {footer ? <div className="mt-auto pt-2">{footer}</div> : null}
      </SheetContent>
    </Sheet>
  );
}
