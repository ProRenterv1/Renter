import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ImageIcon, Upload, VideoIcon, X } from "lucide-react";
import { toast } from "sonner";
import {
  disputesAPI,
  type DisputeCategory,
  type DisputeDamageFlowKind,
  type DisputeEvidenceCompletePayload,
  type DisputeEvidencePresignPayload,
  type DisputeEvidenceValidatePayload,
  type PhotoPresignResponse,
} from "@/lib/api";
import { compressImageFile } from "@/lib/imageCompression";
import { MAX_VIDEO_BYTES, MAX_VIDEO_MB_LABEL } from "@/lib/uploadLimits";
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
type WizardContext = "pre_pickup" | "post_pickup";

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
  width?: number;
  height?: number;
  originalSize?: number;
  compressedSize?: number;
}

export interface DisputeWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookingId: number | null;
  role: WizardRole;
  issueContext?: WizardContext;
  toolName?: string;
  rentalPeriodLabel?: string;
  onCreated?: (disputeId: number) => void;
}

const IMAGE_EXTENSIONS = new Set(["bmp", "gif", "heic", "heif", "jpg", "jpeg", "png", "webp"]);
const VIDEO_EXTENSIONS = new Set(["avi", "m4v", "mov", "mp4", "mpeg", "mpg", "webm"]);

const detectKind = (file: File): DisputeEvidenceCompletePayload["kind"] => {
  const type = (file.type || "").toLowerCase();
  if (type.startsWith("video/")) {
    return "video";
  }
  if (type.startsWith("image/")) {
    return "photo";
  }
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (IMAGE_EXTENSIONS.has(extension)) {
    return "photo";
  }
  if (VIDEO_EXTENSIONS.has(extension)) {
    return "video";
  }
  return "other";
};

const buildIssueOptions = (
  role: WizardRole,
  context: WizardContext = "post_pickup",
): IssueOption[] => {
  if (context === "pre_pickup") {
    if (role === "renter") {
      return [
        {
          key: "owner_no_show",
          title: "Owner didn't show up (pickup no-show)",
          description: "Report that the owner didn't arrive for pickup.",
          category: "pickup_no_show",
        },
      ];
    }
    return [
      {
        key: "renter_no_show",
        title: "Renter didn't show up (pickup no-show)",
        description: "Report that the renter didn't arrive for pickup.",
        category: "pickup_no_show",
      },
    ];
  }

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
const maxEvidenceFiles = 15;

const getFirstString = (value: unknown): string | null => {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      if (typeof item === "string") {
        return item;
      }
    }
  }
  return null;
};

const formatEvidenceErrors = (errors: unknown): string | null => {
  if (!Array.isArray(errors) || errors.length === 0) {
    return null;
  }
  const parts = errors
    .map((entry) => {
      if (!entry || typeof entry !== "object") {
        return null;
      }
      const detail = getFirstString((entry as Record<string, unknown>).detail);
      if (!detail) {
        return null;
      }
      const filename = getFirstString((entry as Record<string, unknown>).filename);
      return filename ? `${filename}: ${detail}` : detail;
    })
    .filter((entry): entry is string => Boolean(entry));
  return parts.length ? parts.join("; ") : null;
};

