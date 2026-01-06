import type React from "react";

import { useOperatorRoles } from "@/operator/session";
import { hasRequiredRoles, type PermissionMode } from "@/operator/utils/permissions";

type PermissionGateProps = {
  roles?: string[];
  mode?: PermissionMode;
  fallback?: React.ReactNode;
  children: React.ReactNode;
};

export function PermissionGate({
  roles = [],
  mode = "any",
  fallback = null,
  children,
}: PermissionGateProps) {
  const operatorRoles = useOperatorRoles();
  const allowed = hasRequiredRoles(operatorRoles, roles, mode);

  if (!allowed) {
    return <>{fallback}</>;
  }

  return <>{children}</>;
}
