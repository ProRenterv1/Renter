import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import { Card, CardContent } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Input } from '../../components/ui/input';
import { 
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../../components/ui/select';
import { 
  Search, 
  MessageSquare, 
  AlertTriangle,
  Calendar,
  Bell,
  XCircle,
  ChevronRight,
} from 'lucide-react';
import {
  operatorAPI,
  type OperatorCommsConversationDetail,
  type OperatorCommsConversationListItem,
  type OperatorCommsMessage,
  type OperatorCommsNotification,
  type OperatorCommsParticipant,
} from '../api';
import { ConversationDetail } from '../components/ConversationDetail';
import { ResendNotificationsModal } from '../components/modals/ResendNotificationsModal';
import { cn } from '../../components/ui/utils';

type Participant = {
  userId: number;
  name: string;
  avatar: string;
};

type Message = {
  id: number;
  senderId: number;
  senderName: string;
  content: string;
  timestamp: string;
  type: 'text' | 'system';
};

type Notification = {
  id: number;
  type: string;
  recipientId: number;
  recipientName: string;
  sentAt: string;
  status: 'delivered' | 'failed' | 'pending';
  openedAt?: string;
};

type Conversation = {
  id: string;
  participants: Participant[];
  listingId: string;
  listingTitle: string;
  bookingId: string | null;
  status: string;
  unreadCount: number;
  lastMessageAt: string;
  createdAt: string;
  messages: Message[];
  notifications: Notification[];
};

type ConversationSummary = Omit<Conversation, 'messages' | 'notifications'>;

type NotificationLog = {
  id: string;
  name: string;
  lastSent?: string;
  status: 'sent' | 'failed' | 'missing';
};

const BASE_NOTIFICATION_TYPES = [
  { id: 'booking_request', name: 'Booking Request Email' },
  { id: 'status_update', name: 'Status Update Email' },
  { id: 'receipt', name: 'Payment Receipt' },
  { id: 'completed', name: 'Completed Email' },
];

const DISPUTE_NOTIFICATION_TYPES = [
  { id: 'dispute_missing_evidence', name: 'Dispute Evidence Reminder' },
];

const buildInitials = (value: string) => {
  const parts = value.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return 'U';
  if (parts.length === 1) return parts[0].charAt(0).toUpperCase();
  return `${parts[0].charAt(0)}${parts[1].charAt(0)}`.toUpperCase();
};

const formatSystemKind = (value?: string | null) => {
  if (!value) return '';
  return value
    .toLowerCase()
    .split('_')
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ''))
    .join(' ');
};

const formatNotificationLabel = (value: string) => {
  return value
    .split('_')
    .map((part) => (part ? part[0].toUpperCase() + part.slice(1) : ''))
    .join(' ');
};

