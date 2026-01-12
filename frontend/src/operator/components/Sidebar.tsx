import { 
  LayoutDashboard, 
  Users, 
  Package, 
  Calendar, 
  DollarSign, 
  Scale,
  Megaphone,
  MessageSquare,
  Settings,
  Activity,
  ScrollText
} from 'lucide-react';
import { cn } from '../../components/ui/utils';

interface SidebarProps {
  currentView: string;
  onNavigate: (view: string) => void;
  operatorName: string;
  operatorEmail: string;
  operatorAvatarUrl?: string | null;
}

const navItems = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'users', label: 'Users', icon: Users },
  { id: 'listings', label: 'Listings', icon: Package },
  { id: 'bookings', label: 'Bookings', icon: Calendar },
  { id: 'finance', label: 'Finance', icon: DollarSign },
  { id: 'disputes', label: 'Disputes', icon: Scale },
  { id: 'promotions', label: 'Promotions', icon: Megaphone },
  { id: 'audit', label: 'Audit Log', icon: ScrollText },
  { id: 'comms', label: 'Comms', icon: MessageSquare },
  { id: 'settings', label: 'Settings', icon: Settings },
  { id: 'health', label: 'Health', icon: Activity },
];

function getInitials(name: string) {
  const parts = name.split(" ").filter(Boolean);
  if (parts.length === 0) return "";
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return (parts[0].charAt(0) + parts[1].charAt(0)).toUpperCase();
}

export function Sidebar({
  currentView,
  onNavigate,
  operatorName,
  operatorEmail,
  operatorAvatarUrl,
}: SidebarProps) {
  const displayName = operatorName?.trim() || operatorEmail?.trim() || "Operator";
  const initials = getInitials(displayName);

  return (
    <aside className="w-[260px] border-r border-border bg-card flex flex-col">
      <div className="p-6 border-b border-border">
        <h1 className="text-xl m-0">Kitoro Ops</h1>
        <p className="text-sm text-muted-foreground m-0 mt-1">Operator Console</p>
      </div>
      
      <nav className="flex-1 p-3">
        <ul className="space-y-1 list-none p-0 m-0">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentView === item.id;
            
            return (
              <li key={item.id}>
                <button
                  onClick={() => onNavigate(item.id)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2.5 rounded-md transition-colors text-left",
                    isActive 
                      ? "bg-primary text-primary-foreground" 
                      : "text-foreground hover:bg-muted"
                  )}
                >
                  <Icon className="w-5 h-5" />
                  <span>{item.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="border-t border-border p-4 flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-muted text-foreground flex items-center justify-center text-sm font-medium overflow-hidden">
          {operatorAvatarUrl ? (
            <img
              src={operatorAvatarUrl}
              alt={displayName}
              className="w-full h-full object-cover"
            />
          ) : (
            initials || "OP"
          )}
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{displayName}</div>
          <div className="text-xs text-muted-foreground truncate">{operatorEmail}</div>
        </div>
      </div>
    </aside>
  );
}
