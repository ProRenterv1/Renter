import { FormEvent, useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";

import {
  authAPI,
  type LoginRequest,
  type SignupPayload,
  type TokenResponse,
  type TwoFactorChannel,
  type TwoFactorLoginStartResponse,
} from "@/lib/api";
import { AuthStore, type AuthTokens } from "@/lib/auth";

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
import { Separator } from "@/components/ui/separator";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ForgotPasswordModal } from "./ForgotPasswordModal";

interface LoginModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultMode?: "login" | "signup";
  onAuthSuccess?: () => void;
}

type SignUpForm = {
  firstName: string;
  lastName: string;
  email: string;
  password: string;
  confirmPassword: string;
  city: string;
  ageConfirmed: boolean;
  acceptedTerms: boolean;
  acceptedPrivacy: boolean;
};

type LoginForm = {
  email: string;
  phone: string;
  password: string;
};

type FieldErrors = Record<string, string>;

const initialSignupState: SignUpForm = {
  firstName: "",
  lastName: "",
  email: "",
  password: "",
  confirmPassword: "",
  city: "",
  ageConfirmed: false,
  acceptedTerms: false,
  acceptedPrivacy: false,
};

const initialLoginState: LoginForm = { email: "", phone: "", password: "" };

type TwoFactorState = {
  active: boolean;
  challengeId: number | null;
  channel: TwoFactorChannel | null;
  contactHint: string;
  resendAvailableAt: number;
  code: string;
  verifying: boolean;
  resendLoading: boolean;
  error: string | null;
};

const initialTwoFactorState: TwoFactorState = {
  active: false,
  challengeId: null,
  channel: null,
  contactHint: "",
  resendAvailableAt: 0,
  code: "",
  verifying: false,
  resendLoading: false,
  error: null,
};

const parseErrorData = (data: unknown): FieldErrors => {
  if (!data || typeof data !== "object") return {};
  const entries = Object.entries(data as Record<string, unknown>);
  return entries.reduce<FieldErrors>((acc, [key, value]) => {
    if (Array.isArray(value)) {
      acc[key] = value.join(" ");
    } else if (typeof value === "string") {
      acc[key] = value;
    }
    return acc;
  }, {});
};

const extractErrorMessage = (error: unknown): string => {
  if (error && typeof error === "object" && "data" in error) {
    const data = (error as { data?: unknown }).data;
    if (data && typeof data === "object" && "detail" in data) {
      const detail = (data as { detail?: string }).detail;
      if (detail) return detail;
    }
  }
  return "Something went wrong";
};

const isTwoFactorResponse = (
  payload: TokenResponse,
): payload is TwoFactorLoginStartResponse => {
  return Boolean(payload && typeof payload === "object" && "requires_2fa" in payload);
};

const parseIsoTimestamp = (value: string): number => {
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? Date.now() : parsed;
};

