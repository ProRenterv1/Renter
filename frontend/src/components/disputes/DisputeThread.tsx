import { useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import {
  AlertCircle,
  FileText,
  ImageIcon,
  Loader2,
  MessageSquare,
  Send,
  Upload,
  VideoIcon,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  disputesAPI,
  type DisputeCase,
  type DisputeEvidenceCompletePayload,
  type DisputeMessage,
  type PhotoPresignRequest,
} from "@/lib/api";
import { compressImageFile } from "@/lib/imageCompression";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "../ui/avatar";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";

interface DisputeThreadProps {
  disputeId: number;
  onDisputeUpdated?: (disputeId: number) => void;
}

interface EvidenceUploadFile {
  file: File;
  previewUrl: string;
  kind: DisputeEvidenceCompletePayload["kind"];
  width?: number;
  height?: number;
  originalSize?: number;
  compressedSize?: number;
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

export function DisputeThread({ disputeId, onDisputeUpdated }: DisputeThreadProps) {
  const [dispute, setDispute] = useState<DisputeCase | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messageText, setMessageText] = useState("");
  const [sending, setSending] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadFiles, setUploadFiles] = useState<EvidenceUploadFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [compressing, setCompressing] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (uploadOpen) {
      return;
    }
    setUploadFiles((prev) => {
      prev.forEach((item) => URL.revokeObjectURL(item.previewUrl));
      return [];
    });
    setUploading(false);
    setCompressing(false);
    setUploadError(null);
  }, [uploadOpen]);

  const loadDispute = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await disputesAPI.retrieve(disputeId);
      setDispute(data);
    } catch (err) {
      setError("Unable to load dispute. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadDispute();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disputeId]);

  const messages = useMemo<DisputeMessage[]>(() => dispute?.messages ?? [], [dispute]);

  const handleSend = async () => {
    if (!messageText.trim()) {
      return;
    }
    setSending(true);
    try {
      const created = await disputesAPI.createMessage(disputeId, messageText.trim());
      setDispute((prev) =>
        prev
          ? {
              ...prev,
              messages: [...(prev.messages ?? []), created],
            }
          : prev,
      );
      setMessageText("");
    } catch (err) {
      setError("Could not send message. Please retry.");
    } finally {
      setSending(false);
    }
  };

  const handleEvidenceFilesAdded = async (fileList: FileList | File[]) => {
    setCompressing(true);
    setUploadError(null);
    try {
      const additions: EvidenceUploadFile[] = [];
      for (const file of Array.from(fileList)) {
        const kind = detectKind(file);
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
      setUploadFiles((prev) => [...prev, ...additions]);
    } catch (err) {
      console.error("dispute evidence compression failed", err);
      toast.error("Could not process one of the files. Please try again.");
    } finally {
      setCompressing(false);
    }
  };

  const removeEvidenceFile = (index: number) => {
    setUploadFiles((prev) => {
      const next = [...prev];
      const [removed] = next.splice(index, 1);
      if (removed) {
        URL.revokeObjectURL(removed.previewUrl);
      }
      return next;
    });
  };

  const handleEvidenceUpload = async () => {
    if (uploading) {
      return;
    }
    if (compressing) {
      setUploadError("Please wait for images to finish compressing.");
      return;
    }
    if (uploadFiles.length === 0) {
      setUploadError("Select at least one file to upload.");
      return;
    }
    setUploading(true);
    setUploadError(null);
    try {
      for (const item of uploadFiles) {
        const presignPayload: PhotoPresignRequest = {
          filename: item.file.name,
          content_type: item.file.type || "application/octet-stream",
          size: item.file.size,
        };
        const presign = await disputesAPI.evidencePresign(disputeId, presignPayload);
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
          uploadResponse.headers.get("ETag") ?? uploadResponse.headers.get("etag");
        if (!etagHeader) {
          throw new Error("Upload completed but verification failed. Please retry.");
        }
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
        await disputesAPI.evidenceComplete(disputeId, completePayload);
      }

      const updated = await disputesAPI.retrieve(disputeId);
      setDispute(updated);
      toast.success("Evidence uploaded. Our team will review it shortly.");
      setUploadOpen(false);
      onDisputeUpdated?.(disputeId);
    } catch (err) {
      console.error("dispute evidence upload failed", err);
      const message = err instanceof Error ? err.message : "Could not upload evidence.";
      setUploadError(message);
      toast.error(message);
    } finally {
      setUploading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading dispute…
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-destructive">
        <AlertCircle className="h-4 w-4" />
        {error}
      </div>
    );
  }

  if (!dispute) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div className="bg-card border rounded-lg p-6">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 className="font-medium">Evidence Submitted</h3>
            <p className="text-sm text-muted-foreground">
              Add additional photos or videos to support your case.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            className="flex items-center gap-2"
            onClick={() => setUploadOpen(true)}
          >
            <Upload className="h-4 w-4" />
            Add evidence
          </Button>
        </div>
        <div className="space-y-4">
          {(dispute.evidence ?? []).map((ev) => {
            const isImage = ev.content_type?.startsWith("image/");
            const isVideo = ev.content_type?.startsWith("video/");
            const description =
              (ev as DisputeEvidenceWithDescription).description ?? ev.filename ?? ev.kind;
            const evidenceUrl = ev.url || ev.s3_key;
            return (
              <div key={ev.id} className="border rounded-lg p-4">
                <div className="flex items-start gap-4">
                  <div className="w-32 h-32 bg-muted rounded-lg flex items-center justify-center overflow-hidden">
                    {isImage && evidenceUrl ? (
                      <img src={evidenceUrl} alt={description} className="w-full h-full object-cover" />
                    ) : isVideo && evidenceUrl ? (
                      <video
                        src={evidenceUrl}
                        className="w-full h-full object-cover"
                        muted
                        playsInline
                      />
                    ) : (
                      <FileText className="w-12 h-12 text-muted-foreground" />
                    )}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2 flex-wrap">
                      <Badge variant="outline" className="text-xs uppercase">
                        {ev.kind}
                      </Badge>
                      <Badge variant="secondary" className="text-xs">
                        AV: {ev.av_status || "pending"}
                      </Badge>
                    </div>
                    <p className="text-sm mb-2 break-words">{description}</p>
                    <p className="text-xs text-muted-foreground">
                      Uploaded: {format(new Date(ev.created_at), "MMM d, yyyy h:mm a")}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}

          {(dispute.evidence ?? []).length === 0 && (
            <div className="border rounded-lg p-6 text-center text-sm text-muted-foreground">
              No evidence uploaded yet.
            </div>
          )}
        </div>
      </div>

      <Dialog
        open={uploadOpen}
        onOpenChange={(next) => {
          if (!uploading) {
            setUploadOpen(next);
          }
        }}
      >
        <DialogContent className="max-w-3xl space-y-4">
          <DialogHeader>
            <DialogTitle>Upload additional evidence</DialogTitle>
            <DialogDescription>
              Add photos or video to help our team review your dispute.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="rounded-md border border-dashed p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium">Select files</p>
                  <p className="text-sm text-muted-foreground">
                    Photos are compressed to reduce upload size. Videos upload as-is.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    className="flex items-center gap-2"
                    disabled={compressing || uploading}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <Upload className="h-4 w-4" />
                    Add files
                  </Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    className="hidden"
                    multiple
                    accept="image/*,video/*"
                    disabled={compressing || uploading}
                    onChange={(event) => {
                      if (event.target.files) {
                        void handleEvidenceFilesAdded(event.target.files);
                        event.target.value = "";
                      }
                    }}
                  />
                </div>
              </div>
              {uploadFiles.length === 0 && (
                <p className="mt-3 text-sm text-muted-foreground">No files selected yet.</p>
              )}
            </div>

            {uploadFiles.length > 0 && (
              <div className="grid gap-3 sm:grid-cols-2">
                {uploadFiles.map((item, index) => (
                  <div
                    key={item.previewUrl}
                    className="relative overflow-hidden rounded-md border bg-card shadow-sm"
                  >
                    <button
                      type="button"
                      onClick={() => removeEvidenceFile(index)}
                      className="absolute right-2 top-2 rounded-full bg-background/80 p-1 text-muted-foreground transition hover:text-foreground"
                      aria-label="Remove evidence"
                    >
                      <X className="h-4 w-4" />
                    </button>
                    <div className="h-32 w-full bg-muted flex items-center justify-center">
                      {item.kind === "photo" ? (
                        <img
                          src={item.previewUrl}
                          alt={item.file.name}
                          className="h-full w-full object-cover"
                        />
                      ) : item.kind === "video" ? (
                        <video
                          src={item.previewUrl}
                          className="h-full w-full object-cover"
                          muted
                          playsInline
                        />
                      ) : (
                        <FileText className="h-10 w-10 text-muted-foreground" />
                      )}
                    </div>
                    <div className="flex items-center justify-between px-3 py-2 text-sm">
                      <div className="flex items-center gap-2 min-w-0">
                        {item.kind === "photo" ? (
                          <ImageIcon className="h-4 w-4" />
                        ) : item.kind === "video" ? (
                          <VideoIcon className="h-4 w-4" />
                        ) : (
                          <FileText className="h-4 w-4" />
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
            )}

            {compressing && (
              <p className="text-sm text-muted-foreground">Compressing images...</p>
            )}

            {uploadError && <p className="text-sm text-destructive">{uploadError}</p>}
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setUploadOpen(false)}
              disabled={uploading}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={() => void handleEvidenceUpload()}
              disabled={uploading || compressing || uploadFiles.length === 0}
              className="flex items-center gap-2"
            >
              {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Upload evidence
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <div className="bg-card border rounded-lg">
        <div className="p-6 border-b">
          <h3 className="font-medium flex items-center gap-2">
            <MessageSquare className="w-5 h-5" />
            Dispute Conversation
          </h3>
        </div>

        <div className="p-6 space-y-4 max-h-96 overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-sm text-muted-foreground">No messages yet.</p>
          )}
          {messages.map((message) => {
            const isSupport = message.role === "admin" || message.role === "system";
            const roleLabel = isSupport ? "Support Team" : message.role.toUpperCase();
            return (
              <div
                key={message.id}
                className={cn(
                  "flex gap-3",
                  isSupport ? "bg-muted/50 -mx-6 px-6 py-4 rounded-none md:rounded-none" : "",
                )}
              >
                <Avatar className="w-8 h-8">
                  <AvatarFallback
                    className={isSupport ? "bg-orange-500 text-white" : "bg-[var(--primary)]"}
                    style={isSupport ? undefined : { color: "var(--primary-foreground)" }}
                  >
                    {isSupport ? "RS" : roleLabel.slice(0, 2)}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-medium text-sm">{roleLabel}</span>
                    {isSupport ? (
                      <Badge variant="secondary" className="text-xs">
                        Support Team
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] uppercase tracking-wide">
                        {roleLabel}
                      </Badge>
                    )}
                    <span className="text-xs text-muted-foreground">
                      {format(new Date(message.created_at), "MMM d, yyyy h:mm a")}
                    </span>
                  </div>
                  <p className="text-sm whitespace-pre-wrap">{message.text}</p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="p-4 border-t">
          <div className="flex gap-2">
            <input
              type="text"
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  void handleSend();
                }
              }}
              placeholder="Type your message..."
              className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] bg-background"
            />
            <Button
              onClick={() => void handleSend()}
              disabled={sending || !messageText.trim()}
              className="flex items-center gap-2"
            >
              <Send className="h-4 w-4" />
              Send
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

type DisputeEvidenceWithDescription = {
  description?: string | null;
};
