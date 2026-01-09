import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Star } from "lucide-react";
import { toast } from "sonner";
import { reviewsAPI, type Review, type ReviewRole } from "@/lib/api";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";

interface ReviewModalProps {
  open: boolean;
  role: ReviewRole;
  bookingId: number;
  otherPartyName: string;
  onClose: () => void;
  onSubmitted?: (review: Review) => void;
  onViewProfile?: () => void;
  viewProfileLabel?: string;
  viewProfileHref?: string;
}

const roleHeading: Record<ReviewRole, string> = {
  owner_to_renter: "Rate your renter",
  renter_to_owner: "Rate the owner",
};

export function ReviewModal({
  open,
  role,
  bookingId,
  otherPartyName,
  onClose,
  onSubmitted,
  onViewProfile,
  viewProfileLabel = "View profile",
  viewProfileHref,
}: ReviewModalProps) {
  const [rating, setRating] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const heading = useMemo(() => roleHeading[role] ?? "Leave a review", [role]);

  useEffect(() => {
    if (open) {
      setRating(null);
      setText("");
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  const toggleRating = (value: number) => {
    setRating((current) => (current === value ? null : value));
  };

  const handleSubmit = async () => {
    if (!bookingId) {
      setError("Booking is required.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        booking: bookingId,
        role,
        rating: rating ?? null,
        text: text.trim() || undefined,
      };
      const review = await reviewsAPI.create(body);
      toast.success("Review submitted. Thank you!");
      if (onSubmitted) {
        onSubmitted(review);
      }
      onClose();
    } catch (err) {
      let message = "Could not submit your review. Please try again.";
      if (err && typeof err === "object" && "data" in err) {
        const data = (err as { data?: unknown }).data;
        if (data && typeof data === "object" && "detail" in data) {
          const detail = (data as Record<string, unknown>).detail;
          if (typeof detail === "string") {
            message = detail;
          }
        }
      }
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleViewProfile = () => {
    if (submitting) return;
    if (onViewProfile) {
      onViewProfile();
    }
  };

  const viewProfileDisabled = submitting;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next && !submitting) {
          onClose();
        }
      }}
    >
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{heading}</DialogTitle>
          <DialogDescription>
            {role === "owner_to_renter"
              ? `How was your experience with ${otherPartyName}?`
              : `Share how the rental went with ${otherPartyName}.`}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-5 py-2">
          <div className="space-y-2">
            <Label>Rating (optional)</Label>
            <div className="flex items-center gap-2">
              {Array.from({ length: 5 }).map((_, index) => {
                const value = index + 1;
                const active = rating !== null && rating >= value;
                return (
                  <button
                    key={value}
                    type="button"
                    className="flex items-center justify-center w-10 h-10 rounded-full border border-border hover:border-primary transition-colors"
                    onClick={() => toggleRating(value)}
                    aria-label={`Rate ${value} star${value === 1 ? "" : "s"}`}
                  >
                    <Star
                      className={`w-5 h-5 ${
                        active ? "text-yellow-500 fill-yellow-500" : "text-muted-foreground"
                      }`}
                    />
                  </button>
                );
              })}
            </div>
            <p className="text-xs text-muted-foreground">
              Tap a star to set your rating. Tap again to clear.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="review-text">Share optional feedback</Label>
            <Textarea
              id="review-text"
              placeholder="Anything the other party should know for next time?"
              value={text}
              onChange={(event) => setText(event.target.value)}
              maxLength={1200}
            />
            <p className="text-xs text-muted-foreground">{text.length}/1200</p>
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter className="gap-2">
          {onViewProfile || viewProfileHref ? (
            viewProfileHref ? (
              <Button
                variant="outline"
                asChild
                className={viewProfileDisabled ? "pointer-events-none opacity-50" : undefined}
                onClick={handleViewProfile}
              >
                <Link to={viewProfileHref} reloadDocument>
                  {viewProfileLabel}
                </Link>
              </Button>
            ) : (
              <Button
                variant="outline"
                onClick={handleViewProfile}
                disabled={viewProfileDisabled}
              >
                {viewProfileLabel}
              </Button>
            )
          ) : null}
          <Button
            variant="outline"
            onClick={() => {
              if (!submitting) {
                onClose();
              }
            }}
            disabled={submitting}
          >
            Skip
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Submitting..." : "Submit review"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
