import { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { Button } from '../../components/ui/button';
import { Skeleton } from '../../components/ui/skeleton';
import { 
  Users, 
  Package, 
  Calendar, 
  DollarSign, 
  AlertTriangle,
  Clock,
  Scale,
  XCircle,
  ChevronRight
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { formatCurrency, parseMoney } from '@/lib/utils';
import { operatorAPI, type OperatorDashboardMetrics } from '../api';

export function Dashboard() {
  const navigate = useNavigate();
  const [metrics, setMetrics] = useState<OperatorDashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    operatorAPI
      .dashboard()
      .then((data) => {
        if (!active) return;
        setMetrics(data);
      })
      .catch((err) => {
        console.error('Failed to load operator dashboard', err);
        if (!active) return;
        setError('Unable to load dashboard metrics right now.');
      })
      .finally(() => {
        if (!active) return;
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const metricsSummary = useMemo(() => {
    const safeMetrics = metrics;
    const sumBookings = (counts: Record<string, number> | undefined | null) =>
      Object.values(counts || {}).reduce((total, value) => total + (Number(value) || 0), 0);
    const todayBookings = sumBookings(safeMetrics?.today?.new_bookings_by_status);
    const weekBookings = sumBookings(safeMetrics?.last_7d?.new_bookings_by_status);

    const gmv7d = parseMoney(safeMetrics?.last_7d?.gmv_approx ?? 0);
    const gmvToday = parseMoney(safeMetrics?.today?.gmv_approx ?? 0);

    const formatChange = (current: number, baseline: number) => {
      if (!baseline && !current) {
        return { text: '0% vs avg', trend: 'up' as const };
      }
      if (!baseline) {
        return { text: '+100% vs avg', trend: 'up' as const };
      }
      const delta = ((current - baseline) / baseline) * 100;
      const rounded = Math.abs(delta) < 0.1 ? 0 : delta;
      const trend = rounded >= 0 ? ('up' as const) : ('down' as const);
      const text = `${rounded >= 0 ? '+' : ''}${rounded.toFixed(1)}% vs avg`;
      return { text, trend };
    };

    const usersChange = formatChange(
      safeMetrics?.today?.new_users ?? 0,
      (safeMetrics?.last_7d?.new_users ?? 0) / 7,
    );
    const listingsChange = formatChange(
      safeMetrics?.today?.new_listings ?? 0,
      (safeMetrics?.last_7d?.new_listings ?? 0) / 7,
    );
    const bookingsChange = formatChange(todayBookings, weekBookings / 7);
    const gmvChange = formatChange(gmvToday, gmv7d / 7);

    return {
      cards: [
        {
          title: 'New Users (7d)',
          value: (safeMetrics?.last_7d?.new_users ?? 0).toLocaleString(),
          change: usersChange.text,
          trend: usersChange.trend,
          icon: Users,
        },
        {
          title: 'New Listings (7d)',
          value: (safeMetrics?.last_7d?.new_listings ?? 0).toLocaleString(),
          change: listingsChange.text,
          trend: listingsChange.trend,
          icon: Package,
        },
        {
          title: 'New Bookings (7d)',
          value: weekBookings.toLocaleString(),
          change: bookingsChange.text,
          trend: bookingsChange.trend,
          icon: Calendar,
        },
        {
          title: 'GMV (7d)',
          value: formatCurrency(gmv7d),
          change: gmvChange.text,
          trend: gmvChange.trend,
          icon: DollarSign,
        },
      ],
      risk: {
        overdue: safeMetrics?.risk?.overdue_bookings_count ?? 0,
        disputed: safeMetrics?.risk?.disputed_bookings_count ?? 0,
      },
      openDisputes: safeMetrics?.open_disputes_count ?? 0,
      rebuttalsDue: safeMetrics?.rebuttals_due_soon_count ?? 0,
    };
  }, [metrics]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2">Dashboard</h1>
        <p className="text-muted-foreground m-0">
          Overview of platform activity and key metrics
        </p>
      </div>

      {error ? (
        <Card>
          <CardContent className="p-6 text-destructive">
            {error}
          </CardContent>
        </Card>
      ) : null}

      {/* Key Metrics Grid - 7 day metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {metricsSummary.cards.map((card) => (
          <MetricCard
            key={card.title}
            title={card.title}
            value={card.value}
            change={card.change}
            icon={card.icon}
            trend={card.trend}
            loading={loading}
          />
        ))}
      </div>

      {/* Risk Tiles Row */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <RiskTile
          title="Overdue Returns"
          count={metricsSummary.risk.overdue}
          severity="high"
          icon={Clock}
          items={[
            {
              text:
                metricsSummary.risk.overdue > 0
                  ? `${metricsSummary.risk.overdue} bookings past end date`
                  : 'No overdue bookings right now',
              meta: 'Bookings ending before today',
            },
          ]}
          loading={loading}
          onViewAll={() => navigate('/operator/bookings?filter=overdue')}
        />
        
        <RiskTile
          title="Disputed Bookings"
          count={metricsSummary.risk.disputed}
          severity="medium"
          icon={Scale}
          items={[
            {
              text:
                metricsSummary.risk.disputed > 0
                  ? `${metricsSummary.risk.disputed} active disputes`
                  : 'No open disputes right now',
              meta: 'Includes intake, rebuttals, and reviews',
            },
          ]}
          loading={loading}
          onViewAll={() => navigate('/operator/disputes')}
        />
        
        <RiskTile
          title="Failed Payments"
          count={0}
          severity="low"
          icon={XCircle}
          items={[
            {
              text: 'No failed payments reported',
              meta: 'Stripe + ledger sync',
            },
          ]}
          loading={loading}
          onViewAll={() => navigate('/operator/finance?filter=failed')}
        />
      </div>

      {/* Dashboard Action Tiles */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <ActionTile
          title="Open Disputes"
          count={metricsSummary.openDisputes}
          description="Disputes requiring immediate attention"
          icon={AlertTriangle}
          variant="warning"
          onClick={() => navigate('/operator/disputes')}
        />
        
        <ActionTile
          title="Rebuttals Due Soon (12h)"
          count={metricsSummary.rebuttalsDue}
          description="Rebuttal deadlines approaching"
          icon={Clock}
          variant="info"
          onClick={() => navigate('/operator/disputes?filter=rebuttals')}
        />
      </div>
    </div>
  );
}

interface MetricCardProps {
  title: string;
  value: string;
  change: string;
  icon: React.ElementType;
  trend: 'up' | 'down';
  loading?: boolean;
}

function MetricCard({ title, value, change, icon: Icon, trend, loading }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-3 w-32" />
          </div>
        ) : (
          <>
            <div className="text-2xl mb-1">{value}</div>
            <p className={`text-xs m-0 ${trend === 'up' ? 'text-[var(--success-solid)]' : 'text-destructive'}`}>
              {change} from previous period
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface RiskTileProps {
  title: string;
  count: number;
  severity: 'high' | 'medium' | 'low';
  icon: React.ElementType;
  items: any[];
  loading?: boolean;
  onViewAll: () => void;
}

function RiskTile({ title, count, severity, icon: Icon, items, onViewAll, loading }: RiskTileProps) {
  const severityColors = {
    high: 'text-destructive',
    medium: 'text-[var(--warning-badge)]',
    low: 'text-muted-foreground',
  };
  const badgeColors = {
    high: 'bg-rose-100 text-rose-700',
    medium: 'bg-amber-100 text-amber-700',
    low: 'bg-slate-100 text-slate-700',
  };

  return (
    <Card className="cursor-pointer hover:border-primary transition-colors h-full" onClick={onViewAll}>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon className={`w-5 h-5 ${severityColors[severity]}`} />
            <CardTitle className="text-base">{title}</CardTitle>
          </div>
          <Badge className={`px-2 py-1 text-xs font-semibold ${badgeColors[severity]}`}>
            {count}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="min-h-[280px] flex flex-col">
        {loading ? (
          <div className="space-y-2 mb-3">
            {Array.from({ length: 3 }).map((_, idx) => (
              <Skeleton key={idx} className="h-10 w-full rounded" />
            ))}
          </div>
        ) : (
          <div className="space-y-2 mb-3 flex-1">
            {items.length === 0 ? (
              <div className="text-sm text-muted-foreground p-3 rounded bg-muted/50">
                No recent alerts
              </div>
            ) : (
              items.slice(0, 5).map((item, index) => (
                <div key={index} className="text-sm p-2 rounded bg-muted/40 hover:bg-muted transition-colors flex items-center justify-between">
                  {item.user && (
                    <>
                      <span className="truncate">{item.user}</span>
                      <span className="text-muted-foreground ml-2">
                        {item.tool && `${item.tool.substring(0, 20)}...`}
                        {item.amount && item.amount}
                        {item.overdueDays && `${item.overdueDays}d overdue`}
                      </span>
                    </>
                  )}
                  {!item.user && !item.booking && (
                    <>
                      <span className="truncate">{item.text}</span>
                      {item.meta ? (
                        <span className="text-muted-foreground ml-2 text-xs">{item.meta}</span>
                      ) : null}
                    </>
                  )}
                </div>
              ))
            )}
          </div>
        )}
        <Button variant="ghost" size="sm" className="w-full" onClick={(e) => { e.stopPropagation(); onViewAll(); }}>
          View all <ChevronRight className="w-4 h-4 ml-1" />
        </Button>
      </CardContent>
    </Card>
  );
}

interface ActionTileProps {
  title: string;
  count: number;
  description: string;
  icon: React.ElementType;
  variant: 'warning' | 'info';
  onClick: () => void;
}

function ActionTile({ title, count, description, icon: Icon, variant, onClick }: ActionTileProps) {
  const variantColors = {
    warning: 'border-[#d9cfc7] bg-[#f5f1ee]',
    info: 'border-[#b7c7d5] bg-[#eef3f7]',
  };

  return (
    <Card 
      className={`cursor-pointer hover:shadow-md transition-all ${variantColors[variant]}`}
      onClick={onClick}
    >
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <Icon className="w-6 h-6 text-foreground" />
              <h3 className="m-0">{title}</h3>
            </div>
            <p className="text-muted-foreground m-0 text-sm">{description}</p>
          </div>
          <div className="text-4xl ml-4">{count}</div>
        </div>
      </CardContent>
    </Card>
  );
}
