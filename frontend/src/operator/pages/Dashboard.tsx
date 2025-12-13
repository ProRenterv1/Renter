import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Skeleton } from '../../components/ui/skeleton';
import { Users, Package, Calendar, DollarSign, TrendingUp, AlertCircle } from 'lucide-react';

export function Dashboard() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="mb-2">Dashboard</h1>
        <p className="text-muted-foreground m-0">
          Overview of platform activity and key metrics
        </p>
      </div>

      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          title="Total Users"
          value="Loading..."
          icon={Users}
          trend="+12.5%"
          loading
        />
        <MetricCard
          title="Active Listings"
          value="Loading..."
          icon={Package}
          trend="+8.2%"
          loading
        />
        <MetricCard
          title="Bookings (30d)"
          value="Loading..."
          icon={Calendar}
          trend="+15.3%"
          loading
        />
        <MetricCard
          title="Revenue (30d)"
          value="Loading..."
          icon={DollarSign}
          trend="+22.1%"
          loading
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Activity */}
        <Card>
          <CardHeader>
            <CardTitle>Recent Activity</CardTitle>
            <CardDescription>Latest platform events and user actions</CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={TrendingUp}
              title="No recent activity"
              description="Activity data will appear here once available"
            />
          </CardContent>
        </Card>

        {/* Pending Disputes */}
        <Card>
          <CardHeader>
            <CardTitle>Pending Disputes</CardTitle>
            <CardDescription>Disputes requiring operator attention</CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={AlertCircle}
              title="No pending disputes"
              description="All disputes have been resolved"
            />
          </CardContent>
        </Card>

        {/* Popular Listings */}
        <Card>
          <CardHeader>
            <CardTitle>Popular Listings</CardTitle>
            <CardDescription>Top performing tool listings this week</CardDescription>
          </CardHeader>
          <CardContent>
            <EmptyState
              icon={Package}
              title="No listing data"
              description="Popular listings will be shown here"
            />
          </CardContent>
        </Card>

        {/* System Health */}
        <Card>
          <CardHeader>
            <CardTitle>System Health</CardTitle>
            <CardDescription>Platform performance and uptime</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              <HealthIndicator label="API Status" status="operational" loading />
              <HealthIndicator label="Database" status="operational" loading />
              <HealthIndicator label="Payment Gateway" status="operational" loading />
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

interface MetricCardProps {
  title: string;
  value: string;
  icon: React.ElementType;
  trend?: string;
  loading?: boolean;
}

function MetricCard({ title, icon: Icon, loading }: MetricCardProps) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
        <Icon className="w-4 h-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        {loading ? (
          <>
            <Skeleton className="h-8 w-24 mb-2" />
            <Skeleton className="h-4 w-16" />
          </>
        ) : (
          <>
            <div className="text-2xl mb-1">--</div>
            <p className="text-xs text-muted-foreground m-0">--</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

interface EmptyStateProps {
  icon: React.ElementType;
  title: string;
  description: string;
}

function EmptyState({ icon: Icon, title, description }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8 text-center">
      <Icon className="w-12 h-12 text-muted-foreground mb-3" />
      <h3 className="mb-1">{title}</h3>
      <p className="text-sm text-muted-foreground m-0">{description}</p>
    </div>
  );
}

interface HealthIndicatorProps {
  label: string;
  status: 'operational' | 'degraded' | 'down';
  loading?: boolean;
}

function HealthIndicator({ label, status, loading }: HealthIndicatorProps) {
  const statusColors = {
    operational: 'bg-[var(--success-solid)]',
    degraded: 'bg-[var(--warning-badge)]',
    down: 'bg-destructive',
  };

  return (
    <div className="flex items-center justify-between">
      <span className="text-sm">{label}</span>
      {loading ? (
        <Skeleton className="h-5 w-24" />
      ) : (
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${statusColors[status]}`} />
          <span className="text-sm text-muted-foreground capitalize">{status}</span>
        </div>
      )}
    </div>
  );
}
