import { createPortal } from "react-dom";
import type { ReactNode } from "react";
import { Button } from "./ui/button";
import { Checkbox } from "./ui/checkbox";

type PolicyConfirmationModalProps = {
  open: boolean;
  title?: string;
  roleLabel: "owner" | "renter";
  checkboxChecked: boolean;
  onCheckboxChange: (checked: boolean) => void;
  onConfirm: () => void;
  onCancel: () => void;
  confirmDisabled?: boolean;
};

const checkboxLabels: Record<PolicyConfirmationModalProps["roleLabel"], string> = {
  owner: "I understand how cancellations, late returns and deposit capture work for this booking.",
  renter: "I understand the cancellation, late return and deposit rules for this booking.",
};

const policySections: Array<{ title: string; bullets: ReactNode[] }> = [
  {
    title: "Cancellation rules (renter)",
    bullets: [
      "Free cancellation (>= 1 full day before start): Full refund of rental, service fee and deposit. Owner gets no payout, platform takes no fee.",
      "Late cancellation (~24h before start): You pay 1 rental day + service fee on that 1 day. Remaining days and full deposit are refunded.",
      "Same-day / no-show (day of start or later): You are charged 50% of rental subtotal + 50% of service fee. The full damage deposit is refunded if the tool never left the owner.",
    ],
  },
  {
    title: "Cancellation rules (owner)",
    bullets: [
      "If you cancel any time after payment but before pickup: renter gets a full refund of rental, service fee and deposit.",
      "You get no payout for a booking you cancel after payment.",
      'The platform refunds its service fee and may count an internal "strike" against your account.',
    ],
  },
  {
    title: "Late return & not returned (after end date)",
    bullets: [
      "If the tool is returned 1-2 days late, the system may charge extra rental (up to 2 extra days x daily price) plus service fee on that extra rental.",
      'If the tool is not returned well after end date: the owner can mark it as "not returned" and part or all of the damage deposit may be captured and kept as compensation.',
    ],
  },
];
export function PolicyConfirmationModal({
  open,
  title = "Review cancellation & late-return policy",
  roleLabel,
  checkboxChecked,
  onCheckboxChange,
  onConfirm,
  onCancel,
  confirmDisabled = false,
}: PolicyConfirmationModalProps) {
  if (!open) {
    return null;
  }

  return createPortal(
    <div className="fixed inset-0 z-[120] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onCancel} />
      <div className="relative z-10 w-full max-w-2xl rounded-2xl bg-white p-6 shadow-2xl">
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Before continuing, please review how cancellations, late returns, and damage deposits are
          handled on Kitoro.
        </p>

        <div className="mt-4 max-h-72 overflow-y-auto rounded-2xl border border-[#F3D2A8] bg-[#FFF3E3] p-4 text-sm leading-relaxed text-slate-800">
          {policySections.map((section) => (
            <div key={section.title} className="mb-4 last:mb-0">
              <p className="font-semibold text-slate-900">{section.title}</p>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {section.bullets.map((bullet, index) => (
                  <li key={index}>{bullet}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <label className="mt-4 flex items-start gap-3 text-sm text-slate-900">
          <Checkbox
            checked={checkboxChecked}
            onCheckedChange={(checked) => onCheckboxChange(Boolean(checked))}
            aria-label={checkboxLabels[roleLabel]}
          />
          <span>{checkboxLabels[roleLabel]}</span>
        </label>

        <div className="mt-6 flex flex-wrap justify-end gap-3">
          <Button variant="outline" onClick={onCancel}>
            Back
          </Button>
          <Button
            onClick={onConfirm}
            disabled={!checkboxChecked || confirmDisabled}
            className="min-w-[160px]"
          >
            Agree & continue
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
