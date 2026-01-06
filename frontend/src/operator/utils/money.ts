import { formatCurrency, parseMoney } from "@/lib/utils";

export function formatCadCents(
  cents?: number | null,
  options: Intl.NumberFormatOptions = {},
) {
  if (cents === null || cents === undefined || !Number.isFinite(cents)) {
    return "--";
  }
  return formatCurrency(cents / 100, "CAD", options);
}

export function formatCadDecimal(
  value?: number | string | null,
  options: Intl.NumberFormatOptions = {},
) {
  if (value === null || value === undefined || value === "") {
    return "--";
  }
  const amount = parseMoney(value);
  return formatCurrency(amount, "CAD", options);
}
