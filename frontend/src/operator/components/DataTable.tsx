import { ReactNode, useMemo } from "react";
import {
  Pagination,
  PaginationContent,
  PaginationItem,
  PaginationLink,
  PaginationNext,
  PaginationPrevious,
} from "@/components/ui/pagination";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/components/ui/utils";
import { LoadingSkeletonTable } from "./LoadingSkeletonTable";

type Column<T> = {
  key: string;
  header: ReactNode;
  className?: string;
  cell: (item: T) => ReactNode;
};

type DataTableProps<T> = {
  columns: Column<T>[];
  data: T[];
  isLoading?: boolean;
  loadingRows?: number;
  emptyMessage?: string;
  onRowClick?: (item: T) => void;
  getRowId?: (item: T, index: number) => string | number;
  getRowClassName?: (item: T) => string | undefined;
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (page: number) => void;
  footerContent?: ReactNode;
};

export function DataTable<T>({
  columns,
  data,
  isLoading = false,
  loadingRows = 8,
  emptyMessage = "No results found.",
  onRowClick,
  getRowId,
  getRowClassName,
  page = 1,
  pageSize,
  total,
  onPageChange,
  footerContent,
}: DataTableProps<T>) {
  const pageSizeValue = pageSize ?? (data?.length || 10);
  const totalValue = total ?? data.length;
  const pageCount = useMemo(() => {
    if (!totalValue || !pageSizeValue) return 1;
    return Math.max(Math.ceil(totalValue / pageSizeValue), 1);
  }, [pageSizeValue, totalValue]);

  const showPagination = onPageChange && pageCount > 1;

  if (isLoading && data.length === 0) {
    return <LoadingSkeletonTable columns={columns.length} rows={loadingRows} />;
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <Table className="w-full">
          <TableHeader>
            <TableRow className="border-b border-border">
              {columns.map((column) => (
                <TableHead key={column.key} className={cn("text-left p-4 text-sm", column.className)}>
                  {column.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.map((item, index) => {
              const rowKey = getRowId ? getRowId(item, index) : index;
              return (
              <TableRow
                key={rowKey}
                className={cn(
                  "border-b border-border transition-colors",
                  onRowClick && "hover:bg-muted/50 cursor-pointer",
                  getRowClassName?.(item),
                )}
                onClick={onRowClick ? () => onRowClick(item) : undefined}
              >
                  {columns.map((column) => (
                    <TableCell key={column.key} className={cn("p-4 align-top", column.className)}>
                      {column.cell(item)}
                    </TableCell>
                  ))}
                </TableRow>
              );
            })}

            {!isLoading && data.length === 0 ? (
              <TableRow>
                <TableCell colSpan={columns.length} className="p-6 text-center text-muted-foreground">
                  {emptyMessage}
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        {footerContent}
        {showPagination ? (
          <Pagination className="justify-end sm:justify-center">
            <PaginationContent>
              <PaginationItem>
                <PaginationPrevious
                  href="#"
                  aria-disabled={page <= 1}
                  onClick={(e) => {
                    e.preventDefault();
                    if (page > 1) {
                      onPageChange(page - 1);
                    }
                  }}
                  className={page <= 1 ? "pointer-events-none opacity-50" : ""}
                />
              </PaginationItem>
              {Array.from({ length: pageCount }).map((_, idx) => {
                const pageNumber = idx + 1;
                if (pageCount > 7) {
                  // Render first, last, current +/-1, and ellipsis for large page counts
                  if (
                    pageNumber !== 1 &&
                    pageNumber !== pageCount &&
                    Math.abs(pageNumber - page) > 1
                  ) {
                    if (
                      (pageNumber === 2 && page > 3) ||
                      (pageNumber === pageCount - 1 && page < pageCount - 2)
                    ) {
                      return (
                        <PaginationItem key={`ellipsis-${pageNumber}`}>
                          <span className="text-muted-foreground px-2">...</span>
                        </PaginationItem>
                      );
                    }
                    return null;
                  }
                }
                return (
                  <PaginationItem key={pageNumber}>
                    <PaginationLink
                      href="#"
                      isActive={pageNumber === page}
                      onClick={(e) => {
                        e.preventDefault();
                        onPageChange(pageNumber);
                      }}
                    >
                      {pageNumber}
                    </PaginationLink>
                  </PaginationItem>
                );
              })}
              <PaginationItem>
                <PaginationNext
                  href="#"
                  aria-disabled={page >= pageCount}
                  onClick={(e) => {
                    e.preventDefault();
                    if (page < pageCount) {
                      onPageChange(page + 1);
                    }
                  }}
                  className={page >= pageCount ? "pointer-events-none opacity-50" : ""}
                />
              </PaginationItem>
            </PaginationContent>
          </Pagination>
        ) : null}
      </div>
    </div>
  );
}
