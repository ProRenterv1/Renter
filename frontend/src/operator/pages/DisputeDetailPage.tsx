import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ArrowLeft,
  ExternalLink,
  Image,
  ListOrdered,
  MessageSquare,
  Package,
  ShieldCheck,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Separator } from "../../components/ui/separator";
import { Skeleton } from "../../components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { EmptyState } from "../components/EmptyState";
import { CountdownChip, StageBadge } from "../components/StatusChips";
import { PermissionGate } from "../components/PermissionGate";
import { EvidenceGallery } from "../components/disputes/EvidenceGallery";
import { MessageThread } from "../components/disputes/MessageThread";
import { Timeline } from "../components/disputes/Timeline";
import { AppealModal } from "../components/disputes/modals/AppealModal";
import { CloseCaseModal } from "../components/disputes/modals/CloseCaseModal";
import { RequestMoreEvidenceModal } from "../components/disputes/modals/RequestMoreEvidenceModal";
import { ResolveDisputeModal } from "../components/disputes/modals/ResolveDisputeModal";
import { formatCadCents } from "../utils/money";
import { OPERATOR_ADMIN_ROLE, OPERATOR_FINANCE_ROLE } from "../utils/permissions";
import {
  operatorAPI,
  type OperatorDisputeDetail,
  type OperatorDisputeAppealPayload,
  type OperatorDisputeClosePayload,
  type OperatorDisputeEvidenceRequestPayload,
  type OperatorDisputeResolvePayload,
} from "../api";

const TABS = [
  { value: "timeline", label: "Timeline", icon: ListOrdered },
  { value: "evidence", label: "Evidence", icon: Image },
  { value: "messages", label: "Messages", icon: MessageSquare },
  { value: "booking", label: "Booking context", icon: Package },
  { value: "resolution", label: "Resolution", icon: ShieldCheck },
];

