import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Card, CardContent } from '../../components/ui/card';
import { Skeleton } from '../../components/ui/skeleton';
import { AlertTriangle, CheckCircle2, Hash, Mail, Phone, Shield, XCircle } from 'lucide-react';
import { DataTable } from '../components/DataTable';
import { FilterBar } from '../components/FilterBar';
import { RightDrawer } from '../components/RightDrawer';
import { LoadingSkeletonTable } from '../components/LoadingSkeletonTable';
import {
  formatOperatorUserName,
  operatorAPI,
  type OperatorUserDetail,
  type OperatorUserListItem,
  type OperatorUserListParams,
} from '../api';
import { copyToClipboard } from '../utils/clipboard';

type AdvancedFilters = {
  canRent: boolean | null;
  canList: boolean | null;
  joinedAfter?: string;
  joinedBefore?: string;
};

function toISODate(value?: string) {
  if (!value) return undefined;
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) {
    return undefined;
  }
  return date.toISOString();
}

function initialsFromUser(user: OperatorUserListItem | OperatorUserDetail) {
  const fullName = `${user.first_name ?? ''} ${user.last_name ?? ''}`.trim();
  if (fullName) {
    return fullName
      .split(' ')
      .filter(Boolean)
      .map((part) => part[0])
      .join('')
      .slice(0, 2)
      .toUpperCase();
  }
  if (user.username) return user.username.slice(0, 2).toUpperCase();
  if (user.email) return user.email[0]?.toUpperCase() ?? 'U';
  return 'U';
}

function formatJoined(dateJoined?: string | null) {
  if (!dateJoined) return '—';
  const parsed = new Date(dateJoined);
  if (Number.isNaN(parsed.getTime())) return '—';
  try {
    return format(parsed, 'PPP');
  } catch {
    return parsed.toLocaleDateString();
  }
}

function formatRiskLevel(level?: string | null) {
  if (!level) return 'Unknown';
  if (level === 'high') return 'High';
  if (level === 'med') return 'Medium';
  if (level === 'low') return 'Low';
  return level;
}

function formatRiskCategory(category?: string | null) {
  if (!category) return 'Unknown';
  return category.charAt(0).toUpperCase() + category.slice(1);
}

