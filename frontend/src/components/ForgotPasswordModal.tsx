import { useState } from "react";
import { toast } from "sonner";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "./ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

import { authAPI } from "@/lib/api";

interface ForgotPasswordModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onPasswordResetSuccess: () => void;
}

type Step = "enter-contact" | "enter-code" | "enter-password";

type ResetErrors = {
  contact?: string;
  code?: string;
  password?: string;
};

const extractError = (error: unknown): string => {
  if (error && typeof error === "object" && "data" in error) {
    const data = (error as { data?: unknown }).data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: string }).detail;
      if (detail) return detail;
    }
  }
  return "Something went wrong";
};

export function ForgotPasswordModal({
  open,
  onOpenChange,
  onPasswordResetSuccess,
}: ForgotPasswordModalProps) {
  const [step, setStep] = useState<Step>("enter-contact");
  const [contactMethod, setContactMethod] = useState<"email" | "phone">("email");
  const [contact, setContact] = useState("");
  const [code, setCode] = useState("");
  const [challengeId, setChallengeId] = useState<number | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [errors, setErrors] = useState<ResetErrors>({});
  const [requesting, setRequesting] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [completing, setCompleting] = useState(false);

  const resetState = () => {
    setStep("enter-contact");
    setContactMethod("email");
    setContact("");
    setCode("");
    setChallengeId(null);
    setNewPassword("");
    setConfirmPassword("");
    setErrors({});
    setRequesting(false);
    setVerifying(false);
    setCompleting(false);
  };

  const handleClose = (nextOpen: boolean) => {
    if (!nextOpen) {
      resetState();
    }
    onOpenChange(nextOpen);
  };

  const handleSendCode = async () => {
    if (requesting) return;
    const trimmedContact = contact.trim();
    if (!trimmedContact) {
      setErrors({ contact: `Enter your ${contactMethod}` });
      return;
    }
    setErrors({});
    setContact(trimmedContact);
    setRequesting(true);
    try {
      const response = await authAPI.passwordReset.request({ contact: trimmedContact });
      if (response.challenge_id) {
        setChallengeId(response.challenge_id);
      }
      toast.success("Verification code sent!");
      setStep("enter-code");
    } catch (error) {
      setErrors({ contact: extractError(error) });
      toast.error(extractError(error));
    } finally {
      setRequesting(false);
    }
  };

  const handleVerifyCode = async () => {
    if (verifying) return;
    if (!code.trim()) {
      setErrors({ code: "Enter the 6-digit code" });
      return;
    }
    setErrors({});
    setVerifying(true);
    try {
      const trimmedContact = contact.trim();
      const payload = challengeId
        ? { challenge_id: challengeId, code }
        : { contact: trimmedContact, code };
      if (!challengeId && !trimmedContact) {
        setErrors({ contact: `Enter your ${contactMethod}` });
        setStep("enter-contact");
        setVerifying(false);
        return;
      }
      const response = await authAPI.passwordReset.verify(payload);
      setChallengeId(response.challenge_id);
      toast.success("Code verified!");
      setStep("enter-password");
    } catch (error) {
      setErrors({ code: extractError(error) });
      toast.error(extractError(error));
    } finally {
      setVerifying(false);
    }
  };

  const handleSavePassword = async () => {
    if (completing) return;
    const trimmedPassword = newPassword.trim();
    if (trimmedPassword.length < 8) {
      setErrors({ password: "Password must be at least 8 characters" });
      return;
    }
    if (trimmedPassword !== confirmPassword.trim()) {
      setErrors({ password: "Passwords do not match" });
      return;
    }
    if (!challengeId || !code.trim()) {
      setErrors({ password: "Please verify the code again" });
      setStep("enter-code");
      return;
    }
    setErrors({});
    setCompleting(true);
    try {
      await authAPI.passwordReset.complete({
        challenge_id: challengeId,
        code,
        new_password: trimmedPassword,
      });
      toast.success("Password updated! You can log in now.");
      handleClose(false);
      onPasswordResetSuccess();
    } catch (error) {
      setErrors({ password: extractError(error) });
      toast.error(extractError(error));
    } finally {
      setCompleting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="text-2xl">Reset Password</DialogTitle>
          <DialogDescription>
            {step === "enter-contact" && "Enter your email or phone number to receive a verification code."}
            {step === "enter-code" && `Enter the verification code we sent to your ${contactMethod}.`}
            {step === "enter-password" && "Enter your new password."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {step === "enter-contact" && (
            <>
              <div className="grid grid-cols-2 gap-2 p-1 rounded-lg bg-muted">
                <button
                  type="button"
                  onClick={() => setContactMethod("email")}
                  className={`px-4 py-2 rounded-md text-sm transition-colors ${
                    contactMethod === "email" ? "bg-card shadow-sm" : "hover:bg-card/50"
                  }`}
                >
                  Email
                </button>
                <button
                  type="button"
                  onClick={() => setContactMethod("phone")}
                  className={`px-4 py-2 rounded-md text-sm transition-colors ${
                    contactMethod === "phone" ? "bg-card shadow-sm" : "hover:bg-card/50"
                  }`}
                >
                  Phone
                </button>
              </div>

              <div className="space-y-2">
                <Label htmlFor="contact">
                  {contactMethod === "email" ? "Email" : "Phone Number"}
                </Label>
                <Input
                  id="contact"
                  type={contactMethod === "email" ? "email" : "tel"}
                  placeholder={
                    contactMethod === "email" ? "you@example.com" : "+1 (587) 123-4567"
                  }
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                  className="h-11"
                />
                {errors.contact && <p className="text-xs text-red-500">{errors.contact}</p>}
              </div>

              <Button
                onClick={handleSendCode}
                disabled={requesting}
                className="w-full h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                style={{ color: "var(--primary-foreground)" }}
              >
                {requesting ? "Sending..." : "Send Verification Code"}
              </Button>
            </>
          )}

          {step === "enter-code" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="code">Verification Code</Label>
                <Input
                  id="code"
                  type="text"
                  placeholder="Enter 6-digit code"
                  className="h-11"
                  maxLength={6}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  We sent a code to {contact || contactMethod}
                </p>
                {errors.code && <p className="text-xs text-red-500">{errors.code}</p>}
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={() => setStep("enter-contact")}
                  variant="outline"
                  className="flex-1 h-11"
                >
                  Back
                </Button>
                <Button
                  onClick={handleVerifyCode}
                  disabled={verifying}
                  className="flex-1 h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                  style={{ color: "var(--primary-foreground)" }}
                >
                  {verifying ? "Verifying..." : "Verify Code"}
                </Button>
              </div>

              <div className="text-center">
                <button
                  type="button"
                  onClick={handleSendCode}
                  className="text-sm hover:underline"
                  style={{ color: "var(--primary)" }}
                >
                  Resend code
                </button>
              </div>
            </>
          )}

          {step === "enter-password" && (
            <>
              <div className="space-y-2">
                <Label htmlFor="new-password">New Password</Label>
                <Input
                  id="new-password"
                  type="password"
                  placeholder="********"
                  className="h-11"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Minimum 8 characters
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="verify-password">Verify New Password</Label>
                <Input
                  id="verify-password"
                  type="password"
                  placeholder="Re-enter your password"
                  className="h-11"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
                {errors.password && <p className="text-xs text-red-500">{errors.password}</p>}
              </div>

              <Button
                onClick={handleSavePassword}
                disabled={completing}
                className="w-full h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                style={{ color: "var(--primary-foreground)" }}
              >
                {completing ? "Saving..." : "Save Password"}
              </Button>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
