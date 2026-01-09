import type React from "react";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { format, formatDistanceToNow } from "date-fns";
import {
  ArrowLeft,
  BadgeAlert,
  Calendar,
  CalendarCheck,
  ClipboardList,
  FileText,
  KeyRound,
  MapPin,
  Mail,
  Package,
  Phone,
  RefreshCw,
  Shield,
  ShieldAlert,
  UserCheck,
  UserX,
  XCircle,
  CheckCircle2,
  Lock,
  DollarSign,
} from "lucide-react";
import { toast } from "sonner";

import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../../components/ui/tabs";
import { Skeleton } from "../../components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../../components/ui/dialog";
import { Label } from "../../components/ui/label";
import { Input } from "../../components/ui/input";
import { Textarea } from "../../components/ui/textarea";
import { Switch } from "../../components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../../components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { EmptyState } from "@/operator/components/EmptyState";
import { listingsAPI, type Listing } from "@/lib/api";
import { formatCurrency, parseMoney } from "@/lib/utils";
import {
  formatOperatorUserName,
  operatorAPI,
  type OperatorBookingSummary,
   type OperatorTransaction,
  type OperatorNote,
  type OperatorUserDetail,
} from "../api";
import { copyToClipboard } from "../utils/clipboard";

type VerificationToggle = "email" | "phone";

const levelOptions = [
  { value: "low", label: "Low" },
  { value: "med", label: "Medium" },
  { value: "high", label: "High" },
];

const categoryOptions = [
  { value: "fraud", label: "Fraud" },
  { value: "chargeback", label: "Chargeback risk" },
  { value: "abuse", label: "Bad-faith disputes / abuse" },
  { value: "other", label: "Other" },
];

