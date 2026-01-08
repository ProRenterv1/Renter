import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { operatorAPI, type OperatorHealthResponse, type OperatorHealthResult } from "@/operator/api";
import { useIsOperatorAdmin, useOperatorSession } from "@/operator/session";
import { RefreshCw, Send } from "lucide-react";

type StatusPill = "OK" | "WARN" | "FAIL";

export function SystemHealthPage() {
  const isAdmin = useIsOperatorAdmin();
  const session = useOperatorSession();
  const [result, setResult] = useState<OperatorHealthResult | null>(null);
  const [lastCheckedAt, setLastCheckedAt] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [testTo, setTestTo] = useState<string>(session.email || "");
  const [sendingTest, setSendingTest] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await operatorAPI.health();
      setResult(resp);
      setLastCheckedAt(new Date());
    } catch (err: any) {
      setError(err?.message || "Unable to run health checks.");
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const data: OperatorHealthResponse | null = result?.data ?? null;
  const overallOk = data?.ok ?? false;

  const latencyLabel = result ? `${Math.max(result.latency_ms, 0)}ms` : "—";
  const checkedLabel = lastCheckedAt ? lastCheckedAt.toLocaleString() : "—";

  const cards = useMemo(() => {
    const checks = data?.checks || {};
    return [
      {
        key: "api",
        label: "API",
        payload: { ok: Boolean(result?.status), status: result?.status },
      },
      { key: "db", label: "DB", payload: checks["db"] || {} },
      { key: "pgbouncer", label: "Pgbouncer", payload: checks["pgbouncer"] || {} },
      { key: "redis", label: "Redis", payload: checks["redis"] || {} },
      { key: "celery", label: "Celery", payload: checks["celery"] || {} },
      { key: "stripe", label: "Stripe", payload: checks["stripe"] || {} },
      { key: "twilio", label: "Twilio", payload: checks["twilio"] || {} },
      { key: "email", label: "Email", payload: checks["email"] || {} },
      { key: "s3", label: "S3", payload: checks["s3"] || {} },
    ];
  }, [data?.checks, result?.status]);

  const sendTestEmail = async () => {
    const to = (testTo || session.email || "").trim();
    if (!to) {
      toast.error("Email address required");
      return;
    }
    setSendingTest(true);
    try {
      await operatorAPI.testEmail({ to });
      toast.success(`Test email sent to ${to}`);
    } catch (err: any) {
      toast.error(err?.data?.detail || "Failed to send test email.");
    } finally {
      setSendingTest(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="mb-1">System Health</h2>
          <p className="text-muted-foreground m-0">
            Last checked: <span className="font-medium text-foreground">{checkedLabel}</span> • Latency:{" "}
            <span className="font-medium text-foreground">{latencyLabel}</span>
          </p>
        </div>
        <Button variant="outline" onClick={load} disabled={loading}>
          <RefreshCw className="w-4 h-4" />
          {loading ? "Running..." : "Run checks"}
        </Button>
      </div>

      {error ? (
        <Card>
          <CardContent className="p-6 text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      <div className="flex items-center gap-3">
        <Badge className={overallOk ? "bg-[var(--success-solid)] text-white border-transparent" : "bg-[var(--error-solid)] text-white border-transparent"}>
          {overallOk ? "OK" : "DEGRADED"}
        </Badge>
        {result ? (
          <div className="text-sm text-muted-foreground">
            HTTP <span className="font-medium text-foreground">{result.status}</span>
          </div>
        ) : null}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <HealthCard
            key={card.key}
            label={card.label}
            checkKey={card.key}
            payload={card.payload}
            lastCheckedAt={checkedLabel}
            latencyLabel={latencyLabel}
            onRun={load}
            loading={loading}
          />
        ))}
      </div>

      {isAdmin ? (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle>Test Email</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="space-y-2 sm:col-span-2">
                <Label>To</Label>
                <Input value={testTo} onChange={(e) => setTestTo(e.target.value)} placeholder="you@example.com" />
              </div>
              <div className="flex items-end">
                <Button onClick={sendTestEmail} disabled={sendingTest || !testTo.trim()}>
                  <Send className="w-4 h-4" />
                  {sendingTest ? "Sending..." : "Send"}
                </Button>
              </div>
            </div>
            <p className="text-sm text-muted-foreground m-0">
              Sends a test message through the configured email backend.
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

function HealthCard({
  label,
  checkKey,
  payload,
  lastCheckedAt,
  latencyLabel,
  onRun,
  loading,
}: {
  label: string;
  checkKey: string;
  payload: Record<string, unknown>;
  lastCheckedAt: string;
  latencyLabel: string;
  onRun: () => void;
  loading: boolean;
}) {
  const ok = Boolean(payload?.ok);
  const pill = computeStatusPill(checkKey, payload);
  const pillClasses =
    pill === "OK"
      ? "bg-[var(--success-solid)] text-white border-transparent"
      : pill === "WARN"
        ? "bg-[var(--warning-strong)] text-foreground border-transparent"
        : "bg-[var(--error-solid)] text-white border-transparent";

  const details = buildDetails(checkKey, payload);
  const error = typeof payload?.error === "string" ? payload.error : null;

  return (
    <Card className="relative">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center justify-between">
          <span>{label}</span>
          <Badge className={pillClasses}>{pill}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="text-sm">
          <span className={ok ? "text-[var(--success-text)]" : "text-[var(--error-text)]"}>
            {ok ? "Healthy" : "Unhealthy"}
          </span>
        </div>

        {details.length ? (
          <div className="space-y-1 text-xs text-muted-foreground">
            {details.map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        ) : null}

        {error ? (
          <div className="rounded-md border border-[var(--error-border)] bg-[var(--error-bg)] p-2 text-xs text-[var(--error-text)]">
            {error}
          </div>
        ) : null}

        <div className="flex items-center justify-between gap-3 pt-1">
          <div className="text-xs text-muted-foreground">
            {lastCheckedAt} • {latencyLabel}
          </div>
          <Button variant="outline" size="sm" onClick={onRun} disabled={loading}>
            Run check
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function computeStatusPill(checkKey: string, payload: Record<string, unknown>): StatusPill {
  const ok = Boolean(payload?.ok);
  if (checkKey === "api") {
    const status = typeof payload?.status === "number" ? payload.status : null;
    if (!status) return "FAIL";
    if (status >= 500) return "WARN";
    return "OK";
  }
  if (ok) return "OK";

  if (checkKey === "celery") {
    const stale = Boolean(payload?.stale);
    if (stale) return "WARN";
  }

  const skipped = Boolean(payload?.skipped);
  if (skipped) return "OK";

  const configured = payload?.configured;
  if (checkKey === "twilio" && configured === false) return "WARN";

  return "FAIL";
}

function buildDetails(checkKey: string, payload: Record<string, unknown>) {
  const details: string[] = [];

  if (checkKey === "api") {
    const status = typeof payload?.status === "number" ? payload.status : null;
    if (status) details.push(`status: ${status}`);
    return details;
  }

  if (checkKey === "celery") {
    const lastSeen = payload?.last_seen_epoch;
    if (typeof lastSeen === "number" && Number.isFinite(lastSeen)) {
      details.push(`last_seen_epoch: ${lastSeen.toFixed(2)}`);
    } else {
      details.push("last_seen_epoch: —");
    }
    details.push(`stale: ${Boolean(payload?.stale)}`);
    return details;
  }

  if (checkKey === "stripe") {
    const accountId = typeof payload?.account_id === "string" ? payload.account_id : "";
    if (accountId) details.push(`account_id: ${accountId}`);
    return details;
  }

  if (checkKey === "twilio") {
    details.push(`configured: ${Boolean(payload?.configured)}`);
    return details;
  }

  if (checkKey === "s3") {
    if (payload?.skipped) details.push("skipped: true");
    const bucket = typeof payload?.bucket === "string" ? payload.bucket : "";
    if (bucket) details.push(`bucket: ${bucket}`);
    return details;
  }

  if (checkKey === "pgbouncer") {
    if (payload?.skipped) {
      details.push("skipped: true");
      return details;
    }
    const poolMode = typeof payload?.pool_mode === "string" ? payload.pool_mode : "";
    const poolCount = typeof payload?.pool_count === "number" ? payload.pool_count : null;
    const clActive = typeof payload?.cl_active === "number" ? payload.cl_active : null;
    const clWaiting = typeof payload?.cl_waiting === "number" ? payload.cl_waiting : null;
    const svActive = typeof payload?.sv_active === "number" ? payload.sv_active : null;
    const svIdle = typeof payload?.sv_idle === "number" ? payload.sv_idle : null;
    if (poolMode) details.push(`mode: ${poolMode}`);
    if (poolCount !== null) details.push(`pools: ${poolCount}`);
    if (clActive !== null || clWaiting !== null) {
      details.push(`clients active=${clActive ?? 0} waiting=${clWaiting ?? 0}`);
    }
    if (svActive !== null || svIdle !== null) {
      details.push(`servers active=${svActive ?? 0} idle=${svIdle ?? 0}`);
    }
    return details;
  }

  if (checkKey === "email") {
    const backend = typeof payload?.backend === "string" ? payload.backend : "";
    if (backend) details.push(`backend: ${backend}`);
    return details;
  }

  return details;
}
