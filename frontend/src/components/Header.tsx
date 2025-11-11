import { Menu, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ThemeToggle";
import logo from "@/assets/logo.png";
import { LoginModal } from "./LoginModal";
import { useState } from "react";

const links = [
  { label: "Browse Tools", href: "#categories" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "List Your Tools", href: "#call-to-action" },
  { label: "About Us", href: "#about" },
];

export function Header() {
  const [loginOpen, setLoginOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"login" | "signup">("login");

  const openModal = (mode: "login" | "signup") => {
    setModalMode(mode);
    setLoginOpen(true);
  };
  return (
    <header className="sticky top-0 z-50 w-full border-b bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-8">
            <a href="/" className="flex items-center">
              <img
              src={logo}
              alt="Renter"
              className="h-9 w-auto dark:brightness-110 dark:invert"
              loading="lazy"
            />
            </a>
            
            <nav className="hidden md:flex items-center gap-6">
              {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="text-sm hover:opacity-70 transition-opacity"
                style={{ color: 'var(--text-heading)' }}
              >
                {link.label}
              </a>
            ))}
            </nav>
          </div>
          
          <div className="flex items-center gap-4">
            <ThemeToggle />
            <Button 
              variant="ghost" 
              size="sm"
              className="hidden sm:flex"
              onClick={() => openModal("login")}
            >
              Log In
            </Button>
            <Button 
              size="sm"
              className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
              style={{ color: 'var(--primary-foreground)' }}
              onClick={() => openModal("signup")}
            >
              <User className="w-4 h-4 mr-2" />
              Sign Up
            </Button>
            <Button 
              variant="ghost" 
              size="icon"
              className="md:hidden"
            >
              <Menu className="w-5 h-5" />
            </Button>
          </div>
        </div>
      </div>
      <LoginModal open={loginOpen} onOpenChange={setLoginOpen} defaultMode={modalMode} />
    </header>
  );
}

