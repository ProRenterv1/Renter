import { useState } from "react";
import { 
  AlertTriangle, 
  ArrowLeft, 
  Calendar, 
  Clock, 
  FileText, 
  Image as ImageIcon,
  MapPin, 
  MessageSquare, 
  Send, 
  Shield, 
  User 
} from "lucide-react";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { Badge } from "../ui/badge";

interface Dispute {
  id: string;
  bookingId: string;
  toolName: string;
  toolImage: string;
  owner: {
    id: string;
    name: string;
    avatar: string;
    verified: boolean;
    rating: number;
  };
  renter: {
    id: string;
    name: string;
    avatar: string;
    verified: boolean;
    rating: number;
  };
  problem: string;
  status: "open" | "in-progress" | "resolved" | "closed";
  dateRange: {
    start: string;
    end: string;
  };
  createdAt: string;
  description: string;
  messages: {
    id: string;
    sender: "owner" | "renter" | "support";
    senderName: string;
    message: string;
    timestamp: string;
  }[];
  evidences: {
    id: string;
    type: "image" | "document";
    url: string;
    uploadedBy: "owner" | "renter";
    uploadedAt: string;
    description: string;
  }[];
}

const mockDisputes: Dispute[] = [
  {
    id: "D001",
    bookingId: "B12345",
    toolName: "Makita Cordless Drill",
    toolImage: "https://images.unsplash.com/photo-1504148455328-c376907d081c?w=400&h=300&fit=crop",
    owner: {
      id: "U001",
      name: "Sarah Mitchell",
      avatar: "",
      verified: true,
      rating: 4.8
    },
    renter: {
      id: "U002",
      name: "John Doe",
      avatar: "",
      verified: true,
      rating: 4.5
    },
    problem: "Tool returned damaged",
    status: "open",
    dateRange: {
      start: "Dec 1, 2025",
      end: "Dec 5, 2025"
    },
    createdAt: "Dec 6, 2025",
    description: "The drill was returned with a cracked battery casing and missing chuck key. The tool was in perfect condition when rented out.",
    messages: [
      {
        id: "M001",
        sender: "owner",
        senderName: "Sarah Mitchell",
        message: "Hi, I noticed the drill came back with significant damage. The battery casing is cracked and the chuck key is missing.",
        timestamp: "Dec 6, 2025 10:30 AM"
      },
      {
        id: "M002",
        sender: "renter",
        senderName: "John Doe",
        message: "I'm sorry about the chuck key - I can return it, I think I left it in my toolbox by mistake. However, the battery casing was already cracked when I picked it up.",
        timestamp: "Dec 6, 2025 11:15 AM"
      },
      {
        id: "M003",
        sender: "support",
        senderName: "Renter Support",
        message: "Thank you both for providing your perspectives. We're reviewing the evidence submitted. Please upload any photos from before/after the rental period.",
        timestamp: "Dec 6, 2025 2:00 PM"
      }
    ],
    evidences: [
      {
        id: "E001",
        type: "image",
        url: "https://images.unsplash.com/photo-1572981779307-38b8cabb2407?w=400&h=300&fit=crop",
        uploadedBy: "owner",
        uploadedAt: "Dec 6, 2025 10:35 AM",
        description: "Photo showing cracked battery casing after return"
      },
      {
        id: "E002",
        type: "image",
        url: "https://images.unsplash.com/photo-1530124566582-a618bc2615dc?w=400&h=300&fit=crop",
        uploadedBy: "owner",
        uploadedAt: "Dec 6, 2025 10:36 AM",
        description: "Missing chuck key - empty storage compartment"
      }
    ]
  },
  {
    id: "D002",
    bookingId: "B12289",
    toolName: "DeWalt Circular Saw",
    toolImage: "https://images.unsplash.com/photo-1572981779307-38b8cabb2407?w=400&h=300&fit=crop",
    owner: {
      id: "U003",
      name: "Mike Johnson",
      avatar: "",
      verified: true,
      rating: 4.9
    },
    renter: {
      id: "U002",
      name: "John Doe",
      avatar: "",
      verified: true,
      rating: 4.5
    },
    problem: "Late return & extra charges dispute",
    status: "in-progress",
    dateRange: {
      start: "Nov 28, 2025",
      end: "Nov 30, 2025"
    },
    createdAt: "Dec 1, 2025",
    description: "Tool was returned 2 days late without prior notification. Renter disputes the late fee charges.",
    messages: [
      {
        id: "M004",
        sender: "owner",
        senderName: "Mike Johnson",
        message: "The saw was supposed to be returned on Nov 30th but I received it on Dec 2nd. I've applied late fees as per our agreement.",
        timestamp: "Dec 1, 2025 9:00 AM"
      },
      {
        id: "M005",
        sender: "renter",
        senderName: "John Doe",
        message: "I messaged you on Nov 29th about needing an extra day and you said it was fine. I don't think the late fees should apply.",
        timestamp: "Dec 1, 2025 10:30 AM"
      },
      {
        id: "M006",
        sender: "owner",
        senderName: "Mike Johnson",
        message: "I agreed to one extra day (Dec 1st), but you returned it on Dec 2nd. That's still one day late from our extended agreement.",
        timestamp: "Dec 1, 2025 11:00 AM"
      },
      {
        id: "M007",
        sender: "support",
        senderName: "Renter Support",
        message: "We're reviewing the message history between both parties to verify the agreed upon return date. This should be resolved within 24-48 hours.",
        timestamp: "Dec 1, 2025 3:30 PM"
      }
    ],
    evidences: [
      {
        id: "E003",
        type: "document",
        url: "#",
        uploadedBy: "renter",
        uploadedAt: "Dec 1, 2025 10:45 AM",
        description: "Screenshot of message conversation about extension"
      }
    ]
  },
  {
    id: "D003",
    bookingId: "B11987",
    toolName: "Pressure Washer 3000 PSI",
    toolImage: "https://images.unsplash.com/photo-1581092918056-0c4c3acd3789?w=400&h=300&fit=crop",
    owner: {
      id: "U002",
      name: "John Doe",
      avatar: "",
      verified: true,
      rating: 4.5
    },
    renter: {
      id: "U004",
      name: "Emily Davis",
      avatar: "",
      verified: true,
      rating: 4.7
    },
    problem: "Tool not as described",
    status: "resolved",
    dateRange: {
      start: "Nov 15, 2025",
      end: "Nov 18, 2025"
    },
    createdAt: "Nov 16, 2025",
    description: "Renter claims the pressure washer was advertised as 3000 PSI but actual unit is only 2000 PSI. Requesting partial refund.",
    messages: [
      {
        id: "M008",
        sender: "renter",
        senderName: "Emily Davis",
        message: "The listing said this was a 3000 PSI pressure washer, but the label on the unit clearly shows it's 2000 PSI. This doesn't meet my project needs.",
        timestamp: "Nov 16, 2025 8:00 AM"
      },
      {
        id: "M009",
        sender: "owner",
        senderName: "John Doe",
        message: "I apologize for the error in the listing. You're right, it is a 2000 PSI model. I must have made a mistake when creating the listing. I'm happy to offer a partial refund.",
        timestamp: "Nov 16, 2025 9:30 AM"
      },
      {
        id: "M010",
        sender: "support",
        senderName: "Renter Support",
        message: "Thank you both for resolving this amicably. We've processed a 30% refund to the renter. Owner, please update your listing with the correct specifications.",
        timestamp: "Nov 16, 2025 2:00 PM"
      }
    ],
    evidences: [
      {
        id: "E004",
        type: "image",
        url: "https://images.unsplash.com/photo-1581092918056-0c4c3acd3789?w=400&h=300&fit=crop",
        uploadedBy: "renter",
        uploadedAt: "Nov 16, 2025 8:05 AM",
        description: "Photo of product label showing 2000 PSI rating"
      }
    ]
  }
];