export function UsersList() {
  const navigate = useNavigate();
  const [users, setUsers] = useState<OperatorUserListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [searchQuery, setSearchQuery] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [cityFilter, setCityFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [verifiedFilters, setVerifiedFilters] = useState<string[]>([]);
  const [advancedFilters, setAdvancedFilters] = useState<AdvancedFilters>({
    canRent: null,
    canList: null,
  });

  const [selectedUser, setSelectedUser] = useState<OperatorUserListItem | null>(null);
  const [previewUser, setPreviewUser] = useState<OperatorUserDetail | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const previewUserIdRef = useRef<number | null>(null);
  const drawerTitle = previewUser
    ? formatOperatorUserName(previewUser)
    : selectedUser
      ? formatOperatorUserName(selectedUser)
      : 'User';
  const drawerDescription = (() => {
    const user = previewUser ?? selectedUser;
    if (!user) return undefined;
    const parts = [`ID: ${user.id}`];
    if (user.email) parts.push(user.email);
    return parts.join(' • ');
  })();

  // Debounce search input
  useEffect(() => {
    const handle = setTimeout(() => setDebouncedSearch(searchQuery.trim()), 300);
    return () => clearTimeout(handle);
  }, [searchQuery]);

  // Reset to first page when filters/search change
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch, cityFilter, statusFilter, verifiedFilters, advancedFilters]);

  useEffect(() => {
    let cancelled = false;
    const fetchUsers = async () => {
      setLoading(true);
      setError(null);

      const params: OperatorUserListParams = {
        page,
        ordering: 'newest',
      };

      if (cityFilter !== 'all') {
        params.city = cityFilter;
      }
      if (statusFilter !== 'all') {
        params.is_active = statusFilter === 'active';
      }
      if (advancedFilters.canRent !== null) {
        params.can_rent = advancedFilters.canRent;
      }
      if (advancedFilters.canList !== null) {
        params.can_list = advancedFilters.canList;
      }
      if (advancedFilters.joinedAfter) {
        params.date_joined_after = toISODate(advancedFilters.joinedAfter);
      }
      if (advancedFilters.joinedBefore) {
        params.date_joined_before = toISODate(advancedFilters.joinedBefore);
      }

      const normalizedSearch = debouncedSearch.trim();
      if (normalizedSearch) {
        params.name = normalizedSearch;
        if (normalizedSearch.includes('@')) {
          params.email = normalizedSearch;
        } else if (/\d/.test(normalizedSearch)) {
          params.phone = normalizedSearch;
        }
      }
      if (verifiedFilters.includes('email')) {
        params.email_verified = true;
      }
      if (verifiedFilters.includes('phone')) {
        params.phone_verified = true;
      }
      if (verifiedFilters.includes('identity')) {
        params.identity_verified = true;
      }
      params.page_size = pageSize;

      try {
        const data = await operatorAPI.users(params);
        if (cancelled) return;
        if (Array.isArray(data)) {
          setUsers(data);
          setTotal(data.length);
          return;
        }
        const results = Array.isArray(data.results) ? data.results : [];
        const count = typeof data.count === 'number' ? data.count : results.length;
        setUsers(results);
        setTotal(count);
        const nextPageSize = params.page_size ?? results.length ?? pageSize;
        setPageSize(nextPageSize || 10);
      } catch (err) {
        console.error('Failed to load users', err);
        if (cancelled) return;
        setError('Unable to load users. Please try again.');
      } finally {
        if (cancelled) return;
        setLoading(false);
      }
    };

    fetchUsers();
    return () => {
      cancelled = true;
    };
  }, [page, cityFilter, statusFilter, advancedFilters, verifiedFilters, debouncedSearch, pageSize]);

  const cityOptions = useMemo(() => {
    const options: { label: string; value: string }[] = [];
    const seen = new Set<string>();
    users.forEach((user) => {
      if (!user.city) return;
      const city = user.city.trim();
      if (!city || seen.has(city)) return;
      seen.add(city);
      options.push({ label: city, value: city });
    });
    if (options.length === 0) {
      return [
        { label: 'Edmonton', value: 'Edmonton' },
        { label: 'Calgary', value: 'Calgary' },
        { label: 'Toronto', value: 'Toronto' },
      ];
    }
    return options;
  }, [users]);

  const handleToggleVerifiedFilter = (filter: string) => {
    setVerifiedFilters((prev) =>
      prev.includes(filter) ? prev.filter((f) => f !== filter) : [...prev, filter]
    );
  };

  const handleRowClick = (user: OperatorUserListItem) => {
    const targetId = user.id;
    previewUserIdRef.current = targetId;
    setSelectedUser(user);
    setPreviewUser(null);
    setPreviewError(null);
    setPreviewLoading(true);
    setDrawerOpen(true);

    operatorAPI
      .userDetail(targetId)
      .then((data) => {
        if (previewUserIdRef.current !== targetId) return;
        setPreviewUser(data);
      })
      .catch((err) => {
        console.error('Failed to load user preview', err);
        if (previewUserIdRef.current !== targetId) return;
        setPreviewError('Unable to load user details.');
      })
      .finally(() => {
        if (previewUserIdRef.current !== targetId) return;
        setPreviewLoading(false);
      });
  };

  const columns = [
    {
      key: 'user',
      header: 'User',
      cell: (user: OperatorUserListItem) => (
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-primary text-primary-foreground flex items-center justify-center">
            {initialsFromUser(user)}
          </div>
          <div>
            <div className="mb-1">{formatOperatorUserName(user)}</div>
            <div className="text-sm text-muted-foreground">{user.username}</div>
          </div>
        </div>
      ),
    },
    {
      key: 'contact',
      header: 'Contact',
      cell: (user: OperatorUserListItem) => (
        <div className="text-sm">
          <div className="mb-1">{user.email ?? '—'}</div>
          <div className="text-muted-foreground">{user.phone ?? '—'}</div>
        </div>
      ),
    },
    {
      key: 'city',
      header: 'City',
      cell: (user: OperatorUserListItem) => <span className="text-sm">{user.city || '—'}</span>,
    },
    {
      key: 'verified',
      header: 'Verified',
      cell: (user: OperatorUserListItem) => (
        <div className="flex gap-2">
          {user.email_verified && (
            <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 border border-emerald-100">
              <Mail className="w-3 h-3 mr-1" />
              Email
            </Badge>
          )}
          {user.phone_verified && (
            <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 border border-emerald-100">
              <Phone className="w-3 h-3 mr-1" />
              Phone
            </Badge>
          )}
          {user.identity_verified && (
            <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 border border-emerald-100">
              <Shield className="w-3 h-3 mr-1" />
              ID
            </Badge>
          )}
        </div>
      ),
    },
    {
      key: 'permissions',
      header: 'Permissions',
      cell: (user: OperatorUserListItem) => (
        <div className="flex gap-2">
          {user.can_rent ? (
            <CheckCircle2 className="w-4 h-4 text-[var(--success-solid)]" title="Can rent" />
          ) : (
            <XCircle className="w-4 h-4 text-muted-foreground" title="Cannot rent" />
          )}
          {user.can_list ? (
            <CheckCircle2 className="w-4 h-4 text-[var(--success-solid)]" title="Can list" />
          ) : (
            <XCircle className="w-4 h-4 text-muted-foreground" title="Cannot list" />
          )}
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      cell: (user: OperatorUserListItem) => (
        <Badge variant={user.is_active ? 'secondary' : 'destructive'}>
          {user.is_active ? 'Active' : 'Suspended'}
        </Badge>
      ),
    },
    {
      key: 'joined',
      header: 'Joined',
      cell: (user: OperatorUserListItem) => (
        <span className="text-sm text-muted-foreground">{formatJoined(user.date_joined)}</span>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2">Users</h1>
        <p className="text-muted-foreground m-0">
          Manage and monitor user accounts
        </p>
      </div>

      <FilterBar
        searchPlaceholder="Search by name, email, or phone..."
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        cityValue={cityFilter}
        cityOptions={cityOptions}
        onCityChange={setCityFilter}
        statusValue={statusFilter}
        onStatusChange={setStatusFilter}
        verifiedFilters={verifiedFilters}
        onToggleVerified={handleToggleVerifiedFilter}
        advancedFilters={advancedFilters}
        onAdvancedChange={(value) => setAdvancedFilters((prev) => ({ ...prev, ...value }))}
      />

      <Card>
        <CardContent className="p-0">
          {error ? (
            <div className="p-6 text-destructive">{error}</div>
          ) : (
            <>
              {loading && users.length === 0 ? (
                <LoadingSkeletonTable columns={columns.length} />
              ) : (
                <DataTable
                  columns={columns}
                  data={users}
                  isLoading={loading}
                  loadingRows={8}
                  onRowClick={handleRowClick}
                  getRowId={(user) => user.id}
                  getRowClassName={(user) =>
                    user.active_risk_flag ? 'bg-rose-50 hover:bg-rose-100/80' : undefined
                  }
                  page={page}
                  pageSize={pageSize}
                  total={total}
                  onPageChange={setPage}
                  footerContent={
                    <div className="text-sm text-muted-foreground px-4">
                      Showing {users.length} of {total} users
                    </div>
                  }
                />
              )}
            </>
          )}
        </CardContent>
      </Card>

      <RightDrawer
        open={drawerOpen}
        onOpenChange={setDrawerOpen}
        title={drawerTitle}
        description={drawerDescription}
        footer={
          selectedUser ? (
            <div className="flex gap-2 p-4">
              <Button
                className="flex-1"
                onClick={() => navigate(`/operator/users/${selectedUser.id}`)}
              >
                View full profile
              </Button>
              <Button variant="outline" onClick={() => setDrawerOpen(false)}>
                Close
              </Button>
            </div>
          ) : null
        }
      >
        {previewLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-14 w-14 rounded-full" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-4 w-48" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        ) : previewError ? (
          <div className="text-destructive text-sm">{previewError}</div>
        ) : (
          (() => {
            const user = previewUser ?? selectedUser;
            if (!user) return null;
            const riskFlag = user.active_risk_flag;
            const levelLabel = riskFlag ? formatRiskLevel(riskFlag.level) : null;
            const categoryLabel = riskFlag ? formatRiskCategory(riskFlag.category) : null;
            const riskNote = riskFlag?.note?.trim();
            const riskMarkedOn = riskFlag?.created_at ? formatJoined(riskFlag.created_at) : null;
            const riskMarkedBy = riskFlag?.created_by_label ?? 'Unknown';
            const tone =
              (riskFlag?.level && riskToneByLevel[riskFlag.level]) || riskToneByLevel['med'] || {
                bg: 'bg-rose-50',
                border: 'border-rose-100',
                text: 'text-rose-900',
                badge: 'bg-rose-100 text-rose-900 border-rose-200',
                chip: 'bg-rose-200/80 text-rose-900 border border-rose-300',
              };
            return (
              <div className="space-y-4">
                <div className="text-xs font-semibold uppercase text-muted-foreground tracking-wide">User Details</div>
                <div className="flex items-start gap-3">
                  <div className="w-14 h-14 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-lg">
                    {initialsFromUser(user)}
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Badge variant={user.is_active ? 'secondary' : 'destructive'}>
                        {user.is_active ? 'Active' : 'Suspended'}
                      </Badge>
                      {user.identity_verified ? (
                        <Badge className="bg-emerald-50 text-emerald-700 border border-emerald-100">
                          <Shield className="w-3 h-3 mr-1" />
                          ID Verified
                        </Badge>
                      ) : null}
                    </div>
                    <div className="mt-2 text-sm text-muted-foreground">
                      Joined {formatJoined(user.date_joined)}
                    </div>
                  </div>
                </div>

                <div className="space-y-3 rounded-xl border border-border bg-muted/40 p-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Hash className="h-4 w-4 text-muted-foreground" />
                      <span>#{user.id}</span>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => copyToClipboard(String(user.id), 'User ID')}
                    >
                      Copy
                    </Button>
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Mail className="h-4 w-4 text-muted-foreground" />
                      <span>{user.email ?? '—'}</span>
                    </div>
                    {user.email ? (
                      <Button variant="ghost" size="icon" onClick={() => copyToClipboard(user.email!, 'Email')}>
                        Copy
                      </Button>
                    ) : null}
                  </div>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Phone className="h-4 w-4 text-muted-foreground" />
                      <span>{user.phone ?? '—'}</span>
                    </div>
                    {user.phone ? (
                      <Button variant="ghost" size="icon" onClick={() => copyToClipboard(user.phone!, 'Phone')}>
                        Copy
                      </Button>
                    ) : null}
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Can rent</span>
                    {user.can_rent ? <CheckCircle2 className="text-[var(--success-solid)] h-4 w-4" /> : <XCircle className="text-muted-foreground h-4 w-4" />}
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Can list</span>
                    {user.can_list ? <CheckCircle2 className="text-[var(--success-solid)] h-4 w-4" /> : <XCircle className="text-muted-foreground h-4 w-4" />}
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-xl border border-border bg-muted/30 p-3">
                    <div className="text-xs uppercase text-muted-foreground mb-1">Bookings</div>
                    <div className="text-lg font-medium">
                      {(user.bookings_as_owner_count ?? 0) + (user.bookings_as_renter_count ?? 0)}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {user.bookings_as_owner_count} as owner · {user.bookings_as_renter_count} as renter
                    </div>
                  </div>
                  <div className="rounded-xl border border-border bg-muted/30 p-3">
                    <div className="text-xs uppercase text-muted-foreground mb-1">Listings</div>
                    <div className="text-lg font-medium">{user.listings_count ?? 0}</div>
                    <div className="text-xs text-muted-foreground">Active tool listings</div>
                  </div>
                </div>

                {riskFlag ? (
                  <div
                    className={`space-y-3 rounded-2xl border p-4 shadow-sm ${tone.bg} ${tone.border} ${tone.text}`}
                  >
                    <div className="flex items-center gap-2">
                      <div className="inline-flex items-center justify-center rounded-full bg-white/60 p-2 border border-white/80">
                        <AlertTriangle className="h-4 w-4" />
                      </div>
                      <div className="font-semibold text-base">Suspicion</div>
                      <Badge variant="outline" className={tone.chip}>
                        {levelLabel}
                      </Badge>
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
                      <div className="rounded-lg bg-white/70 border border-white/80 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
                        <div className="text-[11px] uppercase tracking-wide opacity-70">Level</div>
                        <div className="font-semibold text-base">{levelLabel}</div>
                      </div>
                      <div className="rounded-lg bg-white/70 border border-white/80 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
                        <div className="text-[11px] uppercase tracking-wide opacity-70">Category</div>
                        <div className="font-semibold text-base">{categoryLabel}</div>
                      </div>
                    </div>
                    <div className="rounded-lg bg-white/70 border border-white/80 p-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.4)]">
                      <div className="text-[11px] uppercase tracking-wide opacity-70 mb-1">Description</div>
                      <p className="m-0 text-sm">{riskNote || 'No note provided.'}</p>
                    </div>
                    <div className="text-xs opacity-80">
                      Marked by {riskMarkedBy}
                      {riskMarkedOn ? ` · ${riskMarkedOn}` : ''}
                    </div>
                  </div>
                ) : null}
              </div>
            );
          })()
        )}
      </RightDrawer>
    </div>
  );
}
const riskToneByLevel: Record<string, { bg: string; border: string; text: string; badge: string; chip: string }> = {
  high: {
    bg: 'bg-gradient-to-br from-rose-50 via-amber-50 to-white',
    border: 'border-rose-200',
    text: 'text-rose-900',
    badge: 'bg-rose-100 text-rose-900 border-rose-200',
    chip: 'bg-rose-200/80 text-rose-900 border border-rose-300',
  },
  med: {
    bg: 'bg-gradient-to-br from-amber-50 via-orange-50 to-white',
    border: 'border-amber-200',
    text: 'text-amber-900',
    badge: 'bg-amber-100 text-amber-900 border-amber-200',
    chip: 'bg-amber-200/70 text-amber-900 border border-amber-300',
  },
  low: {
    bg: 'bg-gradient-to-br from-emerald-50 via-lime-50 to-white',
    border: 'border-emerald-200',
    text: 'text-emerald-900',
    badge: 'bg-emerald-100 text-emerald-900 border-emerald-200',
    chip: 'bg-emerald-200/70 text-emerald-900 border border-emerald-300',
  },
};
