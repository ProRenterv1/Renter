import { toast } from "sonner";

export async function copyToClipboard(value: string, label?: string) {
  if (typeof navigator === "undefined" || !navigator.clipboard) {
    toast.error("Clipboard is not available in this browser.");
    return;
  }
  if (!value) {
    toast.error("Nothing to copy.");
    return;
  }
  try {
    await navigator.clipboard.writeText(value);
    const displayLabel = label?.trim() || "Value";
    toast.success(`${displayLabel} copied to clipboard`);
  } catch (error) {
    console.error("Failed to copy to clipboard", error);
    toast.error("Unable to copy to clipboard right now.");
  }
}
