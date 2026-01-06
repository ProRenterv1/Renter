import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { ScrollArea } from '../../components/ui/scroll-area';
import { Separator } from '../../components/ui/separator';
import {
  MessageSquare,
  User,
  Package,
  Calendar,
  ExternalLink,
  Bell,
  CheckCircle2,
  XCircle,
  Clock,
  Mail,
  AlertTriangle,
  Info,
  Send,
} from 'lucide-react';
import { toast } from 'sonner@2.0.3';

interface Participant {
  userId: number;
  name: string;
  avatar: string;
}

interface Message {
  id: number;
  senderId: number;
  senderName: string;
  content: string;
  timestamp: string;
  type: 'text' | 'system';
}

interface Notification {
  id: number;
  type: string;
  recipientId: number;
  recipientName: string;
  sentAt: string;
  status: 'delivered' | 'failed' | 'pending';
  openedAt?: string;
}

interface Conversation {
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
}

interface ConversationDetailProps {
  conversation: Conversation;
  onResendNotification?: (notificationType: string) => void;
}

export function ConversationDetail({ conversation, onResendNotification }: ConversationDetailProps) {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('messages');

  const formatTimestamp = (timestamp: string) => {
    const date = new Date(timestamp);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  const formatNotificationType = (type: string) => {
    return type
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const getNotificationIcon = (type: string) => {
    if (type.includes('dispute')) return AlertTriangle;
    if (type.includes('overdue')) return Clock;
    if (type.includes('booking')) return Calendar;
    if (type.includes('reminder')) return Bell;
    return Mail;
  };

  const handleResendNotification = (notificationType: string) => {
    if (onResendNotification) {
      onResendNotification(notificationType);
      return;
    }
    toast.success('Notification resent successfully');
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'disputed':
        return { variant: 'destructive' as const, label: 'Disputed', icon: AlertTriangle };
      case 'booking_related':
        return { variant: 'default' as const, label: 'Booking Related', icon: Calendar };
      case 'pre_booking':
        return { variant: 'secondary' as const, label: 'Pre-Booking', icon: MessageSquare };
      case 'inactive':
        return { variant: 'outline' as const, label: 'Inactive', icon: XCircle };
      default:
        return { variant: 'outline' as const, label: 'Unknown', icon: MessageSquare };
    }
  };

  const statusBadge = getStatusBadge(conversation.status);
  const StatusIcon = statusBadge.icon;

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <div className="space-y-4">
          {/* Header */}
          <div className="flex items-start justify-between">
            <div className="space-y-2">
              <div className="flex items-center gap-3">
                <h3 className="m-0">{conversation.id}</h3>
                <Badge variant={statusBadge.variant}>
                  <StatusIcon className="w-3 h-3 mr-1" />
                  {statusBadge.label}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground m-0">
                Started {new Date(conversation.createdAt).toLocaleDateString('en-US', { 
                  month: 'long', 
                  day: 'numeric', 
                  year: 'numeric' 
                })}
              </p>
            </div>
          </div>

          {/* Participants */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-muted-foreground" />
              <span className="text-sm">Participants:</span>
            </div>
            <div className="flex items-center gap-3">
              {conversation.participants.map((participant) => (
                <Button
                  key={participant.userId}
                  variant="outline"
                  size="sm"
                  onClick={() => navigate(`/operator/users/${participant.userId}`)}
                  className="h-8"
                >
                  <div className="w-6 h-6 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs mr-2">
                    {participant.avatar}
                  </div>
                  {participant.name}
                  <ExternalLink className="w-3 h-3 ml-2" />
                </Button>
              ))}
            </div>
          </div>

          {/* Related Items */}
          <div className="flex items-center gap-6">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate(`/operator/listings/${conversation.listingId}`)}
              className="h-8 px-3"
            >
              <Package className="w-4 h-4 mr-2" />
              {conversation.listingTitle}
              <ExternalLink className="w-3 h-3 ml-2" />
            </Button>
            {conversation.bookingId && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate(`/operator/bookings/${conversation.bookingId}`)}
                className="h-8 px-3"
              >
                <Calendar className="w-4 h-4 mr-2" />
                {conversation.bookingId}
                <ExternalLink className="w-3 h-3 ml-2" />
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="p-0">
        <Tabs value={activeTab} onValueChange={setActiveTab}>
          <div className="border-b border-border px-6">
            <TabsList className="bg-transparent h-12 p-0 space-x-6">
              <TabsTrigger 
                value="messages" 
                className="bg-transparent data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3"
              >
                <MessageSquare className="w-4 h-4 mr-2" />
                Messages ({conversation.messages.length})
              </TabsTrigger>
              <TabsTrigger 
                value="notifications"
                className="bg-transparent data-[state=active]:bg-transparent data-[state=active]:border-b-2 data-[state=active]:border-primary rounded-none px-0 pb-3"
              >
                <Bell className="w-4 h-4 mr-2" />
                Notifications ({conversation.notifications.length})
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="messages" className="m-0">
            <ScrollArea className="h-[500px]">
              <div className="p-6 space-y-4">
                {conversation.messages.map((message, index) => {
                  const isSystem = message.senderId === 0;
                  const participant = conversation.participants.find(p => p.userId === message.senderId);

                  return (
                    <div key={message.id}>
                      {/* Date separator */}
                      {index === 0 || 
                       new Date(message.timestamp).toDateString() !== 
                       new Date(conversation.messages[index - 1].timestamp).toDateString() ? (
                        <div className="flex items-center gap-3 my-4">
                          <Separator className="flex-1" />
                          <span className="text-xs text-muted-foreground">
                            {new Date(message.timestamp).toLocaleDateString('en-US', {
                              month: 'long',
                              day: 'numeric',
                              year: 'numeric',
                            })}
                          </span>
                          <Separator className="flex-1" />
                        </div>
                      ) : null}

                      {isSystem ? (
                        <div className="flex items-center justify-center my-4">
                          <div className="bg-muted px-4 py-2 rounded-full max-w-md">
                            <div className="flex items-center gap-2">
                              <Info className="w-3 h-3 text-muted-foreground" />
                              <p className="text-xs text-muted-foreground m-0">
                                {message.content}
                              </p>
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs flex-shrink-0">
                            {participant?.avatar}
                          </div>
                          <div className="flex-1 space-y-1">
                            <div className="flex items-center gap-2">
                              <span className="text-sm">{message.senderName}</span>
                              <span className="text-xs text-muted-foreground">
                                {formatTimestamp(message.timestamp)}
                              </span>
                            </div>
                            <div className="bg-muted px-4 py-2 rounded-lg inline-block max-w-lg">
                              <p className="text-sm m-0">{message.content}</p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Read-only notice */}
                <div className="mt-6 p-4 bg-accent border border-[var(--info-border)] rounded-lg">
                  <div className="flex items-start gap-3">
                    <Info className="w-5 h-5 text-accent-foreground flex-shrink-0 mt-0.5" />
                    <div>
                      <p className="text-sm m-0">
                        <strong>Read-Only Mode:</strong> This is a monitoring view for operators. 
                        Users send messages directly through the platform interface. 
                        To intervene, contact users directly or use the booking management tools.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </ScrollArea>
          </TabsContent>

          <TabsContent value="notifications" className="m-0">
            <ScrollArea className="h-[500px]">
              <div className="p-6">
                {conversation.notifications.length === 0 ? (
                  <div className="text-center py-12">
                    <Bell className="w-12 h-12 mx-auto mb-3 text-muted-foreground" />
                    <p className="text-muted-foreground m-0">No notifications sent yet</p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {conversation.notifications.map((notification) => {
                      const NotifIcon = getNotificationIcon(notification.type);
                      const isDelivered = notification.status === 'delivered';
                      const wasOpened = !!notification.openedAt;

                      return (
                        <Card key={notification.id}>
                          <CardContent className="p-4">
                            <div className="flex items-start justify-between gap-4">
                              <div className="flex items-start gap-3 flex-1">
                                <div className={`p-2 rounded-lg ${
                                  isDelivered 
                                    ? 'bg-[var(--success-bg)] text-[var(--success-text)]'
                                    : 'bg-destructive-bg text-destructive-text'
                                }`}>
                                  <NotifIcon className="w-4 h-4" />
                                </div>
                                <div className="flex-1 space-y-2">
                                  <div className="flex items-center gap-2">
                                    <span className="font-medium">
                                      {formatNotificationType(notification.type)}
                                    </span>
                                    <Badge 
                                      variant={isDelivered ? 'secondary' : 'destructive'}
                                      className={isDelivered 
                                        ? 'bg-[var(--success-solid)]/10 text-[var(--success-solid)]' 
                                        : ''
                                      }
                                    >
                                      {isDelivered ? (
                                        <>
                                          <CheckCircle2 className="w-3 h-3 mr-1" />
                                          Delivered
                                        </>
                                      ) : (
                                        <>
                                          <XCircle className="w-3 h-3 mr-1" />
                                          {notification.status}
                                        </>
                                      )}
                                    </Badge>
                                  </div>
                                  <div className="text-sm text-muted-foreground space-y-1">
                                    <div className="flex items-center gap-2">
                                      <User className="w-3 h-3" />
                                      <span>To: {notification.recipientName}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <Clock className="w-3 h-3" />
                                      <span>Sent: {formatTimestamp(notification.sentAt)}</span>
                                    </div>
                                    {wasOpened && (
                                      <div className="flex items-center gap-2 text-[var(--success-text)]">
                                        <CheckCircle2 className="w-3 h-3" />
                                        <span>Opened: {formatTimestamp(notification.openedAt!)}</span>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </div>
                              <Button
                                variant="outline"
                                size="sm"
                                onClick={() => handleResendNotification(notification.type)}
                              >
                                <Send className="w-3 h-3 mr-2" />
                                Resend
                              </Button>
                            </div>
                          </CardContent>
                        </Card>
                      );
                    })}
                  </div>
                )}

                {/* Notification Stats */}
                {conversation.notifications.length > 0 && (
                  <Card className="mt-6 border-[var(--info-border)] bg-accent">
                    <CardContent className="p-4">
                      <h4 className="mb-3">Notification Statistics</h4>
                      <div className="grid grid-cols-3 gap-4">
                        <div>
                          <p className="text-2xl mb-1">
                            {conversation.notifications.length}
                          </p>
                          <p className="text-sm text-muted-foreground m-0">Total Sent</p>
                        </div>
                        <div>
                          <p className="text-2xl mb-1 text-[var(--success-text)]">
                            {conversation.notifications.filter(n => n.status === 'delivered').length}
                          </p>
                          <p className="text-sm text-muted-foreground m-0">Delivered</p>
                        </div>
                        <div>
                          <p className="text-2xl mb-1 text-[var(--success-text)]">
                            {conversation.notifications.filter(n => n.openedAt).length}
                          </p>
                          <p className="text-sm text-muted-foreground m-0">Opened</p>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                )}
              </div>
            </ScrollArea>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
