import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Badge } from "../ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";

export function RecentRentals() {
  const rentals = [
    {
      id: 1,
      toolName: "DeWalt 20V Cordless Drill",
      rentalPeriod: "Jan 8-10, 2025",
      status: "Completed",
      amount: 45,
      type: "earned"
    },
    {
      id: 2,
      toolName: "Honda Pressure Washer 3000 PSI",
      rentalPeriod: "Jan 12-14, 2025",
      status: "Active",
      amount: 105,
      type: "earned"
    },
    {
      id: 3,
      toolName: "STIHL Chainsaw MS 170",
      rentalPeriod: "Jan 5-7, 2025",
      status: "Completed",
      amount: 120,
      type: "spent"
    },
    {
      id: 4,
      toolName: "Werner 8ft Step Ladder",
      rentalPeriod: "Jan 15-17, 2025",
      status: "Active",
      amount: 36,
      type: "earned"
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Recent Rentals</h1>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>
            Track your rental history
          </p>
        </div>
        <div className="flex gap-3">
          <Select defaultValue="all">
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="active">Active</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
            </SelectContent>
          </Select>
          <Select defaultValue="all">
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Types</SelectItem>
              <SelectItem value="earned">Earned</SelectItem>
              <SelectItem value="spent">Spent</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Rental History</CardTitle>
          <CardDescription>Your recent rental activity</CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tool Name</TableHead>
                <TableHead>Rental Period</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Amount</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rentals.map((rental) => (
                <TableRow key={rental.id}>
                  <TableCell>{rental.toolName}</TableCell>
                  <TableCell>{rental.rentalPeriod}</TableCell>
                  <TableCell>
                    <Badge variant={rental.status === "Active" ? "default" : "secondary"}>
                      {rental.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <span 
                      className={rental.type === "earned" ? "text-green-600" : ""}
                    >
                      {rental.type === "earned" ? "+" : "-"}${rental.amount}
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
