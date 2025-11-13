import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Edit, Trash2, PlusCircle } from "lucide-react";
import { Badge } from "../ui/badge";

export function YourListings() {
  const listings = [
    {
      id: 1,
      title: "DeWalt 20V Cordless Drill",
      image: "https://images.unsplash.com/photo-1504148455328-c376907d081c?w=400",
      city: "Edmonton",
      price: 15,
      status: "Active"
    },
    {
      id: 2,
      title: "Honda Pressure Washer 3000 PSI",
      image: "https://images.unsplash.com/photo-1581783898377-1c85bf937427?w=400",
      city: "Edmonton",
      price: 35,
      status: "Active"
    },
    {
      id: 3,
      title: "Werner 8ft Step Ladder",
      image: "https://images.unsplash.com/photo-1616401784845-180882ba9ba8?w=400",
      city: "Edmonton",
      price: 12,
      status: "Rented"
    },
    {
      id: 4,
      title: "STIHL Chainsaw MS 170",
      image: "https://images.unsplash.com/photo-1625225233840-695456021cde?w=400",
      city: "Calgary",
      price: 40,
      status: "Active"
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl">Your Listings</h1>
          <p className="mt-2" style={{ color: "var(--text-muted)" }}>
            Manage your tool listings
          </p>
        </div>
        <Button 
          className="bg-[var(--primary)] hover:bg-[var(--primary-hover)]"
          style={{ color: "var(--primary-foreground)" }}
        >
          <PlusCircle className="w-4 h-4 mr-2" />
          Add New Listing
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {listings.map((listing) => (
          <Card key={listing.id} className="overflow-hidden">
            <div className="aspect-video relative overflow-hidden bg-muted">
              <img 
                src={listing.image} 
                alt={listing.title}
                className="w-full h-full object-cover"
              />
              <Badge 
                className="absolute top-3 right-3"
                variant={listing.status === "Active" ? "default" : "secondary"}
              >
                {listing.status}
              </Badge>
            </div>
            <CardHeader>
              <CardTitle className="text-lg">{listing.title}</CardTitle>
              <CardDescription>{listing.city}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-2xl" style={{ color: "var(--primary)" }}>
                    ${listing.price}
                    <span className="text-sm" style={{ color: "var(--text-muted)" }}>/day</span>
                  </p>
                </div>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm">
                    <Edit className="w-4 h-4" />
                  </Button>
                  <Button variant="outline" size="sm">
                    <Trash2 className="w-4 h-4 text-destructive" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
