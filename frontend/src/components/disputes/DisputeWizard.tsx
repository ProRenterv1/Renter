import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ImageIcon, Upload, VideoIcon, X } from "lucide-react";
import { toast } from "sonner";
import {
  disputesAPI,
  type DisputeCategory,
  type DisputeDamageFlowKind,
  type DisputeEvidenceCompletePayload,
  type PhotoPresignRequest,
} from "@/lib/api";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";

type WizardRole = "renter" | "owner";

interface IssueOption {
  key: string;
  title: string;
  description: string;
  category: DisputeCategory;
  damage_flow_kind?: DisputeDamageFlowKind;
}

interface EvidenceFile {
  file: File;
  previewUrl: string;
  kind: DisputeEvidenceCompletePayload["kind"];
}

export interface DisputeWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookingId: number | null;
  role: WizardRole;
  toolName?: string;
  rentalPeriodLabel?: string;
}

const detectKind = (file: File): DisputeEvidenceCompletePayload["kind"] => {
  if (file.type?.startsWith("video/")) {
    return "video";
  }
  if (file.type?.startsWith("image/")) {
    return "photo";
  }
  return "other";
};

const buildIssueOptions = (role: WizardRole): IssueOption[] => {
  if (role === "renter") {
    return [
      {
        key: "broke_during_use",
        title: "Tool broke during my use",
        description: "Something failed while I was using the tool.",
        category: "damage",
        damage_flow_kind: "broke_during_use",
      },
      {
        key: "something_else",
        title: "Something else",
        description: "Billing or other issues.",
        category: "damage",
        damage_flow_kind: "generic",
      },
    ];
  }
  return [
    {
      key: "owner_damage",
      title: "Damage",
      description: "Report damage or misuse during the rental.",
      category: "damage",
      damage_flow_kind: "generic",
    },
    {
      key: "owner_missing",
      title: "Missing item",
      description: "Parts or accessories not returned.",
      category: "missing_item",
      damage_flow_kind: "generic",
    },
    {
      key: "owner_charges",
      title: "Incorrect charges",
      description: "Dispute payments or adjustments.",
      category: "incorrect_charges",
      damage_flow_kind: "generic",
    },
  ];
};

const minDescriptionLength = 10;

