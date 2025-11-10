import { Menu, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ThemeToggle";
import logo from "@/assets/logo.png";

const links = [
  { label: "Browse Tools", href: "#categories" },
  { label: "How It Works", href: "#how-it-works" },
  { label: "Trust & Safety", href: "#features" },
  { label: "Renter Protect", href: "#cta" },
];

export function Header() {
  return (
    <header className="sticky top-0 z-40 w-full border-b border-border/60 bg-card/90 backdrop-blur supports-[backdrop-filter]:bg-card/70">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <div className="flex items-center gap-8">
          <a href="/" className="flex items-center gap-2" aria-label="Go to Renter home">
            <img
              src={logo}
              alt="Renter"
              className="h-9 w-auto dark:brightness-110 dark:invert"
              loading="lazy"
            />
          </a>
          <nav className="hidden items-center gap-6 text-sm font-medium text-muted-foreground md:flex">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                className="transition-colors hover:text-foreground"
              >
                {link.label}
              </a>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button variant="outline" className="hidden md:inline-flex" aria-label="Sign in">
            <User className="h-4 w-4" aria-hidden />
            Sign in
          </Button>
          <Button className="hidden sm:inline-flex">List an item</Button>
          <Button variant="ghost" size="icon" className="sm:hidden">
            <Menu className="h-5 w-5" aria-hidden />
            <span className="sr-only">Open navigation</span>
          </Button>
        </div>
      </div>
    </header>
  );
}