export function Disputes() {
  const [selectedDispute, setSelectedDispute] = useState<Dispute | null>(null);
  const [newMessage, setNewMessage] = useState("");

  const handleSendMessage = () => {
    if (!newMessage.trim()) return;
    // In a real app, this would send the message to the server
    console.log("Sending message:", newMessage);
    setNewMessage("");
  };

  const handleViewProfile = (userId: string) => {
    // In a real app, this would navigate to the user's profile
    console.log("Navigating to profile:", userId);
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "open":
        return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300";
      case "in-progress":
        return "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300";
      case "resolved":
        return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300";
      case "closed":
        return "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300";
      default:
        return "bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-300";
    }
  };

  if (selectedDispute) {
    return (
      <div>
        <button
          onClick={() => setSelectedDispute(null)}
          className="flex items-center gap-2 mb-6 text-[var(--primary)] hover:underline"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Disputes
        </button>

        <div className="space-y-6">
          {/* Header */}
          <div className="bg-card border rounded-lg p-6">
            <div className="flex items-start justify-between mb-4">
              <div>
                <h2 className="text-2xl mb-2">Dispute #{selectedDispute.id}</h2>
                <p className="text-muted-foreground">Booking #{selectedDispute.bookingId}</p>
              </div>
              <Badge className={getStatusColor(selectedDispute.status)}>
                {selectedDispute.status.replace("-", " ").toUpperCase()}
              </Badge>
            </div>
            
            <div className="flex items-center gap-4 mb-4">
              <img 
                src={selectedDispute.toolImage} 
                alt={selectedDispute.toolName}
                className="w-20 h-20 object-cover rounded-lg"
              />
              <div>
                <h3 className="font-medium">{selectedDispute.toolName}</h3>
                <p className="text-sm text-muted-foreground">{selectedDispute.problem}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-4 border-t">
              <div className="flex items-center gap-2 text-sm">
                <Calendar className="w-4 h-4 text-muted-foreground" />
                <span>Rental: {selectedDispute.dateRange.start} - {selectedDispute.dateRange.end}</span>
              </div>
              <div className="flex items-center gap-2 text-sm">
                <Clock className="w-4 h-4 text-muted-foreground" />
                <span>Dispute opened: {selectedDispute.createdAt}</span>
              </div>
            </div>
          </div>

          {/* Parties Involved */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Owner */}
            <div className="bg-card border rounded-lg p-4">
              <h3 className="text-sm text-muted-foreground mb-3">Tool Owner</h3>
              <div className="flex items-center gap-3">
                <Avatar className="w-12 h-12">
                  <AvatarImage src={selectedDispute.owner.avatar} />
                  <AvatarFallback className="bg-[var(--primary)]" style={{ color: "var(--primary-foreground)" }}>
                    {selectedDispute.owner.name.split(" ").map(n => n[0]).join("")}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium">{selectedDispute.owner.name}</h4>
                    {selectedDispute.owner.verified && (
                      <Shield className="w-4 h-4 text-green-600" />
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">Rating: {selectedDispute.owner.rating} ⭐</p>
                </div>
                <button
                  onClick={() => handleViewProfile(selectedDispute.owner.id)}
                  className="px-3 py-1.5 text-sm bg-[var(--primary)] text-[var(--primary-foreground)] rounded-lg hover:opacity-90 transition-opacity"
                >
                  View Profile
                </button>
              </div>
            </div>

            {/* Renter */}
            <div className="bg-card border rounded-lg p-4">
              <h3 className="text-sm text-muted-foreground mb-3">Renter</h3>
              <div className="flex items-center gap-3">
                <Avatar className="w-12 h-12">
                  <AvatarImage src={selectedDispute.renter.avatar} />
                  <AvatarFallback className="bg-[var(--primary)]" style={{ color: "var(--primary-foreground)" }}>
                    {selectedDispute.renter.name.split(" ").map(n => n[0]).join("")}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h4 className="font-medium">{selectedDispute.renter.name}</h4>
                    {selectedDispute.renter.verified && (
                      <Shield className="w-4 h-4 text-green-600" />
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">Rating: {selectedDispute.renter.rating} ⭐</p>
                </div>
                <button
                  onClick={() => handleViewProfile(selectedDispute.renter.id)}
                  className="px-3 py-1.5 text-sm bg-[var(--primary)] text-[var(--primary-foreground)] rounded-lg hover:opacity-90 transition-opacity"
                >
                  View Profile
                </button>
              </div>
            </div>
          </div>

          {/* Description */}
          <div className="bg-card border rounded-lg p-6">
            <h3 className="font-medium mb-2">Dispute Description</h3>
            <p className="text-muted-foreground">{selectedDispute.description}</p>
          </div>

          {/* Evidence */}
          {selectedDispute.evidences.length > 0 && (
            <div className="bg-card border rounded-lg p-6">
              <h3 className="font-medium mb-4">Evidence Submitted</h3>
              <div className="space-y-4">
                {selectedDispute.evidences.map((evidence) => (
                  <div key={evidence.id} className="border rounded-lg p-4">
                    <div className="flex items-start gap-4">
                      {evidence.type === "image" ? (
                        <img 
                          src={evidence.url} 
                          alt={evidence.description}
                          className="w-32 h-32 object-cover rounded-lg"
                        />
                      ) : (
                        <div className="w-32 h-32 bg-muted rounded-lg flex items-center justify-center">
                          <FileText className="w-12 h-12 text-muted-foreground" />
                        </div>
                      )}
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          {evidence.type === "image" ? (
                            <ImageIcon className="w-4 h-4 text-muted-foreground" />
                          ) : (
                            <FileText className="w-4 h-4 text-muted-foreground" />
                          )}
                          <span className="font-medium capitalize">{evidence.type}</span>
                          <Badge variant="outline" className="text-xs">
                            {evidence.uploadedBy === "owner" ? "Owner" : "Renter"}
                          </Badge>
                        </div>
                        <p className="text-sm mb-2">{evidence.description}</p>
                        <p className="text-xs text-muted-foreground">
                          Uploaded: {evidence.uploadedAt}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chat */}
          <div className="bg-card border rounded-lg">
            <div className="p-6 border-b">
              <h3 className="font-medium flex items-center gap-2">
                <MessageSquare className="w-5 h-5" />
                Dispute Conversation
              </h3>
            </div>
            
            <div className="p-6 space-y-4 max-h-96 overflow-y-auto">
              {selectedDispute.messages.map((message) => (
                <div 
                  key={message.id} 
                  className={`flex gap-3 ${message.sender === "support" ? "bg-muted/50 -mx-6 px-6 py-4" : ""}`}
                >
                  <Avatar className="w-8 h-8">
                    <AvatarFallback className={message.sender === "support" ? "bg-orange-500 text-white" : "bg-[var(--primary)]"} style={message.sender !== "support" ? { color: "var(--primary-foreground)" } : {}}>
                      {message.sender === "support" ? "RS" : message.senderName.split(" ").map(n => n[0]).join("")}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-medium text-sm">{message.senderName}</span>
                      {message.sender === "support" && (
                        <Badge variant="secondary" className="text-xs">Support Team</Badge>
                      )}
                      <span className="text-xs text-muted-foreground">{message.timestamp}</span>
                    </div>
                    <p className="text-sm">{message.message}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="p-4 border-t">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSendMessage()}
                  placeholder="Type your message..."
                  className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--primary)] bg-background"
                />
                <button
                  onClick={handleSendMessage}
                  className="px-4 py-2 bg-[var(--primary)] text-[var(--primary-foreground)] rounded-lg hover:opacity-90 transition-opacity flex items-center gap-2"
                >
                  <Send className="w-4 h-4" />
                  Send
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl mb-2">Disputes</h2>
        <p className="text-muted-foreground">
          View and manage your rental disputes. Our support team is here to help resolve any issues.
        </p>
      </div>

      {mockDisputes.length === 0 ? (
        <div className="bg-card border rounded-lg p-12 text-center">
          <AlertTriangle className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
          <h3 className="font-medium mb-2">No Disputes</h3>
          <p className="text-muted-foreground">
            You don't have any active disputes. We hope your rentals continue to go smoothly!
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {mockDisputes.map((dispute) => (
            <div
              key={dispute.id}
              onClick={() => setSelectedDispute(dispute)}
              className="bg-card border rounded-lg p-6 hover:border-[var(--primary)] transition-colors cursor-pointer"
            >
              <div className="flex items-start gap-4">
                <img 
                  src={dispute.toolImage} 
                  alt={dispute.toolName}
                  className="w-24 h-24 object-cover rounded-lg"
                />
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between mb-2">
                    <div>
                      <h3 className="font-medium mb-1">{dispute.toolName}</h3>
                      <p className="text-sm text-muted-foreground">Booking #{dispute.bookingId}</p>
                    </div>
                    <Badge className={getStatusColor(dispute.status)}>
                      {dispute.status.replace("-", " ")}
                    </Badge>
                  </div>

                  <div className="flex items-center gap-2 mb-3">
                    <AlertTriangle className="w-4 h-4 text-orange-500" />
                    <span className="font-medium text-sm">{dispute.problem}</span>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                    <div className="flex items-center gap-2">
                      <User className="w-4 h-4 text-muted-foreground" />
                      <span className="text-muted-foreground">Owner:</span>
                      <span>{dispute.owner.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <User className="w-4 h-4 text-muted-foreground" />
                      <span className="text-muted-foreground">Renter:</span>
                      <span>{dispute.renter.name}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <Calendar className="w-4 h-4 text-muted-foreground" />
                      <span className="text-muted-foreground">Opened:</span>
                      <span>{dispute.createdAt}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