export function DisputeWizard({
  open,
  onOpenChange,
  bookingId,
  role,
  toolName,
  rentalPeriodLabel,
}: DisputeWizardProps) {
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [selectedIssue, setSelectedIssue] = useState<IssueOption | null>(null);
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<EvidenceFile[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const options = useMemo(() => buildIssueOptions(role), [role]);

  useEffect(() => {
    if (!open) {
      files.forEach((item) => URL.revokeObjectURL(item.previewUrl));
      setFiles([]);
      setSelectedIssue(null);
      setDescription("");
      setStep(0);
      setSubmitting(false);
    }
  }, [open, files]);

  const photoCount = files.filter((item) => item.kind === "photo").length;
  const videoCount = files.filter((item) => item.kind === "video").length;

  const meetsEvidenceRequirement = useMemo(() => {
    if (!selectedIssue) {
      return false;
    }
    if (selectedIssue.damage_flow_kind === "broke_during_use") {
      return videoCount >= 1 || photoCount >= 2;
    }
    return files.length >= 1;
  }, [selectedIssue, files.length, photoCount, videoCount]);

  const handleFilesAdded = (fileList: FileList | File[]) => {
    const additions: EvidenceFile[] = [];
    Array.from(fileList).forEach((file) => {
      additions.push({
        file,
        previewUrl: URL.createObjectURL(file),
        kind: detectKind(file),
      });
    });
    setFiles((prev) => [...prev, ...additions]);
  };

  const removeFile = (index: number) => {
    setFiles((prev) => {
      const next = [...prev];
      const [removed] = next.splice(index, 1);
      if (removed) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return next;
    });
  };

  const handleSubmit = async () => {
    if (!bookingId || !selectedIssue || submitting) {
      return;
    }
    if (description.trim().length < minDescriptionLength) {
      toast.error("Please provide a bit more detail before submitting.");
      setStep(1);
      return;
    }
    if (!meetsEvidenceRequirement) {
      toast.error("Please attach the required evidence before submitting.");
      setStep(2);
      return;
    }

    setSubmitting(true);
    try {
      const dispute = await disputesAPI.create({
        booking: bookingId,
        category: selectedIssue.category,
        damage_flow_kind: selectedIssue.damage_flow_kind,
        description: description.trim(),
      });

      for (const item of files) {
        const presignPayload: PhotoPresignRequest = {
          filename: item.file.name,
          content_type: item.file.type || "application/octet-stream",
          size: item.file.size,
        };
        const presign = await disputesAPI.evidencePresign(dispute.id, presignPayload);
        const uploadHeaders: Record<string, string> = { ...presign.headers };
        if (item.file.type) {
          uploadHeaders["Content-Type"] = item.file.type;
        }
        const uploadResponse = await fetch(presign.upload_url, {
          method: "PUT",
          headers: uploadHeaders,
          body: item.file,
        });
        if (!uploadResponse.ok) {
          throw new Error("Upload failed. Please try again.");
        }
        const etagHeader =
          uploadResponse.headers.get("ETag") ?? uploadResponse.headers.get("etag") ?? "";
        const cleanEtag = etagHeader.replace(/"/g, "");

        const completePayload: DisputeEvidenceCompletePayload = {
          key: presign.key,
          filename: item.file.name,
          content_type: item.file.type || "application/octet-stream",
          size: item.file.size,
          etag: cleanEtag,
          kind: item.kind,
        };
        await disputesAPI.evidenceComplete(dispute.id, completePayload);
      }

      toast.success("Issue reported. Our team will review the dispute.");
      onOpenChange(false);
    } catch (err) {
      const message =
        err && typeof err === "object" && "status" in (err as any)
          ? "Could not file dispute. Please try again."
          : err instanceof Error
          ? err.message
          : "Could not file dispute. Please try again.";
      toast.error(message);
      setSubmitting(false);
    }
  };

  const canContinueIssue = Boolean(selectedIssue);
  const canContinueDetails = description.trim().length >= minDescriptionLength;
  const canSubmit = Boolean(bookingId && selectedIssue && canContinueDetails && meetsEvidenceRequirement);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!submitting) {
          onOpenChange(next);
        }
      }}
    >
      <DialogContent className="max-w-3xl space-y-4">
        <DialogHeader>
          <DialogTitle>Report an issue</DialogTitle>
          <DialogDescription>
            {toolName ? `Booking for ${toolName}` : "Share details about the issue."}
            {rentalPeriodLabel ? ` · ${rentalPeriodLabel}` : ""}
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Badge variant={step === 0 ? "default" : "outline"}>Issue</Badge>
          <span>→</span>
          <Badge variant={step === 1 ? "default" : "outline"}>Details</Badge>
          <span>→</span>
          <Badge variant={step === 2 ? "default" : "outline"}>Evidence</Badge>
        </div>

        {step === 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {options.map((option) => {
              const selected = selectedIssue?.key === option.key;
              return (
                <button
                  key={option.key}
                  type="button"
                  onClick={() => setSelectedIssue(option)}
                  className={`rounded-lg border p-4 text-left transition hover:border-primary ${
                    selected ? "border-primary bg-primary/5" : "border-border bg-card"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">{option.title}</span>
                    {selected && <Badge variant="default">Selected</Badge>}
                  </div>
                  <p className="mt-2 text-sm text-muted-foreground">{option.description}</p>
                  {option.damage_flow_kind === "broke_during_use" && role === "renter" && (
                    <div className="mt-3 flex items-center gap-2 text-sm text-amber-600">
                      <AlertTriangle className="h-4 w-4" />
                      <span>Requires clear photos or video showing what happened.</span>
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label htmlFor="dispute-description">What happened?</Label>
              <Textarea
                id="dispute-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Briefly describe what went wrong."
                rows={4}
              />
              <p className="text-xs text-muted-foreground">
                {description.trim().length < minDescriptionLength
                  ? `Add ${minDescriptionLength - description.trim().length} more characters.`
                  : "Looks good."}
              </p>
            </div>
            <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
              <AlertTriangle className="h-4 w-4" />
              Stop using the tool until the issue is resolved for safety reasons.
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <div className="rounded-md border border-dashed p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium">Upload evidence</p>
                  <p className="text-sm text-muted-foreground">
                    Photos or video of the issue. Drag-and-drop or select files.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <label
                    className="inline-flex cursor-pointer items-center gap-2 rounded-md border bg-background px-3 py-2 text-sm shadow-sm"
                  >
                    <Upload className="h-4 w-4" />
                    Add files
                    <input
                      type="file"
                      className="hidden"
                      multiple
                      accept="image/*,video/*"
                      onChange={(event) => {
                        if (event.target.files) {
                          handleFilesAdded(event.target.files);
                          event.target.value = "";
                        }
                      }}
                    />
                  </label>
                </div>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {files.map((item, index) => (
                  <div
                    key={item.previewUrl}
                    className="relative overflow-hidden rounded-md border bg-card shadow-sm"
                  >
                    <button
                      type="button"
                      onClick={() => removeFile(index)}
                      className="absolute right-2 top-2 rounded-full bg-background/80 p-1 text-muted-foreground transition hover:text-foreground"
                    >
                      <X className="h-4 w-4" />
                    </button>
                    <div className="h-32 w-full bg-muted">
                      {item.kind === "photo" ? (
                        <img
                          src={item.previewUrl}
                          alt={item.file.name}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <video
                          src={item.previewUrl}
                          className="h-full w-full object-cover"
                          muted
                          playsInline
                        />
                      )}
                    </div>
                    <div className="flex items-center justify-between px-3 py-2 text-sm">
                      <div className="flex items-center gap-2">
                        {item.kind === "photo" ? (
                          <ImageIcon className="h-4 w-4" />
                        ) : (
                          <VideoIcon className="h-4 w-4" />
                        )}
                        <span className="line-clamp-1">{item.file.name}</span>
                      </div>
                      <Badge variant="outline" className="uppercase">
                        {item.kind}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
              {files.length === 0 && (
                <p className="mt-3 text-sm text-muted-foreground">
                  No files added yet. {selectedIssue?.damage_flow_kind === "broke_during_use"
                    ? "Add at least two photos or one video."
                    : "Add at least one photo or video."}
                </p>
              )}
            </div>
            <div className="text-sm text-muted-foreground">
              {selectedIssue?.damage_flow_kind === "broke_during_use" ? (
                <span>Need 2+ photos or 1 video showing what happened.</span>
              ) : (
                <span>Attach at least one file to submit.</span>
              )}
            </div>
          </div>
        )}

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => {
              if (step === 0) {
                onOpenChange(false);
              } else {
                setStep((prev) => (prev > 0 ? ((prev - 1) as 0 | 1 | 2) : prev));
              }
            }}
            disabled={submitting}
          >
            {step === 0 ? "Close" : "Back"}
          </Button>
          {step < 2 && (
            <Button
              onClick={() => setStep((prev) => ((prev + 1) as 0 | 1 | 2))}
              disabled={(step === 0 && !canContinueIssue) || (step === 1 && !canContinueDetails)}
            >
              Next
            </Button>
          )}
          {step === 2 && (
            <Button onClick={handleSubmit} disabled={!canSubmit || submitting}>
              {submitting ? "Submitting..." : "Submit issue"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
