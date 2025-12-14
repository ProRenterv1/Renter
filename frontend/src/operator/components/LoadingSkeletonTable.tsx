import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/components/ui/utils";

type LoadingSkeletonTableProps = {
  columns: number;
  rows?: number;
  className?: string;
};

export function LoadingSkeletonTable({
  columns,
  rows = 8,
  className,
}: LoadingSkeletonTableProps) {
  const safeColumns = Math.max(columns, 1);
  const safeRows = Math.max(rows, 1);

  return (
    <div className={cn("overflow-x-auto", className)}>
      <Table>
        <TableHeader>
          <TableRow>
            {Array.from({ length: safeColumns }).map((_, idx) => (
              <TableHead key={idx} className="p-4 text-sm">
                <Skeleton className="h-4 w-24" />
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {Array.from({ length: safeRows }).map((_, rowIdx) => (
            <TableRow key={rowIdx} className="border-b border-border">
              {Array.from({ length: safeColumns }).map((__, colIdx) => (
                <TableCell key={`${rowIdx}-${colIdx}`} className="p-4">
                  <Skeleton className="h-4 w-full max-w-[180px]" />
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