export function DisputeDetailPage() {
  const navigate = useNavigate();
  const { disputeId } = useParams();
  const parsedId = Number(disputeId);

  const [activeTab, setActiveTab] = useState("timeline");
  const [dispute, setDispute] = useState<OperatorDisputeDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requestEvidenceOpen, setRequestEvidenceOpen] = useState(false);
  const [closeCaseOpen, setCloseCaseOpen] = useState(false);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [appealOpen, setAppealOpen] = useState(false);
  const isMountedRef = useRef(true);

  const headerTitle = Number.isFinite(parsedId) ? `Dispute #${parsedId}` : "Dispute";

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadDispute = async (showLoading = true) => {
    if (!Number.isFinite(parsedId)) {
      if (showLoading && isMountedRef.current) {
        setLoading(false);
      }
      if (isMountedRef.current) {
        setError("Invalid dispute id.");
      }
      return;
    }

    if (showLoading && isMountedRef.current) {
      setLoading(true);
      setDispute(null);
    }
    if (isMountedRef.current) {
      setError(null);
    }

    try {
      const data = await operatorAPI.disputeDetail(parsedId);
      if (!isMountedRef.current) return;
      setDispute(data);
    } catch (err: any) {
      if (!isMountedRef.current) return;
      const message = err?.data?.detail || "Unable to load dispute.";
      setError(message);
      toast.error(message);
    } finally {
      if (showLoading && isMountedRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    loadDispute(true);
  }, [parsedId]);

  const evidence = useMemo(() => {
    return (
      dispute?.evidence ?? {
        before_photos: [],
        after_photos: [],
        dispute_uploads: [],
      }
    );
  }, [dispute]);

  const timelineItems = dispute?.timeline ?? [];
  const messages = dispute?.messages ?? [];
  const booking = dispute?.booking ?? null;
  const resolution = dispute?.resolution ?? null;

  const handleRequestEvidence = async (payload: OperatorDisputeEvidenceRequestPayload) => {
    if (!Number.isFinite(parsedId)) return false;
    try {
      await operatorAPI.requestMoreEvidence(parsedId, payload);
      toast.success("Evidence request sent.");
      await loadDispute(false);
      return true;
    } catch (err: any) {
      toast.error(extractErrorMessage(err, "Unable to request evidence."));
      return false;
    }
  };

  const handleCloseCase = async (payload: OperatorDisputeClosePayload) => {
    if (!Number.isFinite(parsedId)) return false;
    try {
      await operatorAPI.closeDispute(parsedId, payload);
      toast.success("Dispute closed.");
      await loadDispute(false);
      return true;
    } catch (err: any) {
      toast.error(extractErrorMessage(err, "Unable to close dispute."));
      return false;
    }
  };

  const handleResolveDispute = async (payload: OperatorDisputeResolvePayload) => {
    if (!Number.isFinite(parsedId)) return false;
    try {
      await operatorAPI.resolveDispute(parsedId, payload);
      toast.success("Dispute resolved.");
      await loadDispute(false);
      return true;
    } catch (err: any) {
      toast.error(extractErrorMessage(err, "Unable to resolve dispute."));
      return false;
    }
  };

  const handleAppeal = async (payload: OperatorDisputeAppealPayload) => {
    if (!Number.isFinite(parsedId)) return false;
    try {
      await operatorAPI.appealDispute(parsedId, payload);
      toast.success("Appeal opened.");
      await loadDispute(false);
      return true;
    } catch (err: any) {
      toast.error(extractErrorMessage(err, "Unable to open appeal."));
      return false;
    }
  };

  if (loading) {
    return <DisputeDetailSkeleton />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="space-y-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate("/operator/disputes")}
            className="px-0 text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back to disputes
          </Button>
          <div>
            <h1 className="mb-2">{headerTitle}</h1>
            <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span>{formatLabel(dispute?.category || "--")}</span>
              <span>•</span>
              <span>{formatLabel(dispute?.flow || "--")}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StageBadge stage={dispute?.stage || "unknown"} />
          {dispute?.evidence_due_at ? (
            <CountdownChip dueAt={dispute.evidence_due_at} kind="evidence" />
          ) : (
            <Badge variant="outline" className="rounded-full text-xs">
              Evidence due - --
            </Badge>
          )}
          {dispute?.rebuttal_due_at ? (
            <CountdownChip dueAt={dispute.rebuttal_due_at} kind="rebuttal" />
          ) : (
            <Badge variant="outline" className="rounded-full text-xs">
              Rebuttal due - --
            </Badge>
          )}
          {dispute?.status ? (
            <Badge variant="outline" className="rounded-full text-xs">
              {formatLabel(dispute.status)}
            </Badge>
          ) : null}
        </div>
      </div>

      {error ? (
        <Card>
          <CardContent className="p-6 text-sm text-destructive">{error}</CardContent>
        </Card>
      ) : null}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col gap-6 lg:flex-row">
        <Card className="h-fit lg:w-64">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Sections</CardTitle>
          </CardHeader>
          <CardContent className="p-3">
            <TabsList className="flex h-auto w-full flex-col items-stretch gap-1 rounded-lg bg-muted/40 p-2">
              {TABS.map((tab) => {
                const Icon = tab.icon;
                return (
                  <TabsTrigger
                    key={tab.value}
                    value={tab.value}
                    className="w-full flex-none justify-start gap-2 rounded-lg px-3 py-2 text-sm"
                  >
                    <Icon className="h-4 w-4" />
                    <span className="flex-1 text-left">{tab.label}</span>
                  </TabsTrigger>
                );
              })}
            </TabsList>
          </CardContent>
        </Card>

        <Card className="flex-1">
          <CardContent className="p-6">
            <TabsContent value="timeline" className="space-y-4">
              <SectionHeader
                title="Timeline"
                description="Stage transitions, reminders, and operator actions."
              />
              <Timeline items={timelineItems} />
            </TabsContent>

            <TabsContent value="evidence" className="space-y-6">
              <SectionHeader
                title="Evidence"
                description="Before/after photos and dispute uploads."
              />
              <EvidenceGallery
                title="Before photos (pickup)"
                description="From booking pickup uploads."
                items={evidence.before_photos}
              />
              <Separator />
              <EvidenceGallery
                title="After photos (return)"
                description="From booking return uploads."
                items={evidence.after_photos}
              />
              <Separator />
              <EvidenceGallery
                title="Dispute uploads"
                description="Files uploaded during the dispute."
                items={evidence.dispute_uploads}
              />
            </TabsContent>

            <TabsContent value="messages" className="space-y-4">
              <SectionHeader
                title="Messages"
                description="Threaded conversation across owner, renter, operator, and system."
              />
              <MessageThread messages={messages} />
            </TabsContent>

            <TabsContent value="booking" className="space-y-6">
              <SectionHeader
                title="Booking context"
                description="Totals, deposit status, and quick links."
              />

              {booking ? (
                <div className="space-y-6">
                  <div className="rounded-lg border border-border bg-card p-4">
                    <div className="grid gap-4 md:grid-cols-2">
                      <DetailRow label="Booking ID" value={`#${booking.id}`} />
                      <DetailRow label="Listing" value={booking.listing_title || "--"} />
                      <DetailRow label="Owner" value={booking.owner_email || "--"} />
                      <DetailRow label="Renter" value={booking.renter_email || "--"} />
                      <DetailRow label="Start date" value={formatDate(booking.start_date)} />
                      <DetailRow label="End date" value={formatDate(booking.end_date)} />
                      <DetailRow label="Deposit status" value={formatDepositStatus(booking)} />
                      <DetailRow label="Deposit hold ID" value={booking.deposit_hold_id || "--"} />
                    </div>
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => navigate(`/operator/bookings/${booking.id}`)}
                      >
                        View booking
                        <ExternalLink className="ml-2 h-4 w-4" />
                      </Button>
                      {booking.chat_url || booking.chat_thread_id ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            const url = booking.chat_url || `/operator/comms?thread=${booking.chat_thread_id}`;
                            navigate(url);
                          }}
                        >
                          View chat history
                          <ExternalLink className="ml-2 h-4 w-4" />
                        </Button>
                      ) : null}
                    </div>
                  </div>

                  <div className="rounded-lg border border-border bg-card p-4">
                    <div className="text-sm font-semibold text-foreground">Totals</div>
                    <div className="mt-3 space-y-2 text-sm">
                      <DetailRow label="Subtotal" value={formatCadCents(booking.totals?.subtotal_cents)} />
                      <DetailRow label="Service fee" value={formatCadCents(booking.totals?.service_fee_cents)} />
                      <DetailRow label="Taxes" value={formatCadCents(booking.totals?.taxes_cents)} />
                      <Separator />
                      <DetailRow label="Total" value={formatCadCents(booking.totals?.total_cents)} bold />
                      <DetailRow label="Deposit hold" value={formatCadCents(booking.totals?.deposit_hold_cents)} />
                    </div>
                  </div>
                </div>
              ) : (
                <EmptyState
                  title="Booking context unavailable"
                  description="Booking details were not returned for this dispute."
                />
              )}
            </TabsContent>

            <TabsContent value="resolution" className="space-y-6">
              <SectionHeader
                title="Resolution"
                description="Operator resolution actions and outcomes."
              />

              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={() => setRequestEvidenceOpen(true)}>
                  Request more evidence
                </Button>
                <Button variant="outline" size="sm" onClick={() => setCloseCaseOpen(true)}>
                  Close case
                </Button>
                <Button variant="outline" size="sm" onClick={() => setAppealOpen(true)}>
                  Open appeal
                </Button>
                <PermissionGate
                  roles={[OPERATOR_ADMIN_ROLE, OPERATOR_FINANCE_ROLE]}
                  fallback={
                    <Button variant="outline" size="sm" disabled>
                      Resolve dispute (finance only)
                    </Button>
                  }
                >
                  <Button size="sm" onClick={() => setResolveOpen(true)}>
                    Resolve dispute
                  </Button>
                </PermissionGate>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-foreground">Current resolution</div>
                    <div className="text-xs text-muted-foreground">
                      {resolution?.resolved_at
                        ? `Resolved ${formatDateTime(resolution.resolved_at)}`
                        : "Not resolved yet."}
                    </div>
                  </div>
                </div>
                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <DetailRow
                    label="Refund"
                    value={formatCadCents(resolution?.refund_cents)}
                  />
                  <DetailRow
                    label="Capture"
                    value={formatCadCents(resolution?.capture_cents)}
                  />
                  <DetailRow
                    label="Resolution note"
                    value={resolution?.note || "--"}
                  />
                  <DetailRow
                    label="Resolved by"
                    value={resolution?.resolved_by || "--"}
                  />
                </div>
              </div>
            </TabsContent>
          </CardContent>
        </Card>
      </Tabs>

      <RequestMoreEvidenceModal
        open={requestEvidenceOpen}
        onOpenChange={setRequestEvidenceOpen}
        onSubmit={handleRequestEvidence}
      />
      <CloseCaseModal
        open={closeCaseOpen}
        onOpenChange={setCloseCaseOpen}
        onSubmit={handleCloseCase}
      />
      <ResolveDisputeModal
        open={resolveOpen}
        onOpenChange={setResolveOpen}
        onSubmit={handleResolveDispute}
        booking={booking}
        openedByRole={dispute?.opened_by_role}
      />
      <AppealModal
        open={appealOpen}
        onOpenChange={setAppealOpen}
        onSubmit={handleAppeal}
      />
    </div>
  );
}

