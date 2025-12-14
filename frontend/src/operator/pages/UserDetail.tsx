import { useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../../components/ui/tabs';
import { Skeleton } from '../../components/ui/skeleton';
import { 
  ArrowLeft, 
  Mail, 
  Phone, 
  MapPin, 
  Calendar, 
  Shield, 
  CheckCircle2,
  XCircle,
  Package,
  CalendarCheck,
  DollarSign,
  FileText,
  ClipboardList,
  Lock
} from 'lucide-react';
import { listingsAPI, type Listing } from '@/lib/api';
import { formatCurrency, parseMoney } from '@/lib/utils';
import { formatOperatorUserName, operatorAPI, type OperatorUserDetail, type OperatorBookingSummary } from '../api';
import { copyToClipboard } from '../utils/clipboard';

export function UserDetail() {
  const { userId } = useParams();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState('bookings');
  const [user, setUser] = useState<OperatorUserDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [listingsLoading, setListingsLoading] = useState(false);
  const [listingsError, setListingsError] = useState<string | null>(null);

  const numericUserId = userId ? Number(userId) : null;
  const isValidUserId = Number.isInteger(numericUserId) && (numericUserId ?? 0) > 0;

  useEffect(() => {
    let cancelled = false;
    if (!isValidUserId) {
      setError('The requested user could not be found.');
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    operatorAPI
      .userDetail(numericUserId!)
      .then((data) => {
        if (cancelled) return;
        setUser(data);
      })
      .catch((err) => {
        console.error('Failed to load user detail', err);
        if (cancelled) return;
        setError('The requested user could not be found.');
        setUser(null);
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isValidUserId, numericUserId]);

  useEffect(() => {
    let cancelled = false;
    if (!user?.id) {
      setListings([]);
      return;
    }
    setListingsLoading(true);
    setListingsError(null);
    listingsAPI
      .list({ owner_id: user.id })
      .then((data) => {
        if (cancelled) return;
        setListings(data.results ?? []);
      })
      .catch((err) => {
        console.error('Failed to load listings for user', err);
        if (cancelled) return;
        setListings([]);
        setListingsError('Unable to load listings for this user.');
      })
      .finally(() => {
        if (cancelled) return;
        setListingsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const displayName = useMemo(() => (user ? formatOperatorUserName(user) : 'User'), [user]);
  const initials = useMemo(() => {
    if (!user) return 'U';
    const name = displayName;
    const parts = name.split(' ').filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    if (parts.length === 1) return parts[0][0]?.toUpperCase() ?? 'U';
    if (user.username) return user.username[0]?.toUpperCase() ?? 'U';
    if (user.email) return user.email[0]?.toUpperCase() ?? 'U';
    return 'U';
  }, [displayName, user]);

  const joinedLabel = useMemo(() => {
    if (!user?.date_joined) return '—';
    const parsed = new Date(user.date_joined);
    if (Number.isNaN(parsed.getTime())) return '—';
    try {
      return format(parsed, 'PPP');
    } catch {
      return parsed.toLocaleDateString();
    }
  }, [user?.date_joined]);

  const addressLine = useMemo(() => {
    if (!user) return '—';
    const parts = [user.street_address, user.city, user.province, user.postal_code].filter(Boolean);
    return parts.length ? parts.join(', ') : '—';
  }, [user]);

  if (loading) {
    return <UserDetailSkeleton onBack={() => navigate('/operator/users')} />;
  }

  if (error || !user) {
    return (
      <div className="space-y-6">
        <Button variant="ghost" onClick={() => navigate('/operator/users')}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Users
        </Button>
        <Card>
          <CardContent className="p-12 text-center">
            <h2 className="mb-2">User Not Found</h2>
            <p className="text-muted-foreground">{error || 'The requested user could not be found.'}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const bookings = Array.isArray(user.bookings) ? user.bookings : [];

  return (
    <div className="space-y-6">
      {/* Back Button */}
      <Button variant="ghost" onClick={() => navigate('/operator/users')}>
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Users
      </Button>

      {/* Header Card */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-start gap-6">
            {/* Avatar */}
            <div className="w-20 h-20 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-2xl">
              {initials}
            </div>

            {/* User Info */}
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2 flex-wrap">
                <h1 className="m-0">{displayName}</h1>
                <span className="text-muted-foreground">{user.username}</span>
                <Badge variant={user.is_active ? 'secondary' : 'destructive'}>
                  {user.is_active ? 'Active' : 'Suspended'}
                </Badge>
              </div>

              {/* Role Badges */}
              <div className="flex gap-2 mb-4 flex-wrap">
                {user.can_rent && (
                  <Badge variant="outline" className="capitalize">
                    <CalendarCheck className="w-3 h-3 mr-1" />
                    Renter
                  </Badge>
                )}
                {user.can_list && (
                  <Badge variant="outline" className="capitalize">
                    <Package className="w-3 h-3 mr-1" />
                    Owner
                  </Badge>
                )}
              </div>

              {/* Quick Actions */}
              <div className="flex gap-2 flex-wrap">
                <Button size="sm" variant="outline">View Activity</Button>
                <Button size="sm" variant="outline">Send Message</Button>
                <Button size="sm" variant="outline" className="text-destructive">
                  Suspend Account
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Summary and Verification Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Summary Card */}
        <Card>
          <CardHeader>
            <CardTitle>Contact & Location</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex items-start gap-3">
              <Mail className="w-5 h-5 text-muted-foreground mt-0.5" />
              <div className="flex-1">
                <div className="text-sm text-muted-foreground mb-1">Email</div>
                <div className="flex items-center gap-2">
                  <span>{user.email ?? '—'}</span>
                  {user.email ? (
                    <Button variant="outline" size="sm" onClick={() => copyToClipboard(user.email!, 'Email')}>
                      Copy
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Phone className="w-5 h-5 text-muted-foreground mt-0.5" />
              <div className="flex-1">
                <div className="text-sm text-muted-foreground mb-1">Phone</div>
                <div className="flex items-center gap-2">
                  <span>{user.phone ?? '—'}</span>
                  {user.phone ? (
                    <Button variant="outline" size="sm" onClick={() => copyToClipboard(user.phone!, 'Phone')}>
                      Copy
                    </Button>
                  ) : null}
                </div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 text-muted-foreground mt-0.5" />
              <div className="flex-1">
                <div className="text-sm text-muted-foreground mb-1">Address</div>
                <div>{addressLine}</div>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <Calendar className="w-5 h-5 text-muted-foreground mt-0.5" />
              <div className="flex-1">
                <div className="text-sm text-muted-foreground mb-1">Joined</div>
                <div>{joinedLabel}</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Verification Card */}
        <Card>
          <CardHeader>
            <CardTitle>Verification Status</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <VerificationItem
              icon={Mail}
              label="Email Verified"
              verified={user.email_verified}
            />
            <VerificationItem
              icon={Phone}
              label="Phone Verified"
              verified={user.phone_verified}
            />
            <VerificationItem
              icon={Shield}
              label="Identity Verified"
              verified={user.identity_verified}
            />
            <div className="pt-4 border-t border-border">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-sm text-muted-foreground mb-1">Can Rent</div>
                  <div className="flex items-center gap-2">
                    {user.can_rent ? (
                      <>
                        <CheckCircle2 className="w-5 h-5 text-[var(--success-solid)]" />
                        <span>Enabled</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-5 h-5 text-destructive" />
                        <span>Disabled</span>
                      </>
                    )}
                  </div>
                </div>
                <div>
                  <div className="text-sm text-muted-foreground mb-1">Can List</div>
                  <div className="flex items-center gap-2">
                    {user.can_list ? (
                      <>
                        <CheckCircle2 className="w-5 h-5 text-[var(--success-solid)]" />
                        <span>Enabled</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-5 h-5 text-destructive" />
                        <span>Disabled</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Activity Tabs */}
      <Card>
        <CardHeader>
          <CardTitle>Activity</CardTitle>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-5">
              <TabsTrigger value="bookings">
                <CalendarCheck className="w-4 h-4 mr-2" />
                Bookings
              </TabsTrigger>
              <TabsTrigger value="listings">
                <Package className="w-4 h-4 mr-2" />
                Listings
              </TabsTrigger>
              <TabsTrigger value="finance">
                <Lock className="w-4 h-4 mr-2" />
                Finance
              </TabsTrigger>
              <TabsTrigger value="notes">
                <FileText className="w-4 h-4 mr-2" />
                Notes
              </TabsTrigger>
              <TabsTrigger value="audit">
                <ClipboardList className="w-4 h-4 mr-2" />
                Audit
              </TabsTrigger>
            </TabsList>

            <TabsContent value="bookings" className="mt-6">
              {bookings.length > 0 ? (
                <div className="space-y-3">
                  {bookings.map((booking: OperatorBookingSummary) => (
                    <div key={booking.id} className="p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors flex justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-sm text-muted-foreground">BK-{booking.id}</span>
                          <Badge variant={booking.status?.toLowerCase() === 'completed' ? 'secondary' : 'outline'}>
                            {booking.status || '—'}
                          </Badge>
                        </div>
                        <div className="mb-1 font-medium">{booking.listing_title || 'Listing'}</div>
                        <div className="text-sm text-muted-foreground">
                          {booking.role === 'owner' ? 'Renter' : 'Owner'}: {booking.other_party || '—'}
                        </div>
                      </div>
                      <div className="text-right whitespace-nowrap">
                        <div className="mb-2 text-base">
                          {booking.amount ? formatCurrency(parseMoney(booking.amount)) : '—'}
                        </div>
                        <div className="text-sm text-muted-foreground">
                          {booking.end_date ? format(new Date(booking.end_date), 'yyyy-MM-dd') : '—'}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={CalendarCheck}
                  title="No bookings"
                  description="This user hasn't made or received any bookings yet"
                />
              )}
            </TabsContent>

            <TabsContent value="listings" className="mt-6">
              {listingsLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 3 }).map((_, idx) => (
                    <Skeleton key={idx} className="h-20 w-full rounded-lg" />
                  ))}
                </div>
              ) : listingsError ? (
                <div className="text-destructive text-sm">{listingsError}</div>
              ) : listings.length > 0 ? (
                <div className="space-y-3">
                  {listings.map((listing) => (
                    <div key={listing.id} className="p-4 rounded-lg border border-border hover:bg-muted/50 transition-colors">
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="text-sm text-muted-foreground">#{listing.id}</span>
                            <Badge variant={listing.is_active ? 'default' : 'secondary'}>
                              {listing.is_active ? 'Active' : 'Paused'}
                            </Badge>
                          </div>
                          <div className="mb-1">{listing.title}</div>
                          <div className="text-sm text-muted-foreground">{listing.city}</div>
                        </div>
                        <div className="text-right">
                          <div className="mb-2">
                            {formatCurrency(parseMoney(listing.daily_price_cad))}/day
                          </div>
                          <div className="text-sm text-muted-foreground">
                            {listing.created_at ? `Listed ${format(new Date(listing.created_at), 'PP')}` : '—'}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={Package}
                  title="No listings"
                  description="This user hasn't created any listings yet"
                />
              )}
            </TabsContent>

            <TabsContent value="finance" className="mt-6">
              <LockedState
                icon={DollarSign}
                title="Finance Information"
                description="Financial data requires additional permissions to view"
              />
            </TabsContent>

            <TabsContent value="notes" className="mt-6">
              <EmptyState
                icon={FileText}
                title="No notes"
                description="No operator notes have been added for this user"
              />
            </TabsContent>

            <TabsContent value="audit" className="mt-6">
              <EmptyState
                icon={ClipboardList}
                title="Audit log"
                description="User activity audit log coming soon"
              />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}

interface VerificationItemProps {
  icon: React.ElementType;
  label: string;
  verified: boolean;
}

function VerificationItem({ icon: Icon, label, verified }: VerificationItemProps) {
  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-muted/50">
      <div className="flex items-center gap-3">
        <Icon className="w-5 h-5 text-muted-foreground" />
        <span>{label}</span>
      </div>
      {verified ? (
        <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 border border-emerald-100">
          <CheckCircle2 className="w-3 h-3 mr-1" />
          Verified
        </Badge>
      ) : (
        <Badge variant="secondary" className="bg-muted">
          <XCircle className="w-3 h-3 mr-1" />
          Not Verified
        </Badge>
      )}
    </div>
  );
}

interface EmptyStateProps {
  icon: React.ElementType;
  title: string;
  description: string;
}

function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <Icon className="w-12 h-12 text-muted-foreground mb-3" />
      <h3 className="mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground m-0">{description}</p>
    </div>
  );
}

interface LockedStateProps {
  icon: React.ElementType;
  title: string;
  description: string;
}

function LockedState({ icon: Icon, title, description }: LockedStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-12 text-center">
      <div className="w-16 h-16 rounded-full bg-muted flex items-center justify-center mb-4">
        <Icon className="w-8 h-8 text-muted-foreground" />
      </div>
      <h3 className="mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground m-0 mb-4">{description}</p>
      <Button variant="outline" size="sm">
        Request Access
      </Button>
    </div>
  );
}

function UserDetailSkeleton({ onBack }: { onBack: () => void }) {
  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={onBack}>
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Users
      </Button>
      <Card>
        <CardContent className="p-6 flex gap-6">
          <Skeleton className="w-20 h-20 rounded-full" />
          <div className="flex-1 space-y-3">
            <Skeleton className="h-6 w-40" />
            <Skeleton className="h-4 w-32" />
            <div className="flex gap-2">
              <Skeleton className="h-6 w-20" />
              <Skeleton className="h-6 w-20" />
            </div>
            <div className="flex gap-2">
              <Skeleton className="h-8 w-28" />
              <Skeleton className="h-8 w-28" />
              <Skeleton className="h-8 w-32" />
            </div>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent className="space-y-4">
            {Array.from({ length: 4 }).map((_, idx) => (
              <div key={idx} className="flex items-center gap-3">
                <Skeleton className="h-5 w-5 rounded-full" />
                <div className="flex-1 space-y-2">
                  <Skeleton className="h-3 w-20" />
                  <Skeleton className="h-4 w-32" />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <Skeleton className="h-5 w-40" />
          </CardHeader>
          <CardContent className="space-y-3">
            {Array.from({ length: 3 }).map((_, idx) => (
              <Skeleton key={idx} className="h-12 w-full" />
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-24" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-10 w-full" />
          <div className="mt-4 space-y-2">
            {Array.from({ length: 3 }).map((_, idx) => (
              <Skeleton key={idx} className="h-16 w-full rounded-lg" />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
