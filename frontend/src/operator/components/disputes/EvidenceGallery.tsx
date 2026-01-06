import { ImageOff } from "lucide-react";

import { AspectRatio } from "@/components/ui/aspect-ratio";
import { cn } from "@/components/ui/utils";
import { AvStatusChip } from "@/operator/components/StatusChips";
import type { OperatorDisputeEvidenceItem } from "@/operator/api";

type EvidenceGalleryProps = {
  title: string;
  description?: string;
  items: OperatorDisputeEvidenceItem[];
  emptyLabel?: string;
  className?: string;
};

export function EvidenceGallery({
  title,
  description,
  items,
  emptyLabel = "No evidence uploaded yet.",
  className,
}: EvidenceGalleryProps) {
  return (
    <div className={cn("space-y-3", className)}>
      <div>
        <div className="text-sm font-semibold text-foreground">{title}</div>
        {description ? (
          <div className="text-xs text-muted-foreground">{description}</div>
        ) : null}
      </div>

      {items.length ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((item) => {
            const label = item.label || item.filename || `Evidence ${item.id}`;
            const previewUrl = item.thumbnail_url || item.url || "";
            return (
              <div
                key={item.id}
                className="overflow-hidden rounded-lg border border-border bg-card"
              >
                <AspectRatio ratio={4 / 3}>
                  {previewUrl ? (
                    <img
                      src={previewUrl}
                      alt={label}
                      className="h-full w-full object-cover"
                      loading="lazy"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center bg-muted/40 text-muted-foreground">
                      <ImageOff className="h-6 w-6" />
                    </div>
                  )}
                </AspectRatio>
                <div className="flex items-center justify-between gap-2 p-2">
                  <div className="min-w-0">
                    <div className="truncate text-xs font-medium text-foreground">
                      {label}
                    </div>
                    {item.uploaded_at ? (
                      <div className="text-[0.65rem] text-muted-foreground">
                        {formatDateTime(item.uploaded_at)}
                      </div>
                    ) : null}
                  </div>
                  <AvStatusChip
                    status={item.av_status || "pending"}
                    className="shrink-0 px-2 py-0.5 text-[0.6rem]"
                  />
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-md border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
          {emptyLabel}
        </div>
      )}
    </div>
  );
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}