const formatNotificationTimestamp = (value?: string) => {
  if (!value) return undefined;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const mapParticipant = (participant: OperatorCommsParticipant): Participant => {
  const name = participant.name || participant.email || 'Unknown';
  return {
    userId: participant.user_id ?? 0,
    name,
    avatar: buildInitials(name),
  };
};

const mapConversationListItem = (
  conversation: OperatorCommsConversationListItem,
): ConversationSummary => ({
  id: String(conversation.id),
  participants: conversation.participants.map(mapParticipant),
  listingId: conversation.listing_id ? String(conversation.listing_id) : '',
  listingTitle: conversation.listing_title || 'Listing',
  bookingId: conversation.booking_id ? String(conversation.booking_id) : null,
  status: conversation.status,
  unreadCount: conversation.unread_count ?? 0,
  lastMessageAt: conversation.last_message_at || conversation.created_at,
  createdAt: conversation.created_at,
});

const mapMessage = (message: OperatorCommsMessage): Message => {
  const content =
    message.text && message.text.trim().length > 0
      ? message.text
      : formatSystemKind(message.system_kind);
  return {
    id: message.id,
    senderId: message.sender_id ?? 0,
    senderName: message.sender_name || 'System',
    content,
    timestamp: message.created_at,
    type: message.message_type === 'system' ? 'system' : 'text',
  };
};

const mapNotification = (notification: OperatorCommsNotification): Notification => ({
  id: notification.id,
  type: notification.type,
  recipientId: notification.user_id ?? 0,
  recipientName: notification.user_name || 'Unknown',
  sentAt: notification.created_at,
  status: notification.status === 'sent' ? 'delivered' : 'failed',
});

const mapConversationDetail = (
  conversation: OperatorCommsConversationDetail,
): Conversation => ({
  ...mapConversationListItem(conversation),
  messages: conversation.messages.map(mapMessage),
  notifications: conversation.notifications.map(mapNotification),
});

const buildNotificationLogs = (
  notifications: Notification[],
  isDisputed: boolean,
): NotificationLog[] => {
  const baseTypes = isDisputed
    ? [...BASE_NOTIFICATION_TYPES, ...DISPUTE_NOTIFICATION_TYPES]
    : BASE_NOTIFICATION_TYPES;
  const known = new Set(baseTypes.map((type) => type.id));
  const extraTypes = Array.from(
    new Set(notifications.map((notification) => notification.type)),
  )
    .filter((type) => !known.has(type))
    .map((type) => ({ id: type, name: formatNotificationLabel(type) }));
  const allTypes = [...baseTypes, ...extraTypes];
  return allTypes.map((type) => {
    const latest = notifications
      .filter((notification) => notification.type === type.id)
      .sort((a, b) => new Date(b.sentAt).getTime() - new Date(a.sentAt).getTime())[0];
    if (!latest) {
      return { id: type.id, name: type.name, status: 'missing' };
    }
    return {
      id: type.id,
      name: type.name,
      status: latest.status === 'delivered' ? 'sent' : 'failed',
      lastSent: formatNotificationTimestamp(latest.sentAt),
    };
  });
};

export function Comms() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationDetails, setConversationDetails] = useState<Record<string, Conversation>>({});
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [resendOpen, setResendOpen] = useState(false);
  const [resendConversationId, setResendConversationId] = useState<string | null>(null);
  const [resendBookingId, setResendBookingId] = useState<string | null>(null);
  const [resendInitialSelected, setResendInitialSelected] = useState<string[]>([]);

  const refreshConversation = useCallback(async (conversationId: string) => {
    const data = await operatorAPI.commsConversationDetail(Number(conversationId));
    const mapped = mapConversationDetail(data);
    setConversationDetails((prev) => ({ ...prev, [conversationId]: mapped }));
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadConversations = async () => {
      setLoading(true);
      try {
        const data = await operatorAPI.commsConversations();
        if (cancelled) return;
        const mapped = data.map(mapConversationListItem);
        setConversations(mapped);
        setConversationDetails((prev) => {
          if (!Object.keys(prev).length) return prev;
          const next: Record<string, Conversation> = {};
          const ids = new Set(mapped.map((item) => item.id));
          Object.entries(prev).forEach(([id, value]) => {
            if (ids.has(id)) {
              next[id] = value;
            }
          });
          return next;
        });
      } catch (error) {
        toast.error('Unable to load conversations.');
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadConversations();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedConversationId) return;
    if (!conversations.some((item) => item.id === selectedConversationId)) {
      setSelectedConversationId(null);
    }
  }, [conversations, selectedConversationId]);

  useEffect(() => {
    if (!selectedConversationId) return;
    if (conversationDetails[selectedConversationId]) return;
    let cancelled = false;
    const loadConversation = async () => {
      setDetailLoading(true);
      try {
        const data = await operatorAPI.commsConversationDetail(Number(selectedConversationId));
        if (cancelled) return;
        setConversationDetails((prev) => ({
          ...prev,
          [selectedConversationId]: mapConversationDetail(data),
        }));
      } catch (error) {
        toast.error('Unable to load conversation.');
      } finally {
        if (!cancelled) {
          setDetailLoading(false);
        }
      }
    };

    loadConversation();

    return () => {
      cancelled = true;
    };
  }, [selectedConversationId, conversationDetails]);

  const filteredConversations = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    return conversations.filter((conversation) => {
      const matchesSearch =
        query.length === 0 ||
        conversation.participants.some((participant) =>
          participant.name.toLowerCase().includes(query),
        ) ||
        conversation.listingTitle.toLowerCase().includes(query) ||
        conversation.id.toLowerCase().includes(query);
      const matchesStatus =
        statusFilter === 'all' || conversation.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  }, [conversations, searchQuery, statusFilter]);

  const selectedConversation = selectedConversationId
    ? conversationDetails[selectedConversationId]
    : null;

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'disputed':
        return { variant: 'destructive' as const, label: 'Disputed', icon: AlertTriangle };
      case 'booking_related':
        return { variant: 'default' as const, label: 'Booking', icon: Calendar };
      case 'pre_booking':
        return { variant: 'secondary' as const, label: 'Pre-Booking', icon: MessageSquare };
      case 'inactive':
        return { variant: 'outline' as const, label: 'Inactive', icon: XCircle };
      default:
        return { variant: 'outline' as const, label: 'Unknown', icon: MessageSquare };
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };

  const handleOpenResendModal = useCallback(
    (notificationType?: string) => {
      if (!selectedConversation || !selectedConversation.bookingId) {
        return;
      }
      setResendConversationId(selectedConversation.id);
      setResendBookingId(selectedConversation.bookingId);
      setResendInitialSelected(notificationType ? [notificationType] : []);
      setResendOpen(true);
    },
    [selectedConversation],
  );

  const handleCloseResendModal = useCallback(() => {
    setResendOpen(false);
    setResendConversationId(null);
    setResendBookingId(null);
    setResendInitialSelected([]);
  }, []);

  const handleResendNotifications = useCallback(
    async (notificationIds: string[]) => {
      if (!resendBookingId || !resendConversationId) {
        return;
      }
      try {
        const response = await operatorAPI.resendBookingNotifications(
          Number(resendBookingId),
          { types: notificationIds },
        );
        const sent = response.queued || [];
        const failed = response.failed || [];
        const sentLabel = sent.join(', ') || 'none';
        const failedLabel = failed.join(', ');
        if (failed.length) {
          toast('Resend finished with issues', {
            description: `Sent: ${sentLabel} • Failed: ${failedLabel}`,
          });
        } else {
          toast.success(`Sent ${sent.length} notification${sent.length === 1 ? '' : 's'}`);
        }
        await refreshConversation(resendConversationId);
      } catch (error) {
        toast.error('Unable to resend notifications.');
        throw error;
      }
    },
    [refreshConversation, resendBookingId, resendConversationId],
  );

  const resendConversation = resendConversationId
    ? conversationDetails[resendConversationId]
    : null;
  const resendLogs = useMemo(() => {
    if (!resendConversation) return [];
    return buildNotificationLogs(
      resendConversation.notifications,
      resendConversation.status === 'disputed',
    );
  }, [resendConversation]);

  // Statistics
  const totalConversations = conversations.length;
  const disputedCount = conversations.filter((conversation) => conversation.status === 'disputed')
    .length;
  const activeBookings = conversations.filter(
    (conversation) => conversation.status === 'booking_related',
  ).length;
  const totalUnread = conversations.reduce((sum, conversation) => sum + conversation.unreadCount, 0);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2">Communications</h1>
        <p className="text-muted-foreground m-0">
          Monitor all user conversations and platform notifications
        </p>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground m-0">Total Chats</p>
                <h3 className="mt-1">{totalConversations}</h3>
              </div>
              <MessageSquare className="w-8 h-8 text-muted-foreground" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground m-0">Active Bookings</p>
                <h3 className="mt-1">{activeBookings}</h3>
              </div>
              <Calendar className="w-8 h-8 text-[var(--chart-1)]" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground m-0">Disputed</p>
                <h3 className="mt-1 text-destructive">{disputedCount}</h3>
              </div>
              <AlertTriangle className="w-8 h-8 text-destructive" />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-muted-foreground m-0">Unread Messages</p>
                <h3 className="mt-1">{totalUnread}</h3>
              </div>
              <Bell className="w-8 h-8 text-[var(--warning-badge)]" />
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content: Split View */}
      <div className="grid grid-cols-12 gap-6">
        {/* Left: Conversations List */}
        <div className="col-span-12 lg:col-span-5 space-y-4">
          {/* Filter Bar */}
          <Card>
            <CardContent className="p-4">
              <div className="space-y-3">
                {/* Search Input */}
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                  <Input
                    placeholder="Search conversations..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-10"
                  />
                </div>

                {/* Status Filter */}
                <Select value={statusFilter} onValueChange={setStatusFilter}>
                  <SelectTrigger>
                    <SelectValue placeholder="All Statuses" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Statuses</SelectItem>
                    <SelectItem value="disputed">Disputed</SelectItem>
                    <SelectItem value="booking_related">Booking Related</SelectItem>
                    <SelectItem value="pre_booking">Pre-Booking</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Conversations List */}
          <Card>
            <CardContent className="p-0">
              <div className="divide-y divide-border max-h-[600px] overflow-y-auto">
                {filteredConversations.length === 0 ? (
                  <div className="p-8 text-center">
                    <MessageSquare className="w-12 h-12 mx-auto mb-3 text-muted-foreground" />
                    <p className="text-muted-foreground m-0">
                      {loading ? 'Loading conversations...' : 'No conversations found'}
                    </p>
                  </div>
                ) : (
                  filteredConversations.map((conversation) => {
                    const statusBadge = getStatusBadge(conversation.status);
                    const StatusIcon = statusBadge.icon;
                    const isSelected = selectedConversationId === conversation.id;

                    return (
                      <button
                        key={conversation.id}
                        onClick={() => setSelectedConversationId(conversation.id)}
                        className={cn(
                          "w-full p-4 text-left transition-colors hover:bg-muted/50",
                          isSelected && "bg-muted border-l-4 border-l-primary"
                        )}
                      >
                        <div className="flex items-start gap-3">
                          {/* Avatars */}
                          <div className="flex -space-x-2">
                            {conversation.participants.map((participant) => (
                              <div
                                key={participant.userId}
                                className="w-10 h-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-sm border-2 border-card"
                              >
                                {participant.avatar}
                              </div>
                            ))}
                          </div>

                          {/* Content */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-2 mb-1">
                                  <span className="font-medium truncate">
                                    {conversation.participants.map(p => p.name).join(' & ')}
                                  </span>
                                  {conversation.unreadCount > 0 && (
                                    <Badge variant="destructive" className="text-xs px-1.5 py-0">
                                      {conversation.unreadCount}
                                    </Badge>
                                  )}
                                </div>
                                <p className="text-sm text-muted-foreground truncate m-0">
                                  {conversation.listingTitle}
                                </p>
                              </div>
                              <span className="text-xs text-muted-foreground whitespace-nowrap">
                                {formatDate(conversation.lastMessageAt)}
                              </span>
                            </div>

                            <div className="flex items-center gap-2 mt-2">
                              <Badge variant={statusBadge.variant} className="text-xs">
                                <StatusIcon className="w-3 h-3 mr-1" />
                                {statusBadge.label}
                              </Badge>
                              {conversation.bookingId && (
                                <Badge variant="outline" className="text-xs">
                                  {conversation.bookingId}
                                </Badge>
                              )}
                            </div>
                          </div>

                          <ChevronRight className="w-5 h-5 text-muted-foreground mt-2" />
                        </div>
                      </button>
                    );
                  })
                )}
              </div>
            </CardContent>
          </Card>

          {/* Results Count */}
          <div className="text-sm text-muted-foreground">
            Showing {filteredConversations.length} of {conversations.length} conversations
          </div>
        </div>

        {/* Right: Conversation Detail */}
        <div className="col-span-12 lg:col-span-7">
          {selectedConversation ? (
            <ConversationDetail
              conversation={selectedConversation}
              onResendNotification={handleOpenResendModal}
            />
          ) : selectedConversationId && detailLoading ? (
            <Card>
              <CardContent className="p-12 text-center">
                <MessageSquare className="w-16 h-16 mx-auto mb-4 text-muted-foreground" />
                <h3 className="mb-2">Loading Conversation</h3>
                <p className="text-muted-foreground m-0">
                  Fetching the conversation details from the database.
                </p>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-12 text-center">
                <MessageSquare className="w-16 h-16 mx-auto mb-4 text-muted-foreground" />
                <h3 className="mb-2">Select a Conversation</h3>
                <p className="text-muted-foreground m-0">
                  Choose a conversation from the list to view messages and details
                </p>
              </CardContent>
            </Card>
          )}
        </div>
      </div>

      <ResendNotificationsModal
        isOpen={resendOpen}
        onClose={handleCloseResendModal}
        bookingId={resendBookingId ?? ''}
        notificationLogs={resendLogs}
        initialSelected={resendInitialSelected}
        onResend={handleResendNotifications}
      />
    </div>
  );
}
