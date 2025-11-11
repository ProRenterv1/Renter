import { useState, useEffect } from "react";
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

interface LoginModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultMode?: "login" | "signup";
}

export function LoginModal({ open, onOpenChange, defaultMode = "login" }: LoginModalProps) {
  const [isSignUp, setIsSignUp] = useState(defaultMode === "signup");
  const [signUpMethod, setSignUpMethod] = useState<"email" | "phone">("email");
  const [loginMethod, setLoginMethod] = useState<"email" | "phone">("email");

  // Sync isSignUp with defaultMode when modal opens
  useEffect(() => {
    if (open) {
      setIsSignUp(defaultMode === "signup");
    }
  }, [open, defaultMode]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="text-2xl">
            {isSignUp ? "Create your account" : "Welcome back"}
          </DialogTitle>
          <DialogDescription>
            {isSignUp
              ? "Join the Renter community and start renting tools from verified neighbours."
              : "Log in to access your account and browse available tools."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {isSignUp ? (
            <>
              {/* Sign Up Method Toggle */}
              <div className="grid grid-cols-2 gap-2 p-1 rounded-lg bg-muted">
                <button
                  onClick={() => setSignUpMethod("email")}
                  className={`px-4 py-2 rounded-md text-sm transition-colors ${
                    signUpMethod === "email"
                      ? "bg-card shadow-sm"
                      : "hover:bg-card/50"
                  }`}
                >
                  Email
                </button>
                <button
                  onClick={() => setSignUpMethod("phone")}
                  className={`px-4 py-2 rounded-md text-sm transition-colors ${
                    signUpMethod === "phone"
                      ? "bg-card shadow-sm"
                      : "hover:bg-card/50"
                  }`}
                >
                  Phone
                </button>
              </div>

              {/* Name Fields */}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-2">
                  <Label htmlFor="firstName">First Name</Label>
                  <Input
                    id="firstName"
                    placeholder="John"
                    className="h-11"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="lastName">Last Name</Label>
                  <Input
                    id="lastName"
                    placeholder="Doe"
                    className="h-11"
                  />
                </div>
              </div>

              {/* Email or Phone */}
              {signUpMethod === "email" ? (
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="you@example.com"
                    className="h-11"
                  />
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="phone">Phone Number</Label>
                  <Input
                    id="phone"
                    type="tel"
                    placeholder="+1 (587) 123-4567"
                    className="h-11"
                  />
                </div>
              )}

              {/* Password */}
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  className="h-11"
                />
                <p className="text-xs" style={{ color: "var(--text-muted)" }}>
                  Minimum 8 characters
                </p>
              </div>

              {/* City Selection */}
              <div className="space-y-2">
                <Label htmlFor="city">City</Label>
                <Select>
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

              {/* Age Confirmation */}
              <div className="flex items-start space-x-3 pt-2">
                <Checkbox id="age" className="mt-1" />
                <div className="space-y-1">
                  <label
                    htmlFor="age"
                    className="text-sm leading-none cursor-pointer"
                  >
                    I am 18 years or older
                  </label>
                </div>
              </div>

              {/* Terms and Privacy */}
              <div className="space-y-3">
                <div className="flex items-start space-x-3">
                  <Checkbox id="terms" className="mt-1" />
                  <div className="space-y-1">
                    <label
                      htmlFor="terms"
                      className="text-sm leading-none cursor-pointer"
                    >
                      I agree to the{" "}
                      <a
                        href="#"
                        className="underline hover:no-underline"
                        style={{ color: "var(--primary)" }}
                      >
                        Terms of Service
                      </a>
                    </label>
                  </div>
                </div>
                <div className="flex items-start space-x-3">
                  <Checkbox id="privacy" className="mt-1" />
                  <div className="space-y-1">
                    <label
                      htmlFor="privacy"
                      className="text-sm leading-none cursor-pointer"
                    >
                      I agree to the{" "}
                      <a
                        href="#"
                        className="underline hover:no-underline"
                        style={{ color: "var(--primary)" }}
                      >
                        Privacy Policy
                      </a>
                    </label>
                  </div>
                </div>
              </div>

              <Button
                className="w-full h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                style={{ color: "var(--primary-foreground)" }}
              >
                {signUpMethod === "email" ? "Create Account" : "Send Verification Code"}
              </Button>
            </>
          ) : (
            <>
              {/* Login Method Toggle */}
              <div className="grid grid-cols-2 gap-2 p-1 rounded-lg bg-muted">
                <button
                  onClick={() => setLoginMethod("email")}
                  className={`px-4 py-2 rounded-md text-sm transition-colors ${
                    loginMethod === "email"
                      ? "bg-card shadow-sm"
                      : "hover:bg-card/50"
                  }`}
                >
                  Email
                </button>
                <button
                  onClick={() => setLoginMethod("phone")}
                  className={`px-4 py-2 rounded-md text-sm transition-colors ${
                    loginMethod === "phone"
                      ? "bg-card shadow-sm"
                      : "hover:bg-card/50"
                  }`}
                >
                  Phone
                </button>
              </div>

              {/* Login Form */}
              {loginMethod === "email" ? (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="login-email">Email</Label>
                    <Input
                      id="login-email"
                      type="email"
                      placeholder="you@example.com"
                      className="h-11"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="login-password">Password</Label>
                      <button
                        className="text-sm hover:underline"
                        style={{ color: "var(--primary)" }}
                      >
                        Forgot password?
                      </button>
                    </div>
                    <Input
                      id="login-password"
                      type="password"
                      placeholder="••••••••"
                      className="h-11"
                    />
                  </div>
                </>
              ) : (
                <>
                  <div className="space-y-2">
                    <Label htmlFor="login-phone">Phone Number</Label>
                    <Input
                      id="login-phone"
                      type="tel"
                      placeholder="+1 (587) 123-4567"
                      className="h-11"
                    />
                  </div>

                  <div className="space-y-2">
                    <div className="flex items-center justify-between">
                      <Label htmlFor="login-phone-password">Password</Label>
                      <button
                        className="text-sm hover:underline"
                        style={{ color: "var(--primary)" }}
                      >
                        Forgot password?
                      </button>
                    </div>
                    <Input
                      id="login-phone-password"
                      type="password"
                      placeholder="••••••••"
                      className="h-11"
                    />
                  </div>
                </>
              )}

              <Button
                className="w-full h-11 bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
                style={{ color: "var(--primary-foreground)" }}
              >
                Log In
              </Button>

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
                <Button
                  variant="outline"
                  className="h-11"
                >
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
                <Button
                  variant="outline"
                  className="h-11"
                >
                  <svg className="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
                  </svg>
                  Facebook
                </Button>
              </div>
            </>
          )}

          <div className="text-center text-sm">
            <span style={{ color: "var(--text-muted)" }}>
              {isSignUp ? "Already have an account?" : "Don't have an account?"}
            </span>{" "}
            <button
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
  );
}