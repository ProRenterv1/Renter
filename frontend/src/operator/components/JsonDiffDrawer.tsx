import type React from "react";
import { useMemo } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/components/ui/utils";

type JsonDiffDrawerProps = {
  trigger?: React.ReactNode;
  before: unknown;
  after: unknown;
  title?: string;
  description?: string;
  headerContent?: React.ReactNode;
  side?: "left" | "right" | "top" | "bottom";
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  className?: string;
};

type DiffRow = {
  before: string | null;
  after: string | null;
  type: "same" | "added" | "removed";
};

export function JsonDiffDrawer({
  trigger,
  before,
  after,
  title = "JSON diff",
  description,
  headerContent,
  side = "right",
  open,
  onOpenChange,
  className,
}: JsonDiffDrawerProps) {
  const diffRows = useMemo(() => buildDiffRows(before, after), [before, after]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {trigger ? <SheetTrigger asChild>{trigger}</SheetTrigger> : null}
      <SheetContent side={side} className={cn("w-full sm:max-w-4xl", className)}>
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description ? <SheetDescription>{description}</SheetDescription> : null}
        </SheetHeader>
        <Separator />
        <div className="flex h-full flex-col gap-4 px-4 pb-6">
          {headerContent ? <div>{headerContent}</div> : null}
          <div className="grid grid-cols-2 gap-3 text-xs font-semibold text-muted-foreground">
            <div>Before</div>
            <div>After</div>
          </div>
          <div className="overflow-hidden rounded-lg border border-border">
            <ScrollArea className="h-[60vh]">
              <div className="grid grid-cols-2 text-xs font-mono">
                {diffRows.map((row, index) => (
                  <div key={index} className="contents">
                    <div
                      className={cn(
                        "border-r border-border/60 px-3 py-1 whitespace-pre",
                        row.type === "removed" && "bg-[var(--error-bg)] text-[var(--error-text)]",
                        row.type === "same" && "text-foreground",
                        row.type === "added" && "text-transparent select-none",
                      )}
                    >
                      {row.before ?? ""}
                    </div>
                    <div
                      className={cn(
                        "px-3 py-1 whitespace-pre",
                        row.type === "added" && "bg-[var(--success-bg)] text-[var(--success-text)]",
                        row.type === "same" && "text-foreground",
                        row.type === "removed" && "text-transparent select-none",
                      )}
                    >
                      {row.after ?? ""}
                    </div>
                  </div>
                ))}
              </div>
            </ScrollArea>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function buildDiffRows(before: unknown, after: unknown): DiffRow[] {
  const beforeLines = safeStringify(before).split("\n");
  const afterLines = safeStringify(after).split("\n");

  const m = beforeLines.length;
  const n = afterLines.length;
  const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));

  for (let i = m - 1; i >= 0; i -= 1) {
    for (let j = n - 1; j >= 0; j -= 1) {
      if (beforeLines[i] === afterLines[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1;
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1]);
      }
    }
  }

  const rows: DiffRow[] = [];
  let i = 0;
  let j = 0;

  while (i < m && j < n) {
    if (beforeLines[i] === afterLines[j]) {
      rows.push({ before: beforeLines[i], after: afterLines[j], type: "same" });
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({ before: beforeLines[i], after: null, type: "removed" });
      i += 1;
    } else {
      rows.push({ before: null, after: afterLines[j], type: "added" });
      j += 1;
    }
  }

  while (i < m) {
    rows.push({ before: beforeLines[i], after: null, type: "removed" });
    i += 1;
  }

  while (j < n) {
    rows.push({ before: null, after: afterLines[j], type: "added" });
    j += 1;
  }

  return rows;
}

function safeStringify(value: unknown) {
  if (value === undefined) return "undefined";
  try {
    const result = JSON.stringify(value, null, 2);
    return result ?? String(value);
  } catch {
    return String(value);
  }
}
