import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { CreditCard, Plus, Building2 } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { Separator } from "../ui/separator";

export function Payments() {
  const paymentMethods = [
    { type: "Visa", last4: "4242", expiry: "12/25", isDefault: true },
    { type: "Mastercard", last4: "5555", expiry: "08/26", isDefault: false },
  ];

  const transactions = [
    { id: "TXN-001", date: "Jan 12, 2025", description: "Rental Payment - Pressure Washer", amount: 105, status: "Completed" },
    { id: "TXN-002", date: "Jan 10, 2025", description: "Payout to Bank", amount: -280, status: "Completed" },
    { id: "TXN-003", date: "Jan 8, 2025", description: "Rental Payment - Cordless Drill", amount: 45, status: "Completed" },
    { id: "TXN-004", date: "Jan 5, 2025", description: "Rental Payment - Chainsaw", amount: 120, status: "Pending" },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Payments</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Manage payment methods and view transaction history
        </p>
      </div>

      {/* Payment Methods */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Payment Methods</CardTitle>
            <CardDescription>Manage your saved payment methods</CardDescription>
          </div>
          <Button 
            size="sm"
            className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
            style={{ color: "var(--primary-foreground)" }}
          >
            <Plus className="w-4 h-4 mr-2" />
            Add Card
          </Button>
        </CardHeader>
        <CardContent className="space-y-4">
          {paymentMethods.map((method, index) => (
            <div key={index}>
              {index > 0 && <Separator className="my-4" />}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center">
                    <CreditCard className="w-6 h-6" style={{ color: "var(--text-muted)" }} />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <p>{method.type} ending in {method.last4}</p>
                      {method.isDefault && (
                        <Badge variant="secondary" className="text-xs">Default</Badge>
                      )}
                    </div>
                    <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                      Expires {method.expiry}
                    </p>
                  </div>
                </div>
                <div className="flex gap-2">
                  {!method.isDefault && (
                    <Button variant="ghost" size="sm">
                      Set as Default
                    </Button>
                  )}
                  <Button variant="ghost" size="sm" className="text-destructive">
                    Remove
                  </Button>
                </div>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {/* Payout Method */}
      <Card>
        <CardHeader>
          <CardTitle>Payout Method</CardTitle>
          <CardDescription>Where you receive your earnings</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-lg bg-muted flex items-center justify-center">
                <Building2 className="w-6 h-6" style={{ color: "var(--text-muted)" }} />
              </div>
              <div>
                <p>Bank Account</p>
                <p className="text-sm mt-1" style={{ color: "var(--text-muted)" }}>
                  Account ending in 7890
                </p>
              </div>
            </div>
            <Button variant="outline" size="sm">
              Update
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Transaction History */}
      <Card>
        <CardHeader>
          <CardTitle>Transaction History</CardTitle>
          <CardDescription>Your recent payment activity</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Transaction ID</TableHead>
                <TableHead>Date</TableHead>
                <TableHead>Description</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {transactions.map((txn) => (
                <TableRow key={txn.id}>
                  <TableCell className="font-mono text-sm">{txn.id}</TableCell>
                  <TableCell>{txn.date}</TableCell>
                  <TableCell>{txn.description}</TableCell>
                  <TableCell>
                    <Badge variant={txn.status === "Completed" ? "secondary" : "default"}>
                      {txn.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <span className={txn.amount > 0 ? "text-green-600" : ""}>
                      {txn.amount > 0 ? "+" : ""}${Math.abs(txn.amount)}
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