export function LoginModal({
  open,
  onOpenChange,
  defaultMode = "login",
  onAuthSuccess,
}: LoginModalProps) {
  const [isSignUp, setIsSignUp] = useState(defaultMode === "signup");
  const [loginMethod, setLoginMethod] = useState<"email" | "phone">("email");
  const [showSignUpPassword, setShowSignUpPassword] = useState(false);
  const [showSignUpConfirmPassword, setShowSignUpConfirmPassword] = useState(false);
  const [showLoginPassword, setShowLoginPassword] = useState(false);
  const [forgotPasswordOpen, setForgotPasswordOpen] = useState(false);

  const [signupForm, setSignupForm] = useState<SignUpForm>(initialSignupState);
  const [signupErrors, setSignupErrors] = useState<FieldErrors>({});
  const [signupLoading, setSignupLoading] = useState(false);

  const [loginForm, setLoginForm] = useState<LoginForm>(initialLoginState);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);
  const [twoFactor, setTwoFactor] = useState<TwoFactorState>(initialTwoFactorState);
  const [twoFactorNow, setTwoFactorNow] = useState(() => Date.now());

  // Sync default mode every time the modal opens.
  useEffect(() => {
    if (open) {
      setIsSignUp(defaultMode === "signup");
    }
  }, [open, defaultMode]);

  useEffect(() => {
    if (!open) {
      setTwoFactor(initialTwoFactorState);
    }
  }, [open]);

  useEffect(() => {
    if (isSignUp) {
      setTwoFactor(initialTwoFactorState);
    }
  }, [isSignUp]);

  useEffect(() => {
    if (!twoFactor.active) {
      return;
    }
    const timer = window.setInterval(() => setTwoFactorNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [twoFactor.active]);

  const closeModal = () => {
    onOpenChange(false);
    setLoginError(null);
    resetTwoFactor();
  };

  const handleForgotPassword = () => {
    closeModal();
    setForgotPasswordOpen(true);
  };

  const handlePasswordResetSuccess = () => {
    setForgotPasswordOpen(false);
    setIsSignUp(false);
    onOpenChange(true);
  };

  const resetTwoFactor = () => {
    setTwoFactor(initialTwoFactorState);
    setTwoFactorNow(Date.now());
  };

  const startTwoFactorFlow = (payload: TwoFactorLoginStartResponse) => {
    setIsSignUp(false);
    const resendAt = parseIsoTimestamp(payload.resend_available_at);
    setTwoFactorNow(Date.now());
    setTwoFactor({
      active: true,
      challengeId: payload.challenge_id,
      channel: payload.channel,
      contactHint: payload.contact_hint,
      resendAvailableAt: resendAt,
      code: "",
      verifying: false,
      resendLoading: false,
      error: null,
    });
    setLoginError(null);
    toast.success("Verification code sent.");
  };

  const handleTwoFactorCodeChange = (value: string) => {
    const sanitized = value.replace(/\D/g, "").slice(0, 6);
    setTwoFactor((prev) => ({ ...prev, code: sanitized, error: null }));
  };

  const handleTwoFactorResend = async () => {
    if (!twoFactor.challengeId || twoFactor.resendLoading) {
      return;
    }
    if (twoFactor.resendAvailableAt > Date.now()) {
      return;
    }
    setTwoFactor((prev) => ({ ...prev, resendLoading: true, error: null }));
    try {
      const response = await authAPI.twoFactor.resendLogin({
        challenge_id: twoFactor.challengeId,
      });
      setTwoFactorNow(Date.now());
      setTwoFactor((prev) => ({
        ...prev,
        resendLoading: false,
        resendAvailableAt: parseIsoTimestamp(response.resend_available_at),
        code: "",
      }));
      toast.success("New verification code sent.");
    } catch (error) {
      setTwoFactor((prev) => ({ ...prev, resendLoading: false }));
      toast.error(extractErrorMessage(error));
    }
  };

  const handleTwoFactorVerify = async () => {
    if (!twoFactor.challengeId || twoFactor.code.length !== 6) {
      return;
    }
    setTwoFactor((prev) => ({ ...prev, verifying: true, error: null }));
    try {
      const tokens = await authAPI.twoFactor.verifyLogin({
        challenge_id: twoFactor.challengeId,
        code: twoFactor.code,
      });
      await handleAuthSuccess(tokens, "Verification successful!");
      resetTwoFactor();
      setLoginForm(initialLoginState);
    } catch (error) {
      const message =
        extractErrorMessage(error) || "Invalid or expired verification code.";
      setTwoFactor((prev) => ({
        ...prev,
        verifying: false,
        error: "Invalid or expired verification code.",
      }));
      const toastMessage =
        message === "Invalid or expired verification code."
          ? "Invalid or expired verification code. Please log in again if the code expired."
          : message;
      toast.error(toastMessage);
    }
  };

  const handleAuthSuccess = async (tokens: AuthTokens, successMessage: string) => {
    AuthStore.setTokens(tokens);
    try {
      const profile = await authAPI.me();
      AuthStore.setCurrentUser(profile);
    } catch {
      AuthStore.setCurrentUser(null);
    }
    toast.success(successMessage);
    closeModal();
    onAuthSuccess?.();
  };

  const updateSignupForm = <K extends keyof SignUpForm>(field: K, value: SignUpForm[K]) => {
    setSignupForm((prev) => ({ ...prev, [field]: value }));
  };

  const updateLoginForm = <K extends keyof LoginForm>(field: K, value: LoginForm[K]) => {
    setLoginForm((prev) => ({ ...prev, [field]: value }));
  };

  const validateSignupForm = (): FieldErrors => {
    const errors: FieldErrors = {};
    if (!signupForm.firstName.trim()) errors.first_name = "Enter your first name";
    if (!signupForm.lastName.trim()) errors.last_name = "Enter your last name";
    if (!signupForm.email.trim()) errors.email = "Email is required";
    if (signupForm.password.length < 8) errors.password = "Password must be at least 8 characters";
    if (signupForm.password !== signupForm.confirmPassword) {
      errors.confirm_password = "Passwords do not match";
    }
    if (!signupForm.ageConfirmed) errors.age = "You must be 18+";
    if (!signupForm.acceptedTerms) errors.terms = "Please accept the Terms of Service";
    if (!signupForm.acceptedPrivacy) errors.privacy = "Please accept the Privacy Policy";
    return errors;
  };

  const handleSignUpSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (signupLoading) return;
    const validationErrors = validateSignupForm();
    if (Object.keys(validationErrors).length) {
      setSignupErrors(validationErrors);
      return;
    }
    setSignupErrors({});
    setSignupLoading(true);
    try {
      const payload: SignupPayload = {
        username: signupForm.email.trim(),
        email: signupForm.email.trim(),
        first_name: signupForm.firstName.trim(),
        last_name: signupForm.lastName.trim(),
        password: signupForm.password,
      };

      await authAPI.signup(payload);

      const loginPayload: LoginRequest = {
        identifier: signupForm.email.trim(),
        password: signupForm.password,
      };
      const tokens = await authAPI.login(loginPayload);
      if (isTwoFactorResponse(tokens)) {
        startTwoFactorFlow(tokens);
      } else {
        await handleAuthSuccess(tokens, "Account created! You're now logged in.");
        setSignupForm(initialSignupState);
      }
    } catch (error) {
      const dataErrors =
        error && typeof error === "object" && "data" in error
          ? parseErrorData((error as { data?: unknown }).data)
          : {};
      setSignupErrors(dataErrors);
      toast.error(extractErrorMessage(error));
    } finally {
      setSignupLoading(false);
    }
  };

  const handleLoginSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (loginLoading) return;
    setLoginError(null);

    const identifier =
      loginMethod === "email" ? loginForm.email.trim() : loginForm.phone.trim();
    if (!identifier) {
      setLoginError("Please enter your " + (loginMethod === "email" ? "email" : "phone number"));
      return;
    }
    if (!loginForm.password) {
      setLoginError("Password is required");
      return;
    }

    setLoginLoading(true);
    try {
      const response = await authAPI.login({
        identifier,
        password: loginForm.password,
      });
      if (isTwoFactorResponse(response)) {
        startTwoFactorFlow(response);
      } else {
        await handleAuthSuccess(response, "Welcome back!");
        setLoginForm(initialLoginState);
      }
    } catch (error) {
      setLoginError("Invalid credentials");
      toast.error(extractErrorMessage(error));
    } finally {
      setLoginLoading(false);
    }
  };

  const renderSignUpForm = () => (
    <form className="space-y-4" onSubmit={handleSignUpSubmit}>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="firstName">First Name</Label>
          <Input
            id="firstName"
            placeholder="John"
            className="h-11"
            value={signupForm.firstName}
            onChange={(e) => updateSignupForm("firstName", e.target.value)}
          />
          {signupErrors.first_name && (
            <p className="text-xs text-red-500">{signupErrors.first_name}</p>
          )}
        </div>
        <div className="space-y-2">
          <Label htmlFor="lastName">Last Name</Label>
          <Input
            id="lastName"
            placeholder="Doe"
            className="h-11"
            value={signupForm.lastName}
            onChange={(e) => updateSignupForm("lastName", e.target.value)}
          />
          {signupErrors.last_name && (
            <p className="text-xs text-red-500">{signupErrors.last_name}</p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          placeholder="you@example.com"
          className="h-11"
          value={signupForm.email}
          onChange={(e) => updateSignupForm("email", e.target.value)}
        />
        {signupErrors.email && <p className="text-xs text-red-500">{signupErrors.email}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <div className="relative">
          <Input
            id="password"
            type={showSignUpPassword ? "text" : "password"}
            placeholder="********"
            className="h-11 pr-10"
            value={signupForm.password}
            onChange={(e) => updateSignupForm("password", e.target.value)}
          />
          <button
            type="button"
            onClick={() => setShowSignUpPassword((prev) => !prev)}
            className="absolute inset-y-0 right-3 flex items-center text-muted-foreground hover:text-foreground transition-colors"
            aria-label={showSignUpPassword ? "Hide password" : "Show password"}
          >
            {showSignUpPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Minimum 8 characters
        </p>
        {signupErrors.password && <p className="text-xs text-red-500">{signupErrors.password}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="confirmPassword">Verify Password</Label>
        <div className="relative">
          <Input
            id="confirmPassword"
            type={showSignUpConfirmPassword ? "text" : "password"}
            placeholder="Re-enter your password"
            className="h-11 pr-10"
            value={signupForm.confirmPassword}
            onChange={(e) => updateSignupForm("confirmPassword", e.target.value)}
          />
          <button
            type="button"
            onClick={() => setShowSignUpConfirmPassword((prev) => !prev)}
            className="absolute inset-y-0 right-3 flex items-center text-muted-foreground hover:text-foreground transition-colors"
            aria-label={showSignUpConfirmPassword ? "Hide confirm password" : "Show confirm password"}
          >
            {showSignUpConfirmPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        </div>
        {signupErrors.confirm_password && (
          <p className="text-xs text-red-500">{signupErrors.confirm_password}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="city">City</Label>
        <Select
          value={signupForm.city || undefined}
          onValueChange={(value) => updateSignupForm("city", value)}
        >
          <SelectTrigger className="h-11">
            <SelectValue placeholder="Select your city" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="edmonton">Edmonton</SelectItem>
            <SelectItem value="calgary">Calgary</SelectItem>
            <SelectItem value="other">Other (AB)</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center space-x-3 pt-2">
        <Checkbox
          id="age"
          checked={signupForm.ageConfirmed}
          onCheckedChange={(checked) => updateSignupForm("ageConfirmed", Boolean(checked))}
        />
        <label htmlFor="age" className="text-sm leading-none cursor-pointer">
          I am 18 years or older
        </label>
      </div>
      {signupErrors.age && <p className="text-xs text-red-500">{signupErrors.age}</p>}

      <div className="space-y-3">
        <div className="flex items-center space-x-3">
          <Checkbox
            id="terms"
            checked={signupForm.acceptedTerms}
            onCheckedChange={(checked) => updateSignupForm("acceptedTerms", Boolean(checked))}
          />
          <label htmlFor="terms" className="text-sm leading-none cursor-pointer">
            I agree to the{" "}
            <a href="#" className="underline hover:no-underline" style={{ color: "var(--primary)" }}>
              Terms of Service
            </a>
          </label>
        </div>
        {signupErrors.terms && <p className="text-xs text-red-500">{signupErrors.terms}</p>}

        <div className="flex items-center space-x-3">
          <Checkbox
            id="privacy"
            checked={signupForm.acceptedPrivacy}
            onCheckedChange={(checked) => updateSignupForm("acceptedPrivacy", Boolean(checked))}
          />
          <label htmlFor="privacy" className="text-sm leading-none cursor-pointer">
            I agree to the{" "}
            <a href="#" className="underline hover:no-underline" style={{ color: "var(--primary)" }}>
              Privacy Policy
            </a>
          </label>
        </div>
        {signupErrors.privacy && <p className="text-xs text-red-500">{signupErrors.privacy}</p>}
      </div>

      <Button
        type="submit"
        disabled={signupLoading}
        className="w-full h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
        style={{ color: "var(--primary-foreground)" }}
      >
        {signupLoading ? "Creating account..." : "Create Account"}
      </Button>
    </form>
  );

  const renderLoginForm = () => {
    const resendRemainingMs = Math.max(0, twoFactor.resendAvailableAt - twoFactorNow);
    const resendCountdown = Math.ceil(resendRemainingMs / 1000);
    const canResend = !twoFactor.resendLoading && resendRemainingMs <= 0;
    const contactDescription =
      twoFactor.contactHint ||
      (twoFactor.channel === "sms"
        ? "your phone"
        : twoFactor.channel === "email"
          ? "your email"
          : "your device");

    return (
      <form className="space-y-4" onSubmit={handleLoginSubmit}>
        <div className="grid grid-cols-2 gap-2 p-1 rounded-lg bg-muted">
          <button
            type="button"
            onClick={() => setLoginMethod("email")}
            className={`px-4 py-2 rounded-md text-sm transition-colors ${
              loginMethod === "email" ? "bg-card shadow-sm" : "hover:bg-card/50"
            }`}
          >
            Email
          </button>
          <button
            type="button"
            onClick={() => setLoginMethod("phone")}
            className={`px-4 py-2 rounded-md text-sm transition-colors ${
              loginMethod === "phone" ? "bg-card shadow-sm" : "hover:bg-card/50"
            }`}
          >
            Phone
          </button>
        </div>

        {loginMethod === "email" ? (
          <div className="space-y-2">
            <Label htmlFor="login-email">Email</Label>
            <Input
              id="login-email"
              type="email"
              placeholder="you@example.com"
              className="h-11"
              value={loginForm.email}
              onChange={(e) => updateLoginForm("email", e.target.value)}
            />
          </div>
        ) : (
          <div className="space-y-2">
            <Label htmlFor="login-phone">Phone Number</Label>
            <Input
              id="login-phone"
              type="tel"
              placeholder="+1 (587) 123-4567"
              className="h-11"
              value={loginForm.phone}
              onChange={(e) => updateLoginForm("phone", e.target.value)}
            />
          </div>
        )}

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="login-password">Password</Label>
            <button
              type="button"
              className="text-sm hover:underline"
              style={{ color: "var(--primary)" }}
              onClick={handleForgotPassword}
            >
              Forgot password?
            </button>
          </div>
          <div className="relative">
            <Input
              id="login-password"
              type={showLoginPassword ? "text" : "password"}
              placeholder="********"
              className="h-11 pr-10"
              value={loginForm.password}
              onChange={(e) => updateLoginForm("password", e.target.value)}
            />
            <button
              type="button"
              onClick={() => setShowLoginPassword((prev) => !prev)}
              className="absolute inset-y-0 right-3 flex items-center text-muted-foreground hover:text-foreground transition-colors"
              aria-label={showLoginPassword ? "Hide password" : "Show password"}
            >
              {showLoginPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
        </div>

        {loginError && <p className="text-sm text-red-500">{loginError}</p>}

        <Button
          type="submit"
          disabled={loginLoading}
          className="w-full h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
          style={{ color: "var(--primary-foreground)" }}
        >
          {loginLoading ? "Logging in..." : "Log In"}
        </Button>

        {twoFactor.active && (
          <div className="rounded-lg border p-4 space-y-3">
            <div>
              <h3 className="text-base font-semibold">Two-Factor Verification</h3>
              <p className="text-sm text-muted-foreground">
                Enter the 6-digit code we sent to {contactDescription}.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="two-factor-code">Verification Code</Label>
              <div className="relative">
                <Input
                  id="two-factor-code"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  maxLength={6}
                  autoComplete="one-time-code"
                  value={twoFactor.code}
                  onChange={(event) => handleTwoFactorCodeChange(event.target.value)}
                  className="pr-32 tracking-[0.3em]"
                  placeholder="______"
                />
                <button
                  type="button"
                  disabled={!canResend}
                  onClick={handleTwoFactorResend}
                  className="absolute inset-y-0 right-3 flex items-center text-sm font-semibold text-[var(--primary)] disabled:text-muted-foreground"
                >
                  {twoFactor.resendLoading
                    ? "Sending..."
                    : canResend
                      ? "Resend code"
                      : `Resend in ${Math.max(resendCountdown, 1)}s`}
                </button>
              </div>
              {twoFactor.error && (
                <p className="text-sm text-red-500">{twoFactor.error}</p>
              )}
            </div>
            <Button
              type="button"
              disabled={twoFactor.verifying || twoFactor.code.length !== 6}
              onClick={handleTwoFactorVerify}
              className="w-full h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
              style={{ color: "var(--primary-foreground)" }}
            >
              {twoFactor.verifying ? "Verifying..." : "Verify & Log In"}
            </Button>
          </div>
        )}

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <Separator />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-card px-2" style={{ color: "var(--text-muted)" }}>
              Or continue with
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <Button type="button" variant="outline" className="h-11">
            <svg className="w-5 h-5 mr-2" viewBox="0 0 24 24">
              <path
                fill="currentColor"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="currentColor"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="currentColor"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
              />
              <path
                fill="currentColor"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
              />
            </svg>
            Google
          </Button>
          <Button type="button" variant="outline" className="h-11">
            <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 24 24">
              <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
            </svg>
            Facebook
          </Button>
        </div>
      </form>
    );
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-2xl">
              {isSignUp ? "Create your account" : "Welcome back"}
            </DialogTitle>
            <DialogDescription>
              {isSignUp ? "" : "Log in to access your account and browse available tools."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4">
            {isSignUp ? renderSignUpForm() : renderLoginForm()}

            <div className="text-center text-sm">
              <span style={{ color: "var(--text-muted)" }}>
                {isSignUp ? "Already have an account?" : "Don't have an account?"}
              </span>{" "}
              <button
                type="button"
                onClick={() => setIsSignUp(!isSignUp)}
                className="hover:underline"
                style={{ color: "var(--primary)" }}
              >
                {isSignUp ? "Log in" : "Sign up"}
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      <ForgotPasswordModal
        open={forgotPasswordOpen}
        onOpenChange={setForgotPasswordOpen}
        onPasswordResetSuccess={handlePasswordResetSuccess}
      />
    </>
  );
}
