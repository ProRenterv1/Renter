import { useEffect, useRef, useState } from "react";
import { Search, ChevronRight, Moon, Sun, User } from 'lucide-react';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';

interface TopBarProps {
  currentView: string;
  darkMode: boolean;
  onToggleTheme: () => void;
  operatorName: string;
  operatorRole: string;
  operatorEmail: string;
  onLogout: () => void;
}

const viewLabels: Record<string, string> = {
  dashboard: 'Dashboard',
  users: 'Users',
  listings: 'Listings',
  bookings: 'Bookings',
  finance: 'Finance',
  disputes: 'Disputes',
  promotions: 'Promotions',
  audit: 'Audit Log',
  comms: 'Communications',
  settings: 'Settings',
  health: 'System Health',
};

export function TopBar({
  currentView,
  darkMode,
  onToggleTheme,
  operatorName,
  operatorRole,
  operatorEmail,
  onLogout,
}: TopBarProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const displayName = operatorName?.trim() || operatorEmail?.trim() || "Operator";
  const roleLabel = operatorRole || "Operator";

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };
    const handleEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEsc);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEsc);
    };
  }, []);

  return (
    <header className="h-16 border-b border-border bg-card px-6 flex items-center justify-between">
      <div className="flex items-center gap-6 flex-1">
        {/* Breadcrumb */}
        <div className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Kitoro Ops</span>
          <ChevronRight className="w-4 h-4 text-muted-foreground" />
          <span className="text-foreground">{viewLabels[currentView]}</span>
        </div>
        
        {/* Global Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search users, listings, bookings..."
            className="w-full pl-10 pr-4 py-2 bg-background border border-input rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-ring"
          />
        </div>
      </div>
      
      <div className="flex items-center gap-4">
        {/* Operator Role Badge */}
        <Badge variant="secondary" className="bg-accent text-accent-foreground px-3 py-1">
          {roleLabel}
        </Badge>
        
        {/* Theme Toggle */}
        <Button
          variant="ghost"
          size="icon"
          onClick={onToggleTheme}
          className="rounded-md"
        >
          {darkMode ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </Button>
        
        {/* Profile Menu */}
        <div className="relative" ref={menuRef}>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="rounded-full"
            aria-label="Operator menu"
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((prev) => !prev)}
          >
            <User className="w-5 h-5" />
          </Button>
          {menuOpen ? (
            <div
              role="menu"
              className="absolute right-0 mt-2 w-48 rounded-md border bg-popover text-popover-foreground shadow-md z-50"
            >
              <div className="px-3 py-2 text-sm font-medium">{displayName}</div>
              <div className="px-3 pb-2 text-xs text-muted-foreground break-words">
                {operatorEmail}
              </div>
              <div className="border-t border-border" />
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
              >
                Profile
              </button>
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-accent hover:text-accent-foreground"
              >
                Activity Log
              </button>
              <div className="border-t border-border" />
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm text-destructive hover:bg-destructive/10"
                onClick={onLogout}
              >
                Log Out
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
