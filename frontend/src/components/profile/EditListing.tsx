import { useState } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { ArrowLeft, Upload, X, Image as ImageIcon } from "lucide-react";
import { Separator } from "../ui/separator";

interface EditListingProps {
  listingId: number;
  onBackToListings: () => void;
}

export function EditListing({ listingId, onBackToListings }: EditListingProps) {
  // Mock data - in a real app, this would be fetched based on listingId
  const [images, setImages] = useState<string[]>([
    "https://images.unsplash.com/photo-1504148455328-c376907d081c?w=800",
    "https://images.unsplash.com/photo-1572981779307-38b8cabb2407?w=800",
    "https://images.unsplash.com/photo-1530124566582-a618bc2615dc?w=800",
  ]);
  
  const [formData, setFormData] = useState({
    title: "DeWalt 20V Cordless Drill",
    description: "Professional-grade cordless drill with 20V battery, perfect for construction and DIY projects. Includes 2 batteries, charger, and carrying case. The drill features variable speed trigger and 15+1 clutch settings for precise control.",
    pricePerDay: "15",
    damageDeposit: "100",
    replacementValue: "250",
    postalCode: "T5K 2J8",
    city: "Edmonton",
  });

  const handleInputChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>
  ) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }));
  };

  const handleRemoveImage = (index: number) => {
    setImages((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAddImage = () => {
    // In a real app, this would open a file picker
    // For demo purposes, we'll add a placeholder
    const placeholderImage = "https://images.unsplash.com/photo-1581783898377-1c85bf937427?w=800";
    setImages((prev) => [...prev, placeholderImage]);
  };

  const handleSave = () => {
    // In a real app, this would save to the backend
    console.log("Saving listing:", { ...formData, images });
    onBackToListings();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={onBackToListings}
          className="rounded-full"
        >
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Listings
        </Button>
      </div>

      <div>
        <h1 className="text-3xl">Edit Listing</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          Update your listing information
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column - Images */}
        <div className="lg:col-span-2 space-y-6">
          {/* Images Section */}
          <Card>
            <CardHeader>
              <CardTitle>Listing Images</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Image Grid */}
              <div className="grid grid-cols-2 gap-4">
                {images.map((image, index) => (
                  <div
                    key={index}
                    className="relative aspect-video rounded-xl overflow-hidden bg-muted border border-border group"
                  >
                    <img
                      src={image}
                      alt={`Listing ${index + 1}`}
                      className="w-full h-full object-cover"
                    />
                    {index === 0 && (
                      <div className="absolute top-2 left-2 bg-primary text-primary-foreground px-2 py-1 rounded-md text-xs">
                        Primary
                      </div>
                    )}
                    <button
                      onClick={() => handleRemoveImage(index)}
                      className="absolute top-2 right-2 bg-destructive text-destructive-foreground p-1.5 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}

                {/* Add Image Button */}
                {images.length < 6 && (
                  <button
                    onClick={handleAddImage}
                    className="aspect-video rounded-xl border-2 border-dashed border-border hover:border-primary hover:bg-primary/5 transition-colors flex flex-col items-center justify-center gap-2"
                  >
                    <Upload className="w-6 h-6 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">
                      Add Image
                    </span>
                  </button>
                )}
              </div>

              <p className="text-sm text-muted-foreground">
                Upload up to 6 images. The first image will be the primary photo.
              </p>
            </CardContent>
          </Card>

          {/* Basic Information */}
          <Card>
            <CardHeader>
              <CardTitle>Basic Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="title">Title</Label>
                <Input
                  id="title"
                  name="title"
                  value={formData.title}
                  onChange={handleInputChange}
                  placeholder="Enter listing title"
                  className="rounded-xl"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  name="description"
                  value={formData.description}
                  onChange={handleInputChange}
                  placeholder="Describe your item..."
                  rows={6}
                  className="rounded-xl resize-none"
                />
              </div>
            </CardContent>
          </Card>

          {/* Location */}
          <Card>
            <CardHeader>
              <CardTitle>Location</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="city">City</Label>
                  <Input
                    id="city"
                    name="city"
                    value={formData.city}
                    onChange={handleInputChange}
                    placeholder="Enter city"
                    className="rounded-xl"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="postalCode">Postal Code</Label>
                  <Input
                    id="postalCode"
                    name="postalCode"
                    value={formData.postalCode}
                    onChange={handleInputChange}
                    placeholder="Enter postal code"
                    className="rounded-xl"
                  />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column - Pricing */}
        <div className="space-y-6">
          <Card className="sticky top-24">
            <CardHeader>
              <CardTitle>Pricing</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="pricePerDay">Price per Day</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                    $
                  </span>
                  <Input
                    id="pricePerDay"
                    name="pricePerDay"
                    type="number"
                    value={formData.pricePerDay}
                    onChange={handleInputChange}
                    placeholder="0.00"
                    className="rounded-xl pl-7"
                  />
                </div>
              </div>

              <Separator />

              <div className="space-y-2">
                <Label htmlFor="damageDeposit">Damage Deposit</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                    $
                  </span>
                  <Input
                    id="damageDeposit"
                    name="damageDeposit"
                    type="number"
                    value={formData.damageDeposit}
                    onChange={handleInputChange}
                    placeholder="0.00"
                    className="rounded-xl pl-7"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Refundable security deposit
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="replacementValue">Replacement Value</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                    $
                  </span>
                  <Input
                    id="replacementValue"
                    name="replacementValue"
                    type="number"
                    value={formData.replacementValue}
                    onChange={handleInputChange}
                    placeholder="0.00"
                    className="rounded-xl pl-7"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  Cost to replace if damaged or lost
                </p>
              </div>

              <Separator className="my-6" />

              {/* Action Buttons */}
              <div className="space-y-3">
                <Button
                  onClick={handleSave}
                  className="w-full rounded-full"
                  size="lg"
                >
                  Save Changes
                </Button>
                <Button
                  onClick={onBackToListings}
                  variant="outline"
                  className="w-full rounded-full"
                >
                  Cancel
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}