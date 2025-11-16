import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "../ui/card";
import { Badge } from "../ui/badge";
import { Button } from "../ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Star } from "lucide-react";

interface BookingRequest {
  id: number;
  toolName: string;
  toolImage: string;
  dateRange: string;
  amount: number;
  status: "pending" | "approved" | "denied";
  renterName: string;
  renterAvatar: string;
  renterRating: number;
  renterReviewCount: number;
}

export function BookingRequests() {
  const [requests, setRequests] = useState<BookingRequest[]>([
    {
      id: 1,
      toolName: "Modern Design Studio",
      toolImage:
        "https://images.unsplash.com/photo-1497366216548-37526070297c?w=400&q=80",
      dateRange: "Jan 20-22, 2025",
      amount: 360,
      status: "pending",
      renterName: "Michael Chen",
      renterAvatar:
        "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=200&q=80",
      renterRating: 4.8,
      renterReviewCount: 23,
    },
    {
      id: 2,
      toolName: "Professional Camera Kit",
      toolImage:
        "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=400&q=80",
      dateRange: "Jan 25-27, 2025",
      amount: 255,
      status: "approved",
      renterName: "Emily Rodriguez",
      renterAvatar:
        "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=200&q=80",
      renterRating: 4.9,
      renterReviewCount: 45,
    },
    {
      id: 3,
      toolName: "Recording Studio Pro",
      toolImage:
        "https://images.unsplash.com/photo-1598488035139-bdbb2231ce04?w=400&q=80",
      dateRange: "Jan 18-19, 2025",
      amount: 300,
      status: "denied",
      renterName: "James Wilson",
      renterAvatar:
        "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=200&q=80",
      renterRating: 4.2,
      renterReviewCount: 12,
    },
    {
      id: 4,
      toolName: "Luxury Event Space",
      toolImage:
        "https://images.unsplash.com/photo-1464366400600-7168b8af9bc3?w=400&q=80",
      dateRange: "Feb 1-3, 2025",
      amount: 1350,
      status: "pending",
      renterName: "Lisa Anderson",
      renterAvatar:
        "https://images.unsplash.com/photo-1487412720507-e7ab37603c6f?w=200&q=80",
      renterRating: 5.0,
      renterReviewCount: 67,
    },
    {
      id: 5,
      toolName: "Cozy Mountain Cabin",
      toolImage:
        "https://images.unsplash.com/photo-1449158743715-0a90ebb6d2d8?w=400&q=80",
      dateRange: "Jan 28-30, 2025",
      amount: 600,
      status: "pending",
      renterName: "David Park",
      renterAvatar:
        "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=200&q=80",
      renterRating: 4.6,
      renterReviewCount: 31,
    },
  ]);

  const [selectedRequest, setSelectedRequest] =
    useState<BookingRequest | null>(null);
  const [statusFilter, setStatusFilter] = useState("all");

  const handleApprove = () => {
    if (selectedRequest) {
      setRequests((prev) =>
        prev.map((req) =>
          req.id === selectedRequest.id ? { ...req, status: "approved" } : req
        )
      );
      setSelectedRequest(null);
    }
  };

  const handleDeny = () => {
    if (selectedRequest) {
      setRequests((prev) =>
        prev.map((req) =>
          req.id === selectedRequest.id ? { ...req, status: "denied" } : req
        )
      );
      setSelectedRequest(null);
    }
  };

  const filteredRequests = requests.filter((request) => {
    if (statusFilter === "all") return true;
    return request.status === statusFilter;
  });

  const getStatusBadge = (status: BookingRequest["status"]) => {
    if (status === "pending") {
      return (
        <Badge variant="outline" className="bg-warning-bg text-warning-text">
          Pending
        </Badge>
      );
    }
    if (status === "approved") {
      return (
        <Badge variant="outline" className="bg-success-bg text-success-text">
          Approved
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="bg-destructive-bg text-destructive-text">
        Denied
      </Badge>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Booking Requests</h1>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>
            Manage booking requests for your listings
          </p>
        </div>
        <div className="flex gap-3">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[140px]">
              <SelectValue placeholder="Status" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All Status</SelectItem>
              <SelectItem value="pending">Pending</SelectItem>
              <SelectItem value="approved">Approved</SelectItem>
              <SelectItem value="denied">Denied</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Booking Requests</CardTitle>
          <CardDescription>
            Review and manage booking requests from renters
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tool Name</TableHead>
                <TableHead>Date Range</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">You Receive</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredRequests.map((request) => (
                <TableRow
                  key={request.id}
                  className="cursor-pointer hover:bg-muted/50"
                  onClick={() => setSelectedRequest(request)}
                >
                  <TableCell>{request.toolName}</TableCell>
                  <TableCell>{request.dateRange}</TableCell>
                  <TableCell>{getStatusBadge(request.status)}</TableCell>
                  <TableCell className="text-right text-green-600">
                    ${request.amount}
                  </TableCell>
                </TableRow>
              ))}
              {filteredRequests.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center py-8">
                    <p style={{ color: "var(--text-muted)" }}>
                      No booking requests found
                    </p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Booking Details Dialog */}
      <Dialog
        open={selectedRequest !== null}
        onOpenChange={(open) => !open && setSelectedRequest(null)}
      >
        <DialogContent className="sm:max-w-[500px]">
          {selectedRequest && (
            <>
              <DialogHeader>
                <DialogTitle>Booking Request Details</DialogTitle>
                <DialogDescription>
                  Review the booking request information
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-6 py-4">
                {/* Tool Info */}
                <div className="flex items-center gap-4">
                  <img
                    src={selectedRequest.toolImage}
                    alt={selectedRequest.toolName}
                    className="w-20 h-20 rounded-xl object-cover border border-border"
                  />
                  <div className="flex-1">
                    <h3
                      className="text-[18px] mb-1"
                      style={{ fontFamily: "Manrope" }}
                    >
                      {selectedRequest.toolName}
                    </h3>
                    <p className="text-muted-foreground">
                      {selectedRequest.dateRange}
                    </p>
                  </div>
                </div>

                <div className="h-px bg-border" />

                {/* Renter Info */}
                <div>
                  <p className="text-sm text-muted-foreground mb-3">
                    Requested by
                  </p>
                  <div className="flex items-center gap-3">
                    <Avatar className="w-12 h-12">
                      <AvatarImage src={selectedRequest.renterAvatar} />
                      <AvatarFallback>
                        {selectedRequest.renterName
                          .split(" ")
                          .map((n) => n[0])
                          .join("")}
                      </AvatarFallback>
                    </Avatar>
                    <div className="flex-1">
                      <p style={{ fontFamily: "Manrope" }}>
                        {selectedRequest.renterName}
                      </p>
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <div className="flex items-center gap-1">
                          <Star className="w-3 h-3 fill-yellow-400 text-yellow-400" />
                          <span className="text-sm">
                            {selectedRequest.renterRating.toFixed(1)}
                          </span>
                        </div>
                        <span className="text-sm">•</span>
                        <span className="text-sm">
                          {selectedRequest.renterReviewCount} reviews
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="h-px bg-border" />

                {/* Booking Details */}
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Date Range</span>
                    <span>{selectedRequest.dateRange}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">Status</span>
                    {getStatusBadge(selectedRequest.status)}
                  </div>
                  <div className="h-px bg-border" />
                  <div className="flex items-center justify-between">
                    <span
                      className="text-[18px]"
                      style={{ fontFamily: "Manrope" }}
                    >
                      You Receive
                    </span>
                    <span
                      className="text-[20px] text-green-600"
                      style={{ fontFamily: "Manrope" }}
                    >
                      ${selectedRequest.amount}
                    </span>
                  </div>
                </div>
              </div>

              {selectedRequest.status === "pending" && (
                <DialogFooter className="gap-2 sm:gap-0">
                  <Button
                    variant="outline"
                    onClick={handleDeny}
                    className="rounded-full"
                  >
                    Deny Booking
                  </Button>
                  <Button onClick={handleApprove} className="rounded-full">
                    Approve Booking
                  </Button>
                </DialogFooter>
              )}

              {selectedRequest.status !== "pending" && (
                <div className="text-center py-2">
                  <p className="text-muted-foreground">
                    This request has been{" "}
                    {selectedRequest.status === "approved"
                      ? "approved"
                      : "denied"}
                  </p>
                </div>
              )}
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