export function UserDetail() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("bookings");
  const [user, setUser] = useState<OperatorUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [listingsLoading, setListingsLoading] = useState(false);
  const [listingsError, setListingsError] = useState<string | null>(null);

  const [notes, setNotes] = useState<OperatorNote[]>([]);
  const [notesLoading, setNotesLoading] = useState(false);
  const [notesError, setNotesError] = useState<string | null>(null);
  const [noteText, setNoteText] = useState("");
  const [noteTags, setNoteTags] = useState("");
  const [noteReason, setNoteReason] = useState("");
  const [noteSubmitting, setNoteSubmitting] = useState(false);
  const [financeRows, setFinanceRows] = useState<OperatorTransaction[]>([]);
  const [financeLoading, setFinanceLoading] = useState(false);
  const [financeError, setFinanceError] = useState<string | null>(null);

  const [suspendOpen, setSuspendOpen] = useState(false);
  const [reinstateOpen, setReinstateOpen] = useState(false);
  const [permissionsOpen, setPermissionsOpen] = useState(false);
  const [markSuspiciousOpen, setMarkSuspiciousOpen] = useState(false);
  const [passwordResetOpen, setPasswordResetOpen] = useState(false);
  const [resendVerificationOpen, setResendVerificationOpen] = useState(false);

  const [confirmText, setConfirmText] = useState("");
  const [reasonText, setReasonText] = useState("");
  const [restrictionsReason, setRestrictionsReason] = useState("");
  const [markLevel, setMarkLevel] = useState("med");
  const [markCategory, setMarkCategory] = useState("fraud");
  const [markNote, setMarkNote] = useState("");
  const [markReason, setMarkReason] = useState("");
  const [permissionsForm, setPermissionsForm] = useState<{ can_rent: boolean; can_list: boolean }>({
    can_rent: true,
    can_list: true,
  });
  const [resendReason, setResendReason] = useState("");
  const [resendChannels, setResendChannels] = useState<{ email: boolean; phone: boolean }>({
    email: false,
    phone: false,
  });
  const [passwordResetReason, setPasswordResetReason] = useState("");

  const [actionLoading, setActionLoading] = useState(false);

  const numericUserId = userId ? Number(userId) : null;
  const isValidUserId = Number.isInteger(numericUserId) && (numericUserId ?? 0) > 0;

  useEffect(() => {
    let cancelled = false;
    if (!isValidUserId) {
      setError("The requested user could not be found.");
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    operatorAPI
      .userDetail(numericUserId!)
      .then((data) => {
        if (cancelled) return;
        setUser(data);
      })
      .catch((err) => {
        console.error("Failed to load user detail", err);
        if (cancelled) return;
        setError("The requested user could not be found.");
        setUser(null);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isValidUserId, numericUserId]);

  useEffect(() => {
    let cancelled = false;
    if (!user?.id) {
      setListings([]);
      return;
    }
    setListingsLoading(true);
    setListingsError(null);
    listingsAPI
      .list({ owner_id: user.id })
      .then((data) => {
        if (cancelled) return;
        setListings(data.results ?? []);
      })
      .catch((err) => {
        console.error("Failed to load listings for user", err);
        if (cancelled) return;
        setListings([]);
        setListingsError("Unable to load listings for this user.");
      })
      .finally(() => {
        if (cancelled) return;
        setListingsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  useEffect(() => {
    let cancelled = false;
    if (!user?.id) {
      setNotes([]);
      return;
    }
    setNotesLoading(true);
    setNotesError(null);
    operatorAPI
      .listNotes("user", user.id)
      .then((data) => {
        if (cancelled) return;
        setNotes(data);
      })
      .catch((err) => {
        console.error("Failed to load notes", err);
        if (cancelled) return;
        setNotesError("Unable to load notes right now.");
      })
      .finally(() => {
        if (cancelled) return;
        setNotesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  useEffect(() => {
    let cancelled = false;
    if (!user?.id) {
      setFinanceRows([]);
      return;
    }
    setFinanceLoading(true);
    setFinanceError(null);
    operatorAPI
      .financeTransactions({ user: user.id, page_size: 200 })
      .then((data) => {
        if (cancelled) return;
        const list = Array.isArray((data as any)?.results) ? (data as any).results : (data as any);
        setFinanceRows(Array.isArray(list) ? list : []);
      })
      .catch((err) => {
        console.error("Failed to load finance data", err);
        if (cancelled) return;
        setFinanceError("Unable to load finance data for this user.");
      })
      .finally(() => {
        if (cancelled) return;
        setFinanceLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const displayName = useMemo(() => (user ? formatOperatorUserName(user) : "User"), [user]);
  const initials = useMemo(() => {
    if (!user) return "U";
    const name = displayName;
    const parts = name.split(" ").filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    if (parts.length === 1) return parts[0][0]?.toUpperCase() ?? "U";
    if (user.username) return user.username[0]?.toUpperCase() ?? "U";
    if (user.email) return user.email[0]?.toUpperCase() ?? "U";
    return "U";
  }, [displayName, user]);

  const joinedLabel = useMemo(() => {
    if (!user?.date_joined) return "—";
    const parsed = new Date(user.date_joined);
    if (Number.isNaN(parsed.getTime())) return "—";
    try {
      return format(parsed, "PPP");
    } catch {
      return parsed.toLocaleDateString();
    }
  }, [user?.date_joined]);

  const addressLine = useMemo(() => {
    if (!user) return "—";
    const parts = [user.street_address, user.city, user.province, user.postal_code].filter(Boolean);
    return parts.length ? parts.join(", ") : "—";
  }, [user]);

  const financeSummary = useMemo(() => {
    const spendableKinds = new Set(["OWNER_EARNING", "REFUND", "OWNER_PAYOUT"]);
    let balance = 0;
    let totalPayouts = 0;
    let totalEarnings = 0;
    let totalCharges = 0;
    let currency = "CAD";

    financeRows.forEach((tx) => {
      const amount = parseMoney(tx.amount);
      currency = tx.currency?.toUpperCase?.() || currency;
      if (tx.kind === "OWNER_PAYOUT") {
        totalPayouts += Math.abs(amount);
      }
      if (tx.kind === "OWNER_EARNING") {
        totalEarnings += amount;
      }
      if (spendableKinds.has(tx.kind)) {
        balance += amount;
      }
      if (tx.kind === "BOOKING_CHARGE" || tx.kind === "PROMOTION_CHARGE") {
        totalCharges += amount;
      }
    });

    return { balance, totalPayouts, totalEarnings, totalCharges, currency };
  }, [financeRows]);

  const bookings = Array.isArray(user?.bookings) ? user?.bookings : [];
  const isSuspended = !user?.is_active;
  const hasEmail = Boolean(user?.email);
  const hasPhone = Boolean(user?.phone);

  const resetModals = () => {
    setConfirmText("");
    setReasonText("");
    setRestrictionsReason("");
    setMarkLevel("med");
    setMarkCategory("fraud");
    setMarkNote("");
    setMarkReason("");
    setPermissionsForm({
      can_rent: Boolean(user?.can_rent),
      can_list: Boolean(user?.can_list),
    });
    setResendReason("");
    setResendChannels({ email: Boolean(hasEmail), phone: false });
    setPasswordResetReason("");
  };

  const openRestrictions = (bookingOnly = false) => {
    setPermissionsForm({
      can_rent: bookingOnly ? true : Boolean(user?.can_rent),
      can_list: bookingOnly ? false : Boolean(user?.can_list),
    });
    setRestrictionsReason(bookingOnly ? "Limit user to booking only" : "");
    setPermissionsOpen(true);
  };

  const handleSuspend = async () => {
    if (!user) return;
    if (confirmText.trim() !== "CONFIRM") {
      toast.error("Type CONFIRM to proceed.");
      return;
    }
    if (!reasonText.trim()) {
      toast.error("A reason is required.");
      return;
    }
    setActionLoading(true);
    try {
      await operatorAPI.suspendUser(user.id, { reason: reasonText.trim() });
      setUser((prev) => (prev ? { ...prev, is_active: false } : prev));
      toast.success("User suspended");
      setSuspendOpen(false);
      resetModals();
    } catch (err) {
      toast.error(extractErrorMessage(err, "Unable to suspend user."));
    } finally {
      setActionLoading(false);
    }
  };

  const handleReinstate = async () => {
    if (!user) return;
    if (!reasonText.trim()) {
      toast.error("A reason is required.");
      return;
    }
    setActionLoading(true);
    try {
      await operatorAPI.reinstateUser(user.id, { reason: reasonText.trim() });
      setUser((prev) => (prev ? { ...prev, is_active: true } : prev));
      toast.success("User reinstated");
      setReinstateOpen(false);
      resetModals();
    } catch (err) {
      toast.error(extractErrorMessage(err, "Unable to reinstate user."));
    } finally {
      setActionLoading(false);
    }
  };

  const handleSetRestrictions = async () => {
    if (!user) return;
    if (!restrictionsReason.trim()) {
      toast.error("A reason is required.");
      return;
    }
    setActionLoading(true);
    try {
      const response = await operatorAPI.setUserRestrictions(user.id, {
        can_rent: permissionsForm.can_rent,
        can_list: permissionsForm.can_list,
        reason: restrictionsReason.trim(),
      });
      setUser((prev) =>
        prev
          ? {
              ...prev,
              can_rent: response.can_rent ?? prev.can_rent,
              can_list: response.can_list ?? prev.can_list,
            }
          : prev,
      );
      toast.success("Permissions updated");
      setPermissionsOpen(false);
      resetModals();
    } catch (err) {
      toast.error(extractErrorMessage(err, "Unable to update permissions."));
    } finally {
      setActionLoading(false);
    }
  };

  const handleMarkSuspicious = async () => {
    if (!user) return;
    if (!markReason.trim()) {
      toast.error("A reason is required.");
      return;
    }
    setActionLoading(true);
    try {
      await operatorAPI.markUserSuspicious(user.id, {
        level: markLevel,
        category: markCategory,
        note: markNote.trim(),
        reason: markReason.trim(),
      });
      toast.success("User marked as suspicious");
      setMarkSuspiciousOpen(false);
      resetModals();
    } catch (err) {
      toast.error(extractErrorMessage(err, "Unable to mark suspicious."));
    } finally {
      setActionLoading(false);
    }
  };

  const handlePasswordReset = async () => {
    if (!user) return;
    if (!passwordResetReason.trim()) {
      toast.error("A reason is required.");
      return;
    }
    setActionLoading(true);
    try {
      await operatorAPI.sendPasswordReset(user.id, { reason: passwordResetReason.trim() });
      toast.success("Password reset sent");
      setPasswordResetOpen(false);
      resetModals();
    } catch (err) {
      toast.error(extractErrorMessage(err, "Unable to send password reset."));
    } finally {
      setActionLoading(false);
    }
  };

  const handleResendVerification = async () => {
    if (!user) return;
    const channels: VerificationToggle[] = [];
    if (resendChannels.email && hasEmail) channels.push("email");
    if (resendChannels.phone && hasPhone) channels.push("phone");
    if (!channels.length) {
      toast.error("Select at least one channel.");
      return;
    }
    if (!resendReason.trim()) {
      toast.error("A reason is required.");
      return;
    }
    setActionLoading(true);
    try {
      for (const channel of channels) {
        await operatorAPI.resendVerification(user.id, { channel, reason: resendReason.trim() });
      }
      toast.success(`Verification sent via ${channels.join(" & ")}`);
      setResendVerificationOpen(false);
      resetModals();
    } catch (err) {
      toast.error(extractErrorMessage(err, "Unable to resend verification."));
    } finally {
      setActionLoading(false);
    }
  };

  const handleAddNote = async () => {
    if (!user) return;
    if (!noteText.trim()) {
      toast.error("Note text is required.");
      return;
    }
    if (!noteReason.trim()) {
      toast.error("Reason is required.");
      return;
    }
    setNoteSubmitting(true);
    try {
      const tags = noteTags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);
      const created = await operatorAPI.createNote({
        entity_type: "user",
        entity_id: user.id,
        text: noteText.trim(),
        tags,
        reason: noteReason.trim(),
      });
      setNotes((prev) => [created, ...(prev ?? [])]);
      setNoteText("");
      setNoteTags("");
      setNoteReason("");
      toast.success("Note added");
    } catch (err) {
      toast.error(extractErrorMessage(err, "Unable to add note."));
    } finally {
      setNoteSubmitting(false);
    }
  };

  const formatTxnDate = (value: string) => {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    try {
      return format(parsed, "yyyy-MM-dd HH:mm");
    } catch {
      return parsed.toLocaleString();
    }
  };

  if (loading) {
    return <UserDetailSkeleton onBack={() => navigate("/operator/users")} />;
  }

  if (error || !user) {
    return (
      <div className="space-y-6">
        <Button variant="ghost" onClick={() => navigate("/operator/users")}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Users
        </Button>
        <Card>
          <CardContent className="p-12 text-center">
            <h2 className="mb-2">User Not Found</h2>
            <p className="text-muted-foreground">{error || "The requested user could not be found."}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate("/operator/users")}>
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Users
      </Button>

      <div className="grid gap-6 xl:grid-cols-[2fr_1fr] items-start">
        <div className="space-y-6">
          <Card>
            <CardContent className="p-6">
              <div className="flex flex-wrap items-center gap-6">
                <div className="w-20 h-20 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-2xl">
                  {initials}
                </div>

                <div className="flex-1 min-w-[240px] space-y-3">
                  <div className="flex items-center gap-3 flex-wrap">
                    <h1 className="m-0">{displayName}</h1>
                    {user.username ? <span className="text-muted-foreground">@{user.username}</span> : null}
                    <Badge variant={user.is_active ? "secondary" : "destructive"}>
                      {user.is_active ? "Active" : "Suspended"}
                    </Badge>
                  </div>

                  <div className="flex gap-2 flex-wrap">
                    {user.can_rent && (
                      <Badge variant="outline" className="capitalize">
                        <CalendarCheck className="w-3 h-3 mr-1" />
                        Renter
                      </Badge>
                    )}
                    {user.can_list && (
                      <Badge variant="outline" className="capitalize">
                        <Package className="w-3 h-3 mr-1" />
                        Owner
                      </Badge>
                    )}
                  </div>

                  <div className="flex gap-2 flex-wrap">
                    <Button size="sm" variant="outline" onClick={() => setMarkSuspiciousOpen(true)}>
                      <ShieldAlert className="w-4 h-4 mr-1" />
                      Mark suspicious (fraud/bad-faith)
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => openRestrictions(true)}
                      disabled={!user.can_list && user.can_rent}
                    >
                      <Lock className="w-4 h-4 mr-1" />
                      Limit to bookings only
                    </Button>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-6 md:grid-cols-2">
            <Card className="h-full">
              <CardHeader>
                <CardTitle>Contact & Location</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <ContactRow
                  icon={Mail}
                  label="Email"
                  value={user.email}
                  onCopy={() => (user.email ? copyToClipboard(user.email, "Email") : null)}
                />
                <ContactRow
                  icon={Phone}
                  label="Phone"
                  value={user.phone}
                  onCopy={() => (user.phone ? copyToClipboard(user.phone, "Phone") : null)}
                />
                <div className="flex items-start gap-3">
                  <MapPin className="w-5 h-5 text-muted-foreground mt-0.5" />
                  <div className="flex-1">
                    <div className="text-sm text-muted-foreground mb-1">Address</div>
                    <div>{addressLine}</div>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <Calendar className="w-5 h-5 text-muted-foreground mt-0.5" />
                  <div className="flex-1">
                    <div className="text-sm text-muted-foreground mb-1">Joined</div>
                    <div>{joinedLabel}</div>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card className="h-full">
              <CardHeader>
                <CardTitle>Verification Status</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <VerificationItem icon={Mail} label="Email Verified" verified={user.email_verified} />
                <VerificationItem icon={Phone} label="Phone Verified" verified={user.phone_verified} />
                <VerificationItem
                  icon={Shield}
                  label="Identity Verified"
                  verified={user.identity_verified}
                />
                <div className="pt-4 border-t border-border">
                  <div className="grid grid-cols-2 gap-4">
                    <PermissionItem label="Can Rent" enabled={user.can_rent} />
                    <PermissionItem label="Can List" enabled={user.can_list} />
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          <Card className="w-full">
            <CardHeader>
              <CardTitle>Activity</CardTitle>
            </CardHeader>
            <CardContent>
              <Tabs value={activeTab} onValueChange={setActiveTab}>
                <TabsList className="grid w-full grid-cols-5">
                  <TabsTrigger value="bookings">
                    <CalendarCheck className="w-4 h-4 mr-2" />
                    Bookings
                  </TabsTrigger>
                  <TabsTrigger value="listings">
                    <Package className="w-4 h-4 mr-2" />
                    Listings
                  </TabsTrigger>
                  <TabsTrigger value="finance">
                    <DollarSign className="w-4 h-4 mr-2" />
                    Finance
                  </TabsTrigger>
                  <TabsTrigger value="notes">
                    <FileText className="w-4 h-4 mr-2" />
                    Notes
                  </TabsTrigger>
                  <TabsTrigger value="audit">
                    <ClipboardList className="w-4 h-4 mr-2" />
                    Audit
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="bookings" className="mt-6">
                  {bookings.length > 0 ? (
                    <div className="space-y-3">
                      {bookings.map((booking: OperatorBookingSummary) => (
                        <div
                          key={booking.id}
                          className="p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors flex justify-between gap-4"
                        >
                          <div className="flex-1">
                            <div className="flex items-center gap-2 mb-2">
                              <span className="text-sm text-muted-foreground">BK-{booking.id}</span>
                              <Badge
                                variant={
                                  booking.status?.toLowerCase() === "completed" ? "secondary" : "outline"
                                }
                              >
                                {booking.status || "—"}
                              </Badge>
                            </div>
                            <div className="mb-1 font-medium">{booking.listing_title || "Listing"}</div>
                            <div className="text-sm text-muted-foreground">
                              {booking.role === "owner" ? "Renter" : "Owner"}: {booking.other_party || "—"}
                            </div>
                          </div>
                          <div className="text-right whitespace-nowrap">
                            <div className="mb-2 text-base">
                              {booking.amount ? formatCurrency(parseMoney(booking.amount)) : "—"}
                            </div>
                            <div className="text-sm text-muted-foreground">
                              {booking.end_date ? format(new Date(booking.end_date), "yyyy-MM-dd") : "—"}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      icon={CalendarCheck}
                      title="No bookings"
                      description="This user hasn't made or received any bookings yet"
                    />
                  )}
                </TabsContent>

                <TabsContent value="listings" className="mt-6">
                  {listingsLoading ? (
                    <div className="space-y-3">
                      {Array.from({ length: 3 }).map((_, idx) => (
                        <Skeleton key={idx} className="h-20 w-full rounded-lg" />
                      ))}
                    </div>
                  ) : listingsError ? (
                    <div className="text-destructive text-sm">{listingsError}</div>
                  ) : listings.length > 0 ? (
                    <div className="space-y-3">
                      {listings.map((listing) => (
                        <div
                          key={listing.id}
                          className="p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors"
                        >
                          <div className="flex justify-between items-start">
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-2">
                                <span className="text-sm text-muted-foreground">#{listing.id}</span>
                                <Badge variant={listing.is_active ? "default" : "secondary"}>
                                  {listing.is_active ? "Active" : "Paused"}
                                </Badge>
                              </div>
                              <div className="mb-1">{listing.title}</div>
                              <div className="text-sm text-muted-foreground">{listing.city}</div>
                            </div>
                            <div className="text-right">
                              <div className="mb-2">
                                {formatCurrency(parseMoney(listing.daily_price_cad))}/day
                              </div>
                              <div className="text-sm text-muted-foreground">
                                {listing.created_at
                                  ? `Listed ${format(new Date(listing.created_at), "PP")}`
                                  : "—"}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      icon={Package}
                      title="No listings"
                      description="This user hasn't created any listings yet"
                    />
                  )}
                </TabsContent>

                <TabsContent value="finance" className="mt-6">
                  {financeLoading ? (
                    <div className="space-y-3">
                      <Skeleton className="h-10 w-full" />
                      <Skeleton className="h-24 w-full" />
                      <Skeleton className="h-10 w-full" />
                    </div>
                  ) : financeError ? (
                    <div className="text-sm text-destructive">{financeError}</div>
                  ) : (
                    <div className="space-y-4">
                      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
                        <FinanceStat
                          label="Current balance"
                          value={formatCurrency(financeSummary.balance, financeSummary.currency)}
                          hint="Earnings + refunds − payouts"
                        />
                        <FinanceStat
                          label="Total payouts"
                          value={formatCurrency(financeSummary.totalPayouts, financeSummary.currency)}
                          hint="Lifetime payouts sent"
                        />
                        <FinanceStat
                          label="Total earnings"
                          value={formatCurrency(financeSummary.totalEarnings, financeSummary.currency)}
                          hint="Owner earnings credited"
                        />
                        <FinanceStat
                          label="Charges"
                          value={formatCurrency(Math.abs(financeSummary.totalCharges), financeSummary.currency)}
                          hint="Charges and promotion debits"
                        />
                      </div>

                      <Card>
                        <CardHeader>
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <CardTitle className="text-base">Transactions</CardTitle>
                            <div className="text-sm text-muted-foreground">
                              Showing {financeRows.length} record{financeRows.length === 1 ? "" : "s"}
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent>
                          <div className="overflow-x-auto">
                            <Table>
                              <TableHeader>
                                <TableRow>
                                  <TableHead>Date</TableHead>
                                  <TableHead>Kind</TableHead>
                                  <TableHead>Booking</TableHead>
                                  <TableHead>Amount</TableHead>
                                  <TableHead>Stripe Ref</TableHead>
                                </TableRow>
                              </TableHeader>
                              <TableBody>
                                {financeRows.map((tx) => {
                                  const amount = parseMoney(tx.amount);
                                  const displayCurrency = tx.currency?.toUpperCase?.() || "CAD";
                                  const amountClass =
                                    amount < 0 ? "text-destructive" : amount > 0 ? "text-emerald-700" : "";
                                  return (
                                    <TableRow key={tx.id}>
                                      <TableCell className="whitespace-nowrap">{formatTxnDate(tx.created_at)}</TableCell>
                                      <TableCell>
                                        <Badge variant="outline" className="uppercase tracking-wide">
                                          {tx.kind}
                                        </Badge>
                                      </TableCell>
                                      <TableCell>{tx.booking_id ?? "—"}</TableCell>
                                      <TableCell className={`font-semibold ${amountClass}`}>
                                        {formatCurrency(amount, displayCurrency)}
                                      </TableCell>
                                      <TableCell className="text-xs">{tx.stripe_id || "—"}</TableCell>
                                    </TableRow>
                                  );
                                })}
                                {!financeRows.length && (
                                  <TableRow>
                                    <TableCell colSpan={5} className="text-center text-muted-foreground">
                                      No finance activity yet for this user.
                                    </TableCell>
                                  </TableRow>
                                )}
                              </TableBody>
                            </Table>
                          </div>
                        </CardContent>
                      </Card>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="notes" className="mt-6">
                  {notesLoading ? (
                    <div className="space-y-2">
                      {Array.from({ length: 3 }).map((_, idx) => (
                        <Skeleton key={idx} className="h-20 w-full rounded-lg" />
                      ))}
                    </div>
                  ) : notesError ? (
                    <div className="text-sm text-destructive">{notesError}</div>
                  ) : notes.length ? (
                    <div className="space-y-3">
                      {notes.map((note) => (
                        <NoteCard key={note.id} note={note} />
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      icon={FileText}
                      title="No notes yet"
                      description="Add an internal note using the form on the right."
                    />
                  )}
                </TabsContent>

                <TabsContent value="audit" className="mt-6">
                  <EmptyState
                    icon={ClipboardList}
                    title="Audit log"
                    description="User activity audit log coming soon"
                  />
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <ActionButton
                icon={isSuspended ? UserCheck : UserX}
                label={isSuspended ? "Reinstate User" : "Suspend User"}
                description={isSuspended ? "Restore login and activity" : "Disable login and all activity"}
                onClick={() => {
                  resetModals();
                  isSuspended ? setReinstateOpen(true) : setSuspendOpen(true);
                }}
                variant={isSuspended ? "secondary" : "destructive"}
              />
              <ActionButton
                icon={KeyRound}
                label="Edit Permissions"
                description="Toggle booking/listing abilities"
                onClick={() => {
                  resetModals();
                  setPermissionsOpen(true);
                }}
              />
              <ActionButton
                icon={ShieldAlert}
                label="Mark Suspicious"
                description="Flag risk level and category"
                onClick={() => {
                  resetModals();
                  setMarkSuspiciousOpen(true);
                }}
              />
              <ActionButton
                icon={BadgeAlert}
                label="Quick: Bad-faith disputes"
                description="Mark high risk for dispute abuse"
                onClick={() => {
                  resetModals();
                  setMarkLevel("high");
                  setMarkCategory("abuse");
                  setMarkSuspiciousOpen(true);
                }}
              />
              <ActionButton
                icon={RefreshCw}
                label="Send Password Reset"
                description="Dispatch reset code to contact"
                onClick={() => {
                  resetModals();
                  setPasswordResetOpen(true);
                }}
              />
              <ActionButton
                icon={Shield}
                label="Resend Verification"
                description="Choose email or phone"
                onClick={() => {
                  resetModals();
                  setResendChannels({ email: Boolean(hasEmail), phone: Boolean(hasPhone) });
                  setResendVerificationOpen(true);
                }}
                disabled={!hasEmail && !hasPhone}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Internal Notes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Textarea
                  id="note-text"
                  placeholder="Add an internal note..."
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                />
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <Input
                    id="note-tags"
                    placeholder="Tags (optional: vip, watch)"
                    value={noteTags}
                    onChange={(e) => setNoteTags(e.target.value)}
                  />
                  <Input
                    id="note-reason"
                    placeholder="Reason (required)"
                    value={noteReason}
                    onChange={(e) => setNoteReason(e.target.value)}
                  />
                </div>
                <div className="flex justify-end">
                  <Button
                    className="w-full sm:w-auto"
                    onClick={handleAddNote}
                    disabled={noteSubmitting || !noteText.trim() || !noteReason.trim()}
                  >
                    {noteSubmitting ? "Saving..." : "Add Note"}
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={suspendOpen} onOpenChange={setSuspendOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Suspend user</DialogTitle>
            <DialogDescription>
              Suspending immediately disables login and actions. Type CONFIRM to continue.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="confirm-text">Type CONFIRM</Label>
              <Input
                id="confirm-text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder="CONFIRM"
              />
            </div>
            <ReasonField value={reasonText} onChange={setReasonText} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSuspendOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleSuspend}
              disabled={actionLoading || confirmText.trim() !== "CONFIRM" || !reasonText.trim()}
            >
              {actionLoading ? "Working..." : "Suspend"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reinstateOpen} onOpenChange={setReinstateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reinstate user</DialogTitle>
            <DialogDescription>Restore access for this account.</DialogDescription>
          </DialogHeader>
          <ReasonField value={reasonText} onChange={setReasonText} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setReinstateOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleReinstate}
              disabled={actionLoading || !reasonText.trim()}
              variant="secondary"
            >
              {actionLoading ? "Working..." : "Reinstate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={permissionsOpen} onOpenChange={setPermissionsOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit permissions</DialogTitle>
            <DialogDescription>Toggle booking/listing capabilities for this user.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <ToggleRow
              label="Can Rent"
              description="Disables booking and rental requests when off."
              checked={permissionsForm.can_rent}
              onChange={(value) => setPermissionsForm((prev) => ({ ...prev, can_rent: value }))}
            />
            <ToggleRow
              label="Can List"
              description="Prevents creating or managing listings when off."
              checked={permissionsForm.can_list}
              onChange={(value) => setPermissionsForm((prev) => ({ ...prev, can_list: value }))}
            />
            <ReasonField value={restrictionsReason} onChange={setRestrictionsReason} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPermissionsOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSetRestrictions}
              disabled={actionLoading || !restrictionsReason.trim()}
            >
              {actionLoading ? "Working..." : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={markSuspiciousOpen} onOpenChange={setMarkSuspiciousOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Mark suspicious</DialogTitle>
            <DialogDescription>Flag this user with a risk level and category.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>Level</Label>
                <Select value={markLevel} onValueChange={setMarkLevel}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select level" />
                  </SelectTrigger>
                  <SelectContent>
                    {levelOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label>Category</Label>
                <Select value={markCategory} onValueChange={setMarkCategory}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select category" />
                  </SelectTrigger>
                  <SelectContent>
                    {categoryOptions.map((opt) => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="mark-note">Internal note</Label>
              <Textarea
                id="mark-note"
                placeholder="Context for this flag (optional)"
                value={markNote}
                onChange={(e) => setMarkNote(e.target.value)}
              />
            </div>
            <ReasonField value={markReason} onChange={setMarkReason} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setMarkSuspiciousOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleMarkSuspicious} disabled={actionLoading || !markReason.trim()}>
              {actionLoading ? "Working..." : "Save flag"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={passwordResetOpen} onOpenChange={setPasswordResetOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Send password reset</DialogTitle>
            <DialogDescription>
              Send a reset code to the user&apos;s primary contact. This action will be audited.
            </DialogDescription>
          </DialogHeader>
          <ReasonField value={passwordResetReason} onChange={setPasswordResetReason} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setPasswordResetOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handlePasswordReset}
              disabled={actionLoading || !passwordResetReason.trim()}
            >
              {actionLoading ? "Working..." : "Send reset"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={resendVerificationOpen} onOpenChange={setResendVerificationOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resend verification</DialogTitle>
            <DialogDescription>Send verification codes to the selected channels.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              {hasEmail ? (
                <ChannelToggle
                  label={`Email (${user.email})`}
                  checked={resendChannels.email}
                  onChange={(checked) =>
                    setResendChannels((prev) => ({
                      ...prev,
                      email: checked,
                    }))
                  }
                />
              ) : null}
              {hasPhone ? (
                <ChannelToggle
                  label={`Phone (${user.phone})`}
                  checked={resendChannels.phone}
                  onChange={(checked) =>
                    setResendChannels((prev) => ({
                      ...prev,
                      phone: checked,
                    }))
                  }
                />
              ) : null}
              {!hasEmail && !hasPhone ? (
                <p className="text-sm text-muted-foreground">No contact methods available.</p>
              ) : null}
            </div>
            <ReasonField value={resendReason} onChange={setResendReason} />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResendVerificationOpen(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleResendVerification}
              disabled={
                actionLoading ||
                !resendReason.trim() ||
                (!resendChannels.email && !resendChannels.phone)
              }
            >
              {actionLoading ? "Working..." : "Send"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function ContactRow({
  icon: Icon,
  label,
  value,
  onCopy,
}: {
  icon: React.ElementType;
  label: string;
  value: string | null;
  onCopy?: () => void;
}) {
  return (
    <div className="flex items-start gap-3">
      <Icon className="w-5 h-5 text-muted-foreground mt-0.5" />
      <div className="flex-1">
        <div className="text-sm text-muted-foreground mb-1">{label}</div>
        <div className="flex items-center gap-2">
          <span>{value ?? "—"}</span>
          {value && onCopy ? (
            <Button variant="outline" size="sm" onClick={onCopy}>
              Copy
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function PermissionItem({ label, enabled }: { label: string; enabled: boolean }) {
  return (
    <div>
      <div className="text-sm text-muted-foreground mb-1">{label}</div>
      <div className="flex items-center gap-2">
        {enabled ? (
          <>
            <CheckCircle2 className="w-5 h-5 text-[var(--success-solid)]" />
            <span>Enabled</span>
          </>
        ) : (
          <>
            <XCircle className="w-5 h-5 text-destructive" />
            <span>Disabled</span>
          </>
        )}
      </div>
    </div>
  );
}

function VerificationItem({ icon: Icon, label, verified }: { icon: React.ElementType; label: string; verified: boolean }) {
  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
      <div className="flex items-center gap-3">
        <Icon className="w-5 h-5 text-muted-foreground" />
        <span>{label}</span>
      </div>
      {verified ? (
        <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 border border-emerald-100">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Verified
        </Badge>
      ) : (
        <Badge variant="secondary" className="bg-muted">
          <XCircle className="w-3 h-3 mr-1" />
          Not Verified
        </Badge>
      )}
    </div>
  );
}

function FinanceStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="h-full">
      <CardContent className="p-4 space-y-1">
        <div className="text-sm text-muted-foreground">{label}</div>
        <div className="text-2xl font-semibold">{value}</div>
        {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}

function NoteCard({ note }: { note: OperatorNote }) {
  const created = note.created_at ? new Date(note.created_at) : null;
  const authorLabel = note.author?.name || note.author?.email || `User ${note.author?.id ?? ""}` || "Unknown";
  const timestamp = created ? formatDistanceToNow(created, { addSuffix: true }) : "";
  return (
    <div className="p-4 rounded-lg border border-border bg-muted/40">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-2">
          <div className="text-sm text-muted-foreground">
            {authorLabel} {timestamp ? `• ${timestamp}` : ""}
          </div>
          <p className="m-0 whitespace-pre-wrap">{note.text}</p>
          {note.tags?.length ? (
            <div className="flex flex-wrap gap-2">
              {note.tags.map((tag) => (
                <Badge key={tag} variant="outline" className="text-xs">
                  {tag}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ActionButton({
  icon: Icon,
  label,
  description,
  onClick,
  variant = "outline",
  disabled,
}: {
  icon: React.ElementType;
  label: string;
  description: string;
  onClick: () => void;
  variant?: "outline" | "secondary" | "destructive";
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full text-left flex items-center gap-3 rounded-lg border px-3 py-3 transition shadow-sm ${
        variant === "destructive"
          ? "border-destructive/50 bg-destructive/15 text-destructive hover:bg-destructive/25 hover:border-destructive/60"
          : variant === "secondary"
            ? "border-border bg-muted hover:bg-muted/80"
            : "border-border bg-muted/40 hover:bg-muted/60"
      } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
    >
      <Icon className="w-5 h-5" />
      <div className="flex-1">
        <div className="font-medium">{label}</div>
        <div className="text-sm text-muted-foreground">{description}</div>
      </div>
    </button>
  );
}

function ReasonField({ value, onChange }: { value: string; onChange: (val: string) => void }) {
  return (
    <div className="space-y-1">
      <Label htmlFor="reason">Reason (required)</Label>
      <Textarea
        id="reason"
        placeholder="Share the rationale. This will be logged."
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      <p className="text-xs text-muted-foreground">Keep it concise; 200–500 characters recommended.</p>
    </div>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-lg border border-border p-3">
      <div>
        <div className="font-medium">{label}</div>
        <p className="text-sm text-muted-foreground m-0">{description}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

function ChannelToggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
      <span>{label}</span>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  );
}

function UserDetailSkeleton({ onBack }: { onBack: () => void }) {
  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={onBack}>
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Users
      </Button>
      <div className="grid gap-6 xl:grid-cols-[2fr_1fr] items-start">
        <div className="space-y-6">
          <Card>
            <CardContent className="p-6 flex flex-wrap items-center gap-6">
              <Skeleton className="w-20 h-20 rounded-full" />
              <div className="flex-1 min-w-[240px] space-y-3">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-4 w-32" />
                <div className="flex gap-2 flex-wrap">
                  <Skeleton className="h-6 w-20" />
                  <Skeleton className="h-6 w-20" />
                </div>
                <div className="flex gap-2 flex-wrap">
                  <Skeleton className="h-8 w-32" />
                  <Skeleton className="h-8 w-36" />
                </div>
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-6 md:grid-cols-2">
            <Card className="h-full">
              <CardHeader>
                <Skeleton className="h-5 w-40" />
              </CardHeader>
              <CardContent className="space-y-4">
                {Array.from({ length: 4 }).map((_, idx) => (
                  <div key={idx} className="flex items-center gap-3">
                    <Skeleton className="h-5 w-5 rounded-full" />
                    <div className="flex-1 space-y-2">
                      <Skeleton className="h-3 w-24" />
                      <Skeleton className="h-4 w-32" />
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
            <Card className="h-full">
              <CardHeader>
                <Skeleton className="h-5 w-40" />
              </CardHeader>
              <CardContent className="space-y-3">
                {Array.from({ length: 3 }).map((_, idx) => (
                  <Skeleton key={idx} className="h-12 w-full" />
                ))}
                <div className="grid grid-cols-2 gap-4 pt-2">
                  <Skeleton className="h-4 w-24" />
                  <Skeleton className="h-4 w-24" />
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-24" />
            </CardHeader>
            <CardContent className="space-y-4">
              <Skeleton className="h-10 w-full" />
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, idx) => (
                  <Skeleton key={idx} className="h-16 w-full rounded-lg" />
                ))}
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-32" />
            </CardHeader>
            <CardContent className="space-y-3">
              {Array.from({ length: 6 }).map((_, idx) => (
                <Skeleton key={idx} className="h-12 w-full rounded-lg" />
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <Skeleton className="h-5 w-32" />
            </CardHeader>
            <CardContent className="space-y-3">
              {Array.from({ length: 2 }).map((_, idx) => (
                <Skeleton key={idx} className="h-16 w-full rounded-lg" />
              ))}
              <Skeleton className="h-20 w-full" />
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
              <Skeleton className="h-10 w-32" />
            </CardContent>
          </Card>
        </div>
      </div>

    </div>
  );
}

function extractErrorMessage(err: any, fallback: string) {
  if (typeof err === "string") return err;
  const detail = err?.data?.detail || err?.message;
  if (Array.isArray(detail)) return detail.join(" ");
  if (detail) return String(detail);
  return fallback;
}
