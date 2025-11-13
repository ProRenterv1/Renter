import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { DollarSign, TrendingUp, Package, Users } from "lucide-react";
import { BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";

export function Statistics() {
  const monthlyData = [
    { month: "Jul", profit: 245 },
    { month: "Aug", profit: 380 },
    { month: "Sep", profit: 290 },
    { month: "Oct", profit: 425 },
    { month: "Nov", profit: 510 },
    { month: "Dec", profit: 390 },
    { month: "Jan", profit: 620 },
  ];

  const rentalData = [
    { month: "Jul", count: 5 },
    { month: "Aug", count: 8 },
    { month: "Sep", count: 6 },
    { month: "Oct", count: 10 },
    { month: "Nov", count: 12 },
    { month: "Dec", count: 9 },
    { month: "Jan", count: 15 },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Statistics</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Track your earnings and performance
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Total Profit</CardTitle>
            <DollarSign className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">$620</div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              <span className="text-green-600">+21.5%</span> from last month
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Total Payouts</CardTitle>
            <TrendingUp className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">$2,860</div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              All-time earnings
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Active Listings</CardTitle>
            <Package className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">4</div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              3 currently rented
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm">Rental Count</CardTitle>
            <Users className="w-4 h-4" style={{ color: "var(--text-muted)" }} />
          </CardHeader>
          <CardContent>
            <div className="text-2xl">15</div>
            <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
              This month
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Monthly Profit</CardTitle>
            <CardDescription>Your earnings over the last 7 months</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={monthlyData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis 
                  dataKey="month" 
                  stroke="#6b7280"
                  fontSize={12}
                />
                <YAxis 
                  stroke="#6b7280"
                  fontSize={12}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'white',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px'
                  }}
                />
                <Bar dataKey="profit" fill="#60B1E0" radius={[8, 8, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Rental Activity</CardTitle>
            <CardDescription>Number of rentals per month</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={rentalData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis 
                  dataKey="month" 
                  stroke="#6b7280"
                  fontSize={12}
                />
                <YAxis 
                  stroke="#6b7280"
                  fontSize={12}
                />
                <Tooltip 
                  contentStyle={{ 
                    backgroundColor: 'white',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px'
                  }}
                />
                <Line 
                  type="monotone" 
                  dataKey="count" 
                  stroke="#5B8CA6" 
                  strokeWidth={2}
                  dot={{ fill: '#5B8CA6', r: 4 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
