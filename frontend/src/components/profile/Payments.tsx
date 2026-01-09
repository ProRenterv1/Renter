import { useEffect, useMemo, useState } from "react";
import { CardElement, useElements, useStripe } from "@stripe/react-stripe-js";
import { CreditCard, Plus, Building2, Loader2 } from "lucide-react";
import { toast } from "sonner";

import {
  paymentsAPI,
  type InstantPayoutResponse,
  type PaymentMethod,
  type OwnerPayoutHistoryRow,
  type OwnerPayoutSummary,
  type JsonError,
} from "@/lib/api";
import { formatCurrency } from "@/lib/utils";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Separator } from "../ui/separator";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Alert, AlertDescription } from "../ui/alert";
import { Skeleton } from "../ui/skeleton";
import { Checkbox } from "../ui/checkbox";

export function Payments() {
  const [paymentMethods, setPaymentMethods] = useState<PaymentMethod[]>([]);
  const [history, setHistory] = useState<OwnerPayoutHistoryRow[]>([]);
  const [summary, setSummary] = useState<OwnerPayoutSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const stripe = useStripe();
  const elements = useElements();

  const [addCardOpen, setAddCardOpen] = useState(false);
  const [cardholderName, setCardholderName] = useState("");
  const [cardError, setCardError] = useState<string | null>(null);
  const [addingCard, setAddingCard] = useState(false);

  const [bankDialogOpen, setBankDialogOpen] = useState(false);
  const [bankForm, setBankForm] = useState({
    transit_number: "",
    institution_number: "",
    account_number: "",
  });
  const [bankErrors, setBankErrors] = useState<Record<string, string>>({});
  const [savingBank, setSavingBank] = useState(false);
  const [instantOpen, setInstantOpen] = useState(false);
  const [instantLoading, setInstantLoading] = useState(false);
  const [instantError, setInstantError] = useState<string | null>(null);
  const [instantAgree, setInstantAgree] = useState(false);
  const [instantQuote, setInstantQuote] = useState<InstantPayoutResponse | null>(null);
  const [startingOnboarding, setStartingOnboarding] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [methods, summaryRes, historyRes] = await Promise.all([
          paymentsAPI.listPaymentMethods(),
          paymentsAPI.ownerPayoutsSummary(),
          paymentsAPI.ownerPayoutsHistory({ limit: 50, scope: "all" }),
        ]);
        if (cancelled) return;
        setPaymentMethods(methods);
        setSummary(summaryRes);
        setHistory(historyRes.results ?? []);
        setBankForm({
          transit_number: summaryRes?.connect?.bank_details?.transit_number ?? "",
          institution_number: summaryRes?.connect?.bank_details?.institution_number ?? "",
          account_number: "",
        });
      } catch (err) {
        if (!cancelled) {
          setError("Unable to load payments right now.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSetDefault = async (methodId: number) => {
    try {
      const updated = await paymentsAPI.setDefaultPaymentMethod(methodId);
      setPaymentMethods((prev) =>
        prev.map((pm) => ({
          ...pm,
          is_default: pm.id === updated.id,
        })),
      );
      toast.success("Default payment method updated.");
    } catch {
      toast.error("Could not update default card. Please try again.");
    }
  };

  const handleRemove = async (methodId: number) => {
    try {
      await paymentsAPI.removePaymentMethod(methodId);
      setPaymentMethods((prev) => prev.filter((pm) => pm.id !== methodId));
      toast.success("Card removed.");
    } catch {
      toast.error("Unable to remove this card right now.");
    }
  };

  const handleAddCard = async () => {
    if (!stripe || !elements) {
      toast.error("Payment form is still loading. Please try again.");
      return;
    }
    const cardElement = elements.getElement(CardElement);
    if (!cardElement) {
      toast.error("Payment form is not ready. Please refresh and try again.");
      return;
    }
    setCardError(null);
    setAddingCard(true);
    try {
      const setupIntent = await paymentsAPI.createPaymentMethodSetupIntent({
        intent_type: "default_card",
      });
      const { error, setupIntent: confirmed } = await stripe.confirmCardSetup(
        setupIntent.client_secret,
        {
          payment_method: {
            card: cardElement,
            billing_details: {
              name: cardholderName || undefined,
            },
          },
          expand: ["payment_method"],
        },
      );

      if (error || !confirmed) {
        setCardError(error?.message || "We couldn't verify your card. Please try again.");
        setAddingCard(false);
        return;
      }

      const pmId =
        typeof confirmed.payment_method === "string"
          ? confirmed.payment_method
          : confirmed.payment_method?.id;
      const cardDetails =
        confirmed && typeof confirmed.payment_method === "object"
          ? (confirmed.payment_method as any).card
          : undefined;
      if (!pmId) {
        setCardError("We couldn't verify your card. Please try again.");
        setAddingCard(false);
        return;
      }

      const created = await paymentsAPI.addPaymentMethod({
        stripe_payment_method_id: pmId,
        stripe_setup_intent_id: confirmed.id,
        setup_intent_status: confirmed.status,
        card_brand: cardDetails?.brand,
        card_last4: cardDetails?.last4,
        card_exp_month: cardDetails?.exp_month ?? null,
        card_exp_year: cardDetails?.exp_year ?? null,
      });
      setPaymentMethods((prev) => [created, ...prev]);
      setCardholderName("");
      cardElement.clear();
      setAddCardOpen(false);
      toast.success("Card added.");
    } catch (err) {
      console.error("payments: add card failed", err);
      setCardError("Unable to add this card. Please try again in a moment.");
    } finally {
      setAddingCard(false);
    }
  };

  const connect = summary?.connect;
  const bankDetails = connect?.bank_details;
  const hasConnectAccount = connect?.has_account;
  const canStartOnboarding = !loading && (connect ? !connect.is_fully_onboarded : true);

  const handleBankSubmit = async () => {
    setSavingBank(true);
    setBankErrors({});
    try {
      const updated = await paymentsAPI.updateBankDetails(bankForm);
      setSummary(updated);
      setBankDialogOpen(false);
      setBankForm((prev) => ({
        ...prev,
        account_number: "",
      }));
      toast.success("Bank details updated.");
    } catch (err) {
      let detailMessage: string | null = null;
      if (err && typeof err === "object" && "data" in err) {
        const data = (err as JsonError).data as any;
        if (data && typeof data === "object" && !Array.isArray(data)) {
          const fieldMessages: Record<string, string> = {};
          for (const key of ["transit_number", "institution_number", "account_number"]) {
            const value = (data as Record<string, unknown>)[key];
            if (Array.isArray(value) && value.length) {
              fieldMessages[key] = String(value[0]);
              if (!detailMessage) {
                detailMessage = fieldMessages[key];
              }
            }
          }
          if (Object.keys(fieldMessages).length) {
            setBankErrors(fieldMessages);
          }
          const possibleDetail = (data as Record<string, unknown>).detail;
          if (typeof possibleDetail === "string") {
            detailMessage = possibleDetail;
          }
        }
      }
      toast.error(detailMessage || "Unable to save bank details right now.");
    } finally {
      setSavingBank(false);
    }
  };

  const handleOpenInstantPayout = async () => {
    setInstantOpen(true);
    setInstantLoading(true);
    setInstantError(null);
    setInstantAgree(false);
    setInstantQuote(null);

    try {
      const quote = await paymentsAPI.instantPayoutPreview();
      setInstantQuote(quote);
    } catch (err: any) {
      const detail =
        err?.data?.detail ??
        err?.response?.data?.detail ??
        "Unable to calculate instant payout right now.";
      setInstantError(detail);
    } finally {
      setInstantLoading(false);
    }
  };

  const handleConfirmInstantPayout = async () => {
    if (!instantAgree || instantLoading) return;

    setInstantLoading(true);
    setInstantError(null);

    try {
      const res = await paymentsAPI.instantPayoutExecute();
      setInstantQuote(res);

      toast.success("Instant payout initiated", {
        description: "Your payout has been submitted successfully.",
      });

      setInstantOpen(false);
      setInstantAgree(false);

      // Optional: refresh summary/history so balances update
      // await reloadPaymentsData();
    } catch (err: any) {
      const detail =
        err?.data?.detail ??
        err?.response?.data?.detail ??
        "Instant payout failed. Please try again later.";
      setInstantError(detail);
    } finally {
      setInstantLoading(false);
    }
  };

  const handleStartOnboarding = async () => {
    setStartingOnboarding(true);
    try {
      const response = await paymentsAPI.ownerPayoutsStartOnboarding();
      if (!response.onboarding_url) {
        toast.error("Unable to start verification right now.");
        return;
      }
      window.location.href = response.onboarding_url;
    } catch (err) {
      let detail: string | null = null;
      if (err && typeof err === "object" && "data" in err) {
        const data = (err as JsonError).data as Record<string, unknown>;
        if (data && typeof data.detail === "string") {
          detail = data.detail;
        }
      }
      toast.error(detail || "Unable to start verification right now.");
    } finally {
      setStartingOnboarding(false);
    }
  };

  const transactions = useMemo(() => {
    return history
      .filter((txn) => {
        if (txn.kind === "DAMAGE_DEPOSIT_CAPTURE") {
          return false;
        }
        if (txn.kind === "PLATFORM_FEE" && !txn.booking_id) {
          return false;
        }
        return true;
      })
      .map((txn) => {
        const date = txn.created_at
          ? new Date(txn.created_at).toLocaleDateString(undefined, {
              year: "numeric",
              month: "short",
              day: "numeric",
            })
          : "";

        let description = txn.kind;
        const isPayout =
          txn.kind === "OWNER_PAYOUT" ||
          (txn.kind === "OWNER_EARNING" && txn.direction === "debit" && !txn.booking_id);
        if (txn.kind === "BOOKING_CHARGE") {
          description = txn.listing_title
            ? `Booking charge – ${txn.listing_title}`
            : "Booking charge";
        } else if (isPayout) {
          description = "Payout";
        } else if (txn.kind === "OWNER_EARNING" && txn.listing_title) {
          description = `Owner earning – ${txn.listing_title}`;
        } else if (txn.kind === "OWNER_EARNING") {
          description = "Owner earning";
        } else if (txn.kind === "REFUND") {
          description = "Refund";
        } else if (txn.kind === "DAMAGE_DEPOSIT_CAPTURE") {
          description = "Deposit captured";
        } else if (txn.kind === "DAMAGE_DEPOSIT_RELEASE") {
          description = "Deposit released";
        } else if (txn.kind === "PROMOTION_CHARGE") {
          description = "Promotion payment";
        }

        const amountNumber = Math.abs(Number(txn.amount || "0"));
        const signed = txn.direction === "debit" ? -amountNumber : amountNumber;

        return {
          id: txn.id,
          date,
          description,
          status: "Completed",
          amount: signed,
          currency: (txn.currency || "").toUpperCase(),
        };
      });
  }, [history]);

  const renderPaymentMethods = () => {
    if (loading) {
      return (
        <div className="space-y-4">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      );
    }
    if (!paymentMethods.length) {
      return <p style={{ color: "var(--text-muted)" }}>No saved cards yet.</p>;
    }
    return paymentMethods.map((method, index) => (
      <div key={method.id}>
        {index > 0 && <Separator className="my-4" />}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center">
              <CreditCard className="w-6 h-6" style={{ color: "var(--text-muted)" }} />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <p>
                  {method.brand} ending in {method.last4}
                </p>
                {method.is_default && (
                  <Badge variant="secondary" className="text-xs">
                    Default
                  </Badge>
                )}
              </div>
              <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                Expires {String(method.exp_month || "").padStart(2, "0")}/{method.exp_year || "--"}
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            {!method.is_default && (
              <Button variant="ghost" size="sm" onClick={() => handleSetDefault(method.id)}>
                Set as Default
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              className="text-destructive"
              onClick={() => handleRemove(method.id)}
            >
              Remove
            </Button>
          </div>
        </div>
      </div>
    ));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Payments</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Manage payment methods and view transaction history
        </p>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Payment Methods */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Payment Methods</CardTitle>
            <CardDescription>Manage your saved payment methods</CardDescription>
          </div>
          <Button
            size="sm"
            className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
            style={{ color: "var(--primary-foreground)" }}
            onClick={() => setAddCardOpen(true)}
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Card
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {renderPaymentMethods()}
        </CardContent>
      </Card>

      {/* Payout Method */}
      <Card>
        <CardHeader>
          <CardTitle>Payout Method</CardTitle>
          <CardDescription>Where you receive your earnings</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center">
                <Building2 className="w-6 h-6" style={{ color: "var(--text-muted)" }} />
              </div>
              <div>
                <p>Bank Account</p>
                {loading ? (
                  <Skeleton className="h-4 w-48 mt-2" />
                ) : !hasConnectAccount ? (
                  <div className="text-sm mt-1 space-y-1 text-yellow-700">
                    <p>Start Stripe verification to enable payouts.</p>
                    <p className="text-xs text-muted-foreground">
                      You don&apos;t need to add bank details here first—Stripe will ask for them
                      during verification or you can add them later.
                    </p>
                  </div>
                ) : bankDetails && bankDetails.account_last4 ? (
                  <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                    Transit {bankDetails.transit_number}, Institution {bankDetails.institution_number}
                    , Account ending in {bankDetails.account_last4 || "--"}
                  </p>
                ) : (
                  <div className="text-sm mt-1 space-y-1" style={{ color: "var(--text-muted)" }}>
                    <p>No bank account on file yet.</p>
                    <p className="text-xs text-muted-foreground">
                      You can complete Stripe verification first and add payout details there or here
                      later.
                    </p>
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2 flex-wrap justify-end">
              {canStartOnboarding && (
                <Button
                  size="sm"
                  className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                  style={{ color: "var(--primary-foreground)" }}
                  onClick={handleStartOnboarding}
                  disabled={startingOnboarding}
                >
                  {startingOnboarding ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Starting verification...
                    </>
                  ) : (
                    "Start verification"
                  )}
                </Button>
              )}
              <Button variant="outline" size="sm" onClick={() => setBankDialogOpen(true)}>
                Update
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleOpenInstantPayout}
                disabled={!hasConnectAccount || !bankDetails}
              >
                Instant payout
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Transaction History */}
      <Card>
        <CardHeader>
          <CardTitle>Transaction History</CardTitle>
          <CardDescription>Your recent payment activity</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Transaction ID</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={5}>
                    <div className="flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span>Loading payments...</span>
                    </div>
                  </TableCell>
                </TableRow>
              ) : transactions.length ? (
                transactions.map((txn) => (
                  <TableRow key={txn.id}>
                    <TableCell className="font-mono text-sm">{txn.id}</TableCell>
                    <TableCell>{txn.date}</TableCell>
                    <TableCell>{txn.description}</TableCell>
                <TableCell>
                  <Badge variant="secondary">{txn.status}</Badge>
                </TableCell>
                <TableCell className="text-right">
                  <span
                    className={
                      txn.amount > 0 ? "text-green-600" : txn.amount < 0 ? "text-destructive" : ""
                    }
                  >
                    {txn.amount > 0 ? "+" : ""}
                    {formatCurrency(Math.abs(txn.amount), txn.currency || "CAD")}
                  </span>
                </TableCell>
              </TableRow>
            ))
              ) : (
                <TableRow>
                  <TableCell colSpan={5} className="text-center" style={{ color: "var(--text-muted)" }}>
                    No transactions yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Dialog open={addCardOpen} onOpenChange={(open) => {
        setAddCardOpen(open);
        if (!open) {
          setCardError(null);
          setCardholderName("");
        }
      }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add payment method</DialogTitle>
            <DialogDescription>
              Enter your card details. We will create a Stripe payment method and attach it to your account.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="cardholder_name">Cardholder name</Label>
              <Input
                id="cardholder_name"
                placeholder="Name on card"
                value={cardholderName}
                onChange={(e) => setCardholderName(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label>Card details</Label>
              <div className="rounded-md border p-3">
                <CardElement
                  options={{
                    hidePostalCode: true,
                    style: {
                      base: {
                        color: "var(--foreground)",
                        fontFamily: "Manrope, system-ui, sans-serif",
                        fontSize: "16px",
                        "::placeholder": {
                          color: "var(--muted-foreground)",
                        },
                      },
                      invalid: {
                        color: "#ef4444",
                      },
                    },
                  }}
                />
              </div>
              {cardError && (
                <p className="text-sm text-destructive" role="alert">
                  {cardError}
                </p>
              )}
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setAddCardOpen(false)} disabled={addingCard}>
              Cancel
            </Button>
            <Button onClick={handleAddCard} disabled={addingCard}>
              {addingCard && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Save card
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={bankDialogOpen} onOpenChange={setBankDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Update bank details</DialogTitle>
            <DialogDescription>
              Enter your Canadian bank info to receive payouts. Values are stored securely.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="transit_number">Transit number</Label>
              <Input
                id="transit_number"
                value={bankForm.transit_number}
                onChange={(e) => setBankForm((prev) => ({ ...prev, transit_number: e.target.value }))}
              />
              {bankErrors.transit_number && (
                <p className="text-xs text-red-600">{bankErrors.transit_number}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="institution_number">Institution number</Label>
              <Input
                id="institution_number"
                value={bankForm.institution_number}
                onChange={(e) =>
                  setBankForm((prev) => ({ ...prev, institution_number: e.target.value }))
                }
              />
              {bankErrors.institution_number && (
                <p className="text-xs text-red-600">{bankErrors.institution_number}</p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="account_number">Account number</Label>
              <Input
                id="account_number"
                value={bankForm.account_number}
                onChange={(e) => setBankForm((prev) => ({ ...prev, account_number: e.target.value }))}
              />
              {bankErrors.account_number && (
                <p className="text-xs text-red-600">{bankErrors.account_number}</p>
              )}
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setBankDialogOpen(false)} disabled={savingBank}>
              Cancel
            </Button>
            <Button onClick={handleBankSubmit} disabled={savingBank}>
              {savingBank && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
              Save details
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={instantOpen}
        onOpenChange={(open) => {
          setInstantOpen(open);
          if (!open) {
            setInstantError(null);
            setInstantAgree(false);
            setInstantQuote(null);
            setInstantLoading(false);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Instant payout</DialogTitle>
            <DialogDescription>
              Get your earnings sent to your bank account right away. An instant payout fee will be
              applied.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3 mt-3">
            {instantLoading && (
              <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                Calculating your available amount...
              </p>
            )}

            {instantError && <p className="text-sm text-red-600">{instantError}</p>}

            {instantQuote && !instantLoading && !instantError && (
              <>
                <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                  You&apos;ll receive:
                </p>
                <p className="text-2xl font-semibold">
                  {new Intl.NumberFormat(undefined, {
                    style: "currency",
                    currency: instantQuote.currency.toUpperCase(),
                  }).format(Number(instantQuote.amount_after_fee))}
                </p>
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  The payout will be sent to your current payout bank account.
                </p>
              </>
            )}

            <div className="flex items-start gap-2 pt-2">
              <Checkbox
                id="instant-agree"
                checked={instantAgree}
                onCheckedChange={(checked) => setInstantAgree(Boolean(checked))}
              />
              <label htmlFor="instant-agree" className="text-sm leading-relaxed">
                I understand that a fee is charged for instant payouts and agree to proceed with this
                payout.
              </label>
            </div>
          </div>

          <DialogFooter className="mt-4">
            <Button variant="outline" type="button" onClick={() => setInstantOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handleConfirmInstantPayout}
              disabled={!instantAgree || instantLoading || !!instantError || !instantQuote}
            >
              {instantLoading ? "Processing..." : "Confirm payout"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