function SectionHeader({ title, description }: { title: string; description?: string }) {
  return (
    <div className="space-y-1">
      <h2 className="text-base font-semibold text-foreground">{title}</h2>
      {description ? (
        <p className="text-sm text-muted-foreground">{description}</p>
      ) : null}
    </div>
  );
}

function DetailRow({
  label,
  value,
  bold = false,
}: {
  label: string;
  value: string;
  bold?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className={bold ? "text-sm font-semibold text-foreground" : "text-sm"}>{value}</span>
    </div>
  );
}

function formatLabel(value: string) {
  if (!value || value === "--") {
    return "--";
  }
  return value
    .replace(/[_-]+/g, " ")
    .split(" ")
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ""))
    .join(" ")
    .trim();
}

function formatDate(value?: string | null) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString();
}

function formatDateTime(value?: string | null) {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatDepositStatus(booking: OperatorDisputeDetail["booking"]) {
  if (!booking) return "--";
  if (booking.deposit_locked) return "Locked";
  if (booking.deposit_status) return formatLabel(booking.deposit_status);
  if (booking.deposit_hold_id) return "Held";
  return "--";
}

function DisputeDetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-3">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-8 w-56" />
        <div className="flex flex-wrap gap-2">
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-6 w-28 rounded-full" />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[16rem_1fr]">
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-[480px] w-full" />
      </div>
    </div>
  );
}

function extractErrorMessage(err: any, fallback: string) {
  return err?.data?.detail || fallback;
}
