import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type GoogleIdentityContextValue = {
  clientId: string | null;
  ready: boolean;
  setCredentialCallback: (callback: (response: GoogleCredentialResponse) => void) => void;
};

const GoogleIdentityContext = createContext<GoogleIdentityContextValue>({
  clientId: null,
  ready: false,
  setCredentialCallback: () => {},
});

const GOOGLE_IDENTITY_SCRIPT_SRC = "https://accounts.google.com/gsi/client";
const GOOGLE_IDENTITY_SCRIPT_ID = "google-identity-service";

let scriptPromise: Promise<void> | null = null;
const loadGoogleIdentityScript = () => {
  if (window.google?.accounts?.id) {
    return Promise.resolve();
  }
  if (scriptPromise) {
    return scriptPromise;
  }

  scriptPromise = new Promise((resolve, reject) => {
    const existing = document.getElementById(
      GOOGLE_IDENTITY_SCRIPT_ID,
    ) as HTMLScriptElement | null;
    if (existing) {
      existing.addEventListener("load", () => resolve(), { once: true });
      existing.addEventListener(
        "error",
        () => reject(new Error("Google Identity Services failed to load.")),
        { once: true },
      );
      return;
    }

    const script = document.createElement("script");
    script.id = GOOGLE_IDENTITY_SCRIPT_ID;
    script.src = GOOGLE_IDENTITY_SCRIPT_SRC;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Google Identity Services failed to load."));
    document.head.appendChild(script);
  });

  return scriptPromise;
};

export function GoogleIdentityProvider({ children }: { children: ReactNode }) {
  const clientId = import.meta.env.VITE_GOOGLE_OAUTH_CLIENT_ID || null;
  const [ready, setReady] = useState(false);
  const credentialCallbackRef = useRef<(response: GoogleCredentialResponse) => void>(() => {});
  const initializedClientIdRef = useRef<string | null>(null);
  const setCredentialCallback = useCallback(
    (callback: (response: GoogleCredentialResponse) => void) => {
      credentialCallbackRef.current = callback;
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    if (!clientId) {
      setReady(false);
      initializedClientIdRef.current = null;
      return undefined;
    }

    loadGoogleIdentityScript()
      .then(() => {
        if (!cancelled) {
          if (!window.google?.accounts?.id) {
            setReady(false);
            return;
          }
          if (initializedClientIdRef.current !== clientId) {
            try {
              window.google.accounts.id.initialize({
                client_id: clientId,
                callback: (response) => credentialCallbackRef.current(response),
                ux_mode: "popup",
              });
              initializedClientIdRef.current = clientId;
            } catch {
              setReady(false);
              return;
            }
          }
          setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setReady(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [clientId]);

  const value = useMemo(
    () => ({ clientId, ready, setCredentialCallback }),
    [clientId, ready, setCredentialCallback],
  );
  return <GoogleIdentityContext.Provider value={value}>{children}</GoogleIdentityContext.Provider>;
}

export const useGoogleIdentity = () => useContext(GoogleIdentityContext);
