export type PermissionMode = "any" | "all";

export function normalizeRoles(roles?: string[] | null) {
  return (roles ?? [])
    .map((role) => role.trim().toLowerCase())
    .filter((role) => role.length > 0);
}

export function hasRequiredRoles(
  operatorRoles?: string[] | null,
  requiredRoles?: string[] | null,
  mode: PermissionMode = "any",
) {
  const required = normalizeRoles(requiredRoles);
  if (required.length === 0) return true;

  const roleSet = new Set(normalizeRoles(operatorRoles));
  if (roleSet.size === 0) return false;

  if (mode === "all") {
    return required.every((role) => roleSet.has(role));
  }

  return required.some((role) => roleSet.has(role));
}

export const OPERATOR_ADMIN_ROLE = "operator_admin";
export const OPERATOR_FINANCE_ROLE = "operator_finance";
