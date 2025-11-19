import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(
  value: number,
  currency: string = "CAD",
  options: Intl.NumberFormatOptions = {},
) {
  const normalizedValue = Number.isFinite(value) ? value : 0;
  const normalizedCurrency = (currency || "CAD").toUpperCase();
  return new Intl.NumberFormat("en-CA", {
    style: "currency",
    currency: normalizedCurrency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    ...options,
  }).format(normalizedValue);
}

export function parseMoney(value: unknown): number {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const normalized = value.replace(/,/g, "").trim();
    if (!normalized) {
      return 0;
    }
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export function pluralize(value: number, unit: string) {
  return `${value} ${value === 1 ? unit : `${unit}s`}`;
}
