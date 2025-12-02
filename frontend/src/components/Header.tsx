import { Menu, User, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ThemeToggle";
import logo from "@/assets/logo.png";
import { LoginModal } from "./LoginModal";
import { useEffect, useState } from "react";
import { AuthStore } from "@/lib/auth";
import { startEventStream } from "@/lib/events";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { fetchConversations, type ConversationSummary } from "@/lib/chat";
import { bookingsAPI, disputesAPI, type DisputeCase } from "@/lib/api";

const links = [
  { label: "Browse Tools", type: "route", href: "/feed" as const },
  { label: "How It Works", type: "section", sectionId: "how-it-works" as const },
  { label: "List Your Tools", type: "action" as const },
  { label: "About Us", type: "section", sectionId: "about" as const },
] as const;

type NavLink = (typeof links)[number];

type ChatEventMessage = {
  sender_is_me?: boolean;
  sender_id?: number | null;
  sender?: number | null;
  message_type: "user" | "system";
  system_kind: string | null;
  text: string;
  created_at: string;
};

const isMessageMine = (
  message: { sender_is_me?: boolean; sender_id?: number | null; sender?: number | null },
  currentUserId: number | null,
) => {
  if (typeof message.sender_is_me === "boolean") {
    return message.sender_is_me;
  }
  const senderCandidate =
    typeof message.sender_id === "number"
      ? message.sender_id
      : typeof message.sender === "number"
        ? message.sender
        : null;
  return senderCandidate !== null && currentUserId !== null && senderCandidate === currentUserId;
};

const deriveUnreadConversationIds = (conversations: ConversationSummary[]) => {
  return conversations.reduce((set, conv) => {
    if ((conv.unread_count ?? 0) > 0) {
      set.add(conv.id);
    }
    return set;
  }, new Set<number>());
};

export function Header() {
  const [loginOpen, setLoginOpen] = useState(false);
  const [modalMode, setModalMode] = useState<"login" | "signup">("login");
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [postLoginAction, setPostLoginAction] = useState<null | "add-listing">(null);
  const [unreadConversationIds, setUnreadConversationIds] = useState<Set<number>>(
    () => new Set(),
  );
  const [currentUserId, setCurrentUserId] = useState<number | null>(
    AuthStore.getCurrentUser()?.id ?? null,
  );
  const [actionCount, setActionCount] = useState(0);
  const unreadCount = unreadConversationIds.size;
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    const updateAuthState = () => {
      setIsAuthenticated(Boolean(AuthStore.getTokens()));
      setCurrentUserId(AuthStore.getCurrentUser()?.id ?? null);
    };
    updateAuthState();
    const unsubscribe = AuthStore.subscribe(updateAuthState);
    return () => {
      unsubscribe();
    };
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      setActionCount(0);
      return;
    }
    let cancelled = false;
    const loadActions = async () => {
      try {
        const [pending, disputes] = await Promise.all([
          bookingsAPI.pendingRequestsCount(),
          disputesAPI.list(),
        ]);
        if (cancelled) return;

        const unpaid = Number(pending.renter_unpaid_bookings ?? pending.unpaid_bookings ?? 0);
        const pendingRequests = Number(pending.pending_requests ?? 0);
        const disputeActions = (disputes as DisputeCase[]).filter((d) =>
          ["intake_missing_evidence", "awaiting_rebuttal"].includes(d.status),
        ).length;

        setActionCount(unpaid + pendingRequests + disputeActions);
      } catch (err) {
        if (import.meta.env.DEV) {
          console.warn("header: failed to load action counts", err);
        }
      }
    };

    void loadActions();
    const intervalId = window.setInterval(loadActions, 20000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [isAuthenticated]);

  useEffect(() => {
    if (!isAuthenticated) {
      setUnreadConversationIds(new Set());
      return;
    }
    if (location.pathname === "/messages") {
      setUnreadConversationIds(new Set());
    }
    const handle = startEventStream<{
      conversation_id: number;
      booking_id: number;
      message: ChatEventMessage;
    }>({
      onEvents: (events) => {
        if (location.pathname === "/messages") {
          return;
        }
        const newUnreadIds: number[] = [];
        for (const event of events) {
          if (event.type !== "chat:new_message" || !event.payload) {
            continue;
          }
          const message = event.payload.message;
          if (!message) {
            continue;
          }
          if (isMessageMine(message, currentUserId)) {
            continue;
          }
          const conversationId = event.payload.conversation_id;
          if (!newUnreadIds.includes(conversationId)) {
            newUnreadIds.push(conversationId);
          }
        }
        if (newUnreadIds.length > 0) {
          setUnreadConversationIds((prev) => {
            let changed = false;
            const next = new Set(prev);
            for (const id of newUnreadIds) {
              if (!next.has(id)) {
                next.add(id);
                changed = true;
              }
            }
            return changed ? next : prev;
          });
        }
      },
    });
    return () => handle.stop();
  }, [isAuthenticated, location.pathname, currentUserId]);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    let cancelled = false;
    const userId = AuthStore.getCurrentUser()?.id ?? null;
    fetchConversations()
      .then((conversations) => {
        if (cancelled) {
          return;
        }
        if (location.pathname === "/messages") {
          setUnreadConversationIds(new Set());
          return;
        }
        setUnreadConversationIds(deriveUnreadConversationIds(conversations));
      })
      .catch((err) => {
        console.error("header: failed to load conversations for unread count", err);
      });
    return () => {
      cancelled = true;
    };
  }, [isAuthenticated, currentUserId, location.pathname]);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    if (location.pathname === "/messages") {
      setUnreadConversationIds(new Set());
      return;
    }
    fetchConversations()
      .then((conversations) => {
        setUnreadConversationIds(deriveUnreadConversationIds(conversations));
      })
      .catch((err) => {
        console.error("header: failed to refresh unread count after leaving messages", err);
      });
  }, [isAuthenticated, currentUserId, location.pathname]);

  useEffect(() => {
    if (location.pathname === "/messages") {
      setUnreadConversationIds(new Set());
    }
  }, [location.pathname]);

  const openModal = (mode: "login" | "signup", nextAction: "add-listing" | null = null) => {
    setModalMode(mode);
    setPostLoginAction(nextAction);
    setLoginOpen(true);
  };

  const handleModalOpenChange = (open: boolean) => {
    setLoginOpen(open);
    if (!open) {
      setPostLoginAction(null);
    }
  };

  const handleMessagesClick = () => {
    navigate("/messages");
  };

  const handleProfileClick = () => {
    navigate("/profile");
  };

  const handleLogoutClick = () => {
    AuthStore.clearTokens();
    setIsAuthenticated(false);
    setModalMode("login");
    navigate("/");
  };

  const handleListYourTools = () => {
    if (isAuthenticated) {
      navigate("/profile?tab=add-listing");
      return;
    }
    openModal("login", "add-listing");
  };

  const scrollToSection = (sectionId: string) => {
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const handleSectionNavigation = (sectionId: string) => {
    const hash = `#${sectionId}`;
    if (location.pathname !== "/") {
      navigate({ pathname: "/", hash });
      return;
    }
    navigate({ hash });
    scrollToSection(sectionId);
  };

  const handleAuthSuccess = () => {
    setIsAuthenticated(true);
    if (postLoginAction === "add-listing") {
      navigate("/profile?tab=add-listing");
    }
    setPostLoginAction(null);
  };

  const renderNavLink = (link: NavLink) => {
    const baseClass =
      "text-sm font-normal hover:opacity-70 transition-opacity text-left";
    const buttonClass = `${baseClass} bg-transparent p-0 border-0`;
    if (link.type === "route") {
      return (
        <Link
          key={link.label}
          to={link.href}
          className={baseClass}
          style={{ color: "var(--text-heading)" }}
        >
          {link.label}
        </Link>
      );
    }
    if (link.type === "section") {
      return (
        <button
          key={link.label}
          type="button"
          className={buttonClass}
          style={{ color: "var(--text-heading)" }}
          onClick={() => handleSectionNavigation(link.sectionId)}
        >
          {link.label}
        </button>
      );
    }
    return (
      <button
        key={link.label}
        type="button"
        className={buttonClass}
        style={{ color: "var(--text-heading)" }}
        onClick={handleListYourTools}
      >
        {link.label}
      </button>
    );
  };

  return (
    <header className="sticky top-0 z-50 w-full border-b bg-card/95 backdrop-blur supports-[backdrop-filter]:bg-card/80">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">
        <div className="flex h-16 items-center justify-between">
          <div className="flex items-center gap-8">
            <Link to="/" className="flex items-center">
              <img
              src={logo}
              alt="Renter"
              className="h-9 w-auto dark:brightness-110 dark:invert"
              loading="lazy"
            />
            </Link>
            
            <nav className="hidden md:flex items-center gap-6">
              {links.map((link) => renderNavLink(link))}
            </nav>
          </div>
          
          <div className="flex items-center gap-3">
            <ThemeToggle />
            {isAuthenticated ? (
              <>
                <Button 
                  variant="ghost" 
                  onClick={handleMessagesClick}
                  className="relative"
                >
                  <MessageSquare className="w-4 h-4 mr-2" />
                  {unreadCount > 0 && (
                    <span
                      className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-semibold leading-none text-white"
                      style={{ backgroundColor: "#5B8CA6" }}
                    >
                      {unreadCount > 98 ? "99+" : unreadCount}
                    </span>
                  )}
                </Button>
                <Button 
                  variant="ghost" 
                  onClick={handleProfileClick}
                  className="relative"
                >
                  Profile
                  {actionCount > 0 && (
                    <span
                      className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full px-1 text-[10px] font-semibold leading-none text-white"
                      style={{ backgroundColor: "#5B8CA6" }}
                    >
                      {actionCount > 98 ? "99+" : actionCount}
                    </span>
                  )}
                </Button>
                <Button 
                  size="sm"
                  variant="ghost"
                  onClick={handleLogoutClick}
                >

                  Log Out
                </Button>
              </>
            ) : (
              <>
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
              </>
            )}
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
      <LoginModal
        open={loginOpen}
        onOpenChange={handleModalOpenChange}
        defaultMode={modalMode}
        onAuthSuccess={handleAuthSuccess}
      />
    </header>
  );
}

