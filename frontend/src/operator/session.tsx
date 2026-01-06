import { createContext, ReactNode, useContext, useMemo } from "react";

export type OperatorSession = {
  id: number;
  email: string;
  name: string;
  roles: string[];
};

const OperatorSessionContext = createContext<OperatorSession | null>(null);

export function OperatorSessionProvider({
  value,
  children,
}: {
  value: OperatorSession;
  children: ReactNode;
}) {
  return (
    <OperatorSessionContext.Provider value={value}>
      {children}
    </OperatorSessionContext.Provider>
  );
}

export function useOperatorSession() {
  const session = useContext(OperatorSessionContext);
  if (!session) {
    throw new Error("useOperatorSession must be used within OperatorSessionProvider");
  }
  return session;
}

export function useOperatorRoles() {
  const session = useOperatorSession();
  return session.roles || [];
}

export function useIsOperatorAdmin() {
  const roles = useOperatorRoles();
  return useMemo(() => roles.includes("operator_admin"), [roles]);
}