const extractApiErrorMessage = (error: unknown): string | null => {
  if (typeof error === "string") {
    return error;
  }
  if (!error || typeof error !== "object") {
    return null;
  }
  if ("data" in error) {
    const data = (error as { data?: unknown }).data;
    if (typeof data === "string") {
      return data;
    }
    if (data && typeof data === "object") {
      const record = data as Record<string, unknown>;
      const evidenceErrors = formatEvidenceErrors(record.errors);
      if (evidenceErrors) {
        return evidenceErrors;
      }
      const detail = getFirstString(record.detail);
      if (detail) {
        return detail;
      }
      const nonField = getFirstString(record.non_field_errors);
      if (nonField) {
        return nonField;
      }
      for (const value of Object.values(record)) {
        const fieldMessage = getFirstString(value);
        if (fieldMessage) {
          return fieldMessage;
        }
      }
    }
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return null;
};

export function DisputeWizard({
  open,
  onOpenChange,
  bookingId,
  role,
  issueContext,
  toolName,
  rentalPeriodLabel,
  onCreated,
}: DisputeWizardProps) {
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [selectedIssue, setSelectedIssue] = useState<IssueOption | null>(null);
  const [description, setDescription] = useState("");
  const [files, setFiles] = useState<EvidenceFile[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [compressing, setCompressing] = useState(false);

  const options = useMemo(
    () => buildIssueOptions(role, issueContext),
    [role, issueContext],
  );

  useEffect(() => {
    if (!open) {
      files.forEach((item) => URL.revokeObjectURL(item.previewUrl));
      setFiles([]);
      setSelectedIssue(null);
      setDescription("");
      setStep(0);
      setSubmitting(false);
      setCompressing(false);
    }
  }, [open, files]);

  const photoCount = files.filter((item) => item.kind === "photo").length;
  const videoCount = files.filter((item) => item.kind === "video").length;
  const isPickupNoShow = selectedIssue?.category === "pickup_no_show";

  const meetsEvidenceRequirement = useMemo(() => {
    if (!selectedIssue) {
      return false;
    }
    if (selectedIssue.damage_flow_kind === "broke_during_use") {
      return videoCount >= 1 || photoCount >= 2;
    }
    return files.length >= 1;
  }, [selectedIssue, files.length, photoCount, videoCount]);

  const handleFilesAdded = async (fileList: FileList | File[]) => {
    const remainingSlots = maxEvidenceFiles - files.length;
    if (remainingSlots <= 0) {
      toast.error(`You can upload up to ${maxEvidenceFiles} files.`);
      return;
    }
    setCompressing(true);
    try {
      const additions: EvidenceFile[] = [];
      let limitReached = false;
      for (const file of Array.from(fileList)) {
        if (additions.length >= remainingSlots) {
          limitReached = true;
          break;
        }
        const kind = detectKind(file);
        if (kind === "other") {
          toast.error(
            `${file.name || "File"} is not a supported file type. Please upload images or videos.`,
          );
          continue;
        }
        if (kind === "video" && file.size > MAX_VIDEO_BYTES) {
          toast.error(
            `${file.name || "Video"} is too large. Max size is ${MAX_VIDEO_MB_LABEL} MB.`,
          );
          continue;
        }
        if (kind === "photo") {
          const compressed = await compressImageFile(file);
          additions.push({
            file: compressed.file,
            previewUrl: URL.createObjectURL(compressed.file),
            kind,
            width: compressed.width,
            height: compressed.height,
            originalSize: compressed.originalSize,
            compressedSize: compressed.compressedSize,
          });
        } else {
          additions.push({
            file,
            previewUrl: URL.createObjectURL(file),
            kind,
          });
        }
      }
      if (limitReached) {
        toast.error(`You can upload up to ${maxEvidenceFiles} files.`);
      }
      if (additions.length) {
        setFiles((prev) => [...prev, ...additions]);
      }
    } catch (err) {
      console.error("evidence compression failed", err);
      toast.error("Could not process one of the files. Please try again.");
    } finally {
      setCompressing(false);
    }
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
    if (compressing) {
      toast.error("Please wait for images to finish compressing.");
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
      const validationPayload: DisputeEvidenceValidatePayload = {
        booking: bookingId,
        files: files.map((item) => ({
          filename: item.file.name,
          content_type: item.file.type || "application/octet-stream",
          size: item.file.size,
          width: item.width,
          height: item.height,
        })),
      };
      await disputesAPI.evidenceValidate(validationPayload);

      const presignedUploads: Array<{ item: EvidenceFile; presign: PhotoPresignResponse }> = [];
      for (const item of files) {
        const fileName = item.file.name || "file";
        try {
          const presignPayload: DisputeEvidencePresignPayload = {
            booking: bookingId,
            filename: item.file.name,
            content_type: item.file.type || "application/octet-stream",
            size: item.file.size,
          };
          const presign = await disputesAPI.evidencePresignForBooking(presignPayload);
          presignedUploads.push({ item, presign });
        } catch (err) {
          const detail = extractApiErrorMessage(err);
          const message = detail
            ? detail.startsWith(`${fileName}:`)
              ? detail
              : `${fileName}: ${detail}`
            : `${fileName}: Upload failed. Please try again.`;
          throw new Error(message);
        }
      }

      const dispute = await disputesAPI.create({
        booking: bookingId,
        category: selectedIssue.category,
        damage_flow_kind: selectedIssue.damage_flow_kind,
        description: description.trim(),
      });

      for (const { item, presign } of presignedUploads) {
        const fileName = item.file.name || "file";
        try {
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
            width: item.width,
            height: item.height,
            original_size: item.originalSize,
            compressed_size: item.compressedSize,
          };
          await disputesAPI.evidenceComplete(dispute.id, completePayload);
        } catch (err) {
          const detail = extractApiErrorMessage(err);
          const message = detail
            ? detail.startsWith(`${fileName}:`)
              ? detail
              : `${fileName}: ${detail}`
            : `${fileName}: Upload failed. Please try again.`;
          throw new Error(message);
        }
      }

      toast.success("Issue reported. Our team will review the dispute.");
      onCreated?.(dispute.id);
      if (typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("dispute:created", { detail: { id: dispute.id } }));
      }
      setSubmitting(false);
      onOpenChange(false);
    } catch (err) {
      const message =
        extractApiErrorMessage(err) || "Could not file dispute. Please try again.";
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
      <DialogContent className="max-h-[calc(100vh-2rem)] max-w-3xl space-y-4 overflow-y-auto">
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
            {isPickupNoShow ? (
              <div className="flex items-center gap-2 rounded-md border border-muted bg-muted/40 px-3 py-2 text-sm text-muted-foreground">
                <AlertTriangle className="h-4 w-4" />
                We'll notify the other party and request a response within 2 hours.
              </div>
            ) : (
              <div className="flex items-center gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">
                <AlertTriangle className="h-4 w-4" />
                Stop using the tool until the issue is resolved for safety reasons.
              </div>
            )}
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <div className="rounded-md border border-dashed p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium">Upload evidence</p>
                  <p className="text-sm text-muted-foreground">
                    {isPickupNoShow
                      ? "Upload a screenshot of messages, arrival photo, or location proof."
                      : "Photos or video of the issue. Drag-and-drop or select files."}
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
                        disabled={compressing || files.length >= maxEvidenceFiles}
                        onChange={(event) => {
                          if (event.target.files) {
                              void handleFilesAdded(event.target.files);
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
                  No files added yet.{" "}
                  {isPickupNoShow
                    ? "Add a screenshot or photo to show you were there."
                    : selectedIssue?.damage_flow_kind === "broke_during_use"
                    ? "Add at least two photos or one video."
                    : "Add at least one photo or video."}
                </p>
              )}
              <p className="text-xs text-muted-foreground">
                Images are compressed to reduce upload size; videos are compressed after upload. Up to{" "}
                {maxEvidenceFiles} files total, {MAX_VIDEO_MB_LABEL} MB max per video.
              </p>
              {compressing && (
                <p className="text-sm text-muted-foreground">Compressing images...</p>
              )}
            </div>
            <div className="text-sm text-muted-foreground">
              {isPickupNoShow ? (
                <span>The other party has 2 hours to respond once you submit.</span>
              ) : selectedIssue?.damage_flow_kind === "broke_during_use" ? (
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
