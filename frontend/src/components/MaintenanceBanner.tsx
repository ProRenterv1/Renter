import { AlertTriangle, Info, OctagonAlert, RefreshCw } from "lucide-react";
import type { MaintenanceBanner as MaintenanceBannerType } from "@/lib/api";

type Props = {
  severity?: MaintenanceBannerType["severity"];
  message?: string;
  showRetry?: boolean;
};

/**
  * Presentational maintenance overlay. Caller controls when to render.
  * Use in App to completely replace page content during maintenance.
  */
export function MaintenanceBanner({
  severity = "info",
  message = "We’re performing maintenance. Please check back soon.",
  showRetry = true,
}: Props) {
  const iconMap = {
    info: Info,
    warning: AlertTriangle,
    error: OctagonAlert,
  };
  const Icon = iconMap[severity] ?? Info;
  const classMap: Record<MaintenanceBannerType["severity"], { bg: string; accent: string; text: string }> = {
    info: { bg: "from-blue-50 via-white to-blue-100", accent: "text-blue-700", text: "text-slate-800" },
    warning: { bg: "from-amber-50 via-white to-amber-100", accent: "text-amber-700", text: "text-slate-900" },
    error: { bg: "from-rose-50 via-white to-rose-100", accent: "text-rose-700", text: "text-slate-900" },
  };

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center px-4 py-8 bg-slate-900/70 backdrop-blur-sm">
      <div
        role="alert"
        aria-live="assertive"
        className={`w-full max-w-2xl rounded-2xl border border-slate-200 shadow-2xl bg-gradient-to-br ${classMap[severity].bg} ${classMap[severity].text} p-8`}
      >
        <div className="flex items-center gap-3">
          <div className={`flex h-12 w-12 items-center justify-center rounded-xl bg-white/70 border ${classMap[severity].accent}`}>
            <Icon className="h-6 w-6" />
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-semibold m-0">Maintenance</h1>
              <span className="rounded-full border px-3 py-1 text-xs font-semibold uppercase bg-white/80">
                {severity}
              </span>
            </div>
            <p className="mt-2 text-base leading-relaxed">{message}</p>
          </div>
        </div>
        <div className="mt-6 flex flex-wrap items-center gap-3 text-sm text-slate-700">
          <span>We’re making improvements. The site will be back shortly.</span>
          {showRetry ? (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white/90 px-3 py-2 text-sm font-semibold text-slate-800 shadow-sm hover:bg-white"
            >
              <RefreshCw className="h-4 w-4" />
              Retry
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
