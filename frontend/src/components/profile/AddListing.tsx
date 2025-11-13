import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Upload, X } from "lucide-react";

type Step = 1 | 2 | 3;

export function AddListing() {
  const [currentStep, setCurrentStep] = useState<Step>(1);
  const [uploadedImages, setUploadedImages] = useState<string[]>([]);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files) {
      const newImages = Array.from(files).map((file) => URL.createObjectURL(file));
      setUploadedImages([...uploadedImages, ...newImages]);
    }
  };

  const removeImage = (index: number) => {
    setUploadedImages(uploadedImages.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Add New Listing</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          List your tool for rent
        </p>
      </div>

      {/* Progress Indicator */}
      <div className="flex items-center gap-2">
        {[1, 2, 3].map((step) => (
          <div key={step} className="flex items-center flex-1">
            <div className="flex items-center gap-2 flex-1">
              <div 
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm ${
                  currentStep >= step 
                    ? "bg-[var(--primary)] text-[var(--primary-foreground)]"
                    : "bg-muted"
                }`}
              >
                {step}
              </div>
              <span className="text-sm hidden sm:inline">
                {step === 1 && "Basic Info"}
                {step === 2 && "Pricing & Location"}
                {step === 3 && "Photos"}
              </span>
            </div>
            {step < 3 && (
              <div className={`h-0.5 flex-1 mx-2 ${currentStep > step ? "bg-[var(--primary)]" : "bg-muted"}`} />
            )}
          </div>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>
            {currentStep === 1 && "Step 1: Basic Information"}
            {currentStep === 2 && "Step 2: Pricing & Availability"}
            {currentStep === 3 && "Step 3: Upload Photos"}
          </CardTitle>
          <CardDescription>
            {currentStep === 1 && "Tell us about your tool"}
            {currentStep === 2 && "Set your pricing and location"}
            {currentStep === 3 && "Add photos of your tool"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {currentStep === 1 && (
            <>
              <div className="space-y-2">
                <Label htmlFor="title">Tool Title</Label>
                <Input id="title" placeholder="e.g., DeWalt 20V Cordless Drill" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea 
                  id="description" 
                  placeholder="Describe your tool, its condition, and any accessories included..."
                  rows={5}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="category">Category</Label>
                <Select>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a category" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="drills">Drills & Drivers</SelectItem>
                    <SelectItem value="saws">Saws</SelectItem>
                    <SelectItem value="lawn">Lawn & Garden</SelectItem>
                    <SelectItem value="ladders">Ladders & Scaffolding</SelectItem>
                    <SelectItem value="pressure">Pressure Washers</SelectItem>
                    <SelectItem value="other">Other</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          {currentStep === 2 && (
            <>
              <div className="space-y-2">
                <Label htmlFor="price">Price per Day ($)</Label>
                <Input id="price" type="number" placeholder="25" />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="city">City</Label>
                  <Select>
                    <SelectTrigger>
                      <SelectValue placeholder="Select your city" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="edmonton">Edmonton</SelectItem>
                      <SelectItem value="calgary">Calgary</SelectItem>
                      <SelectItem value="other">Other (AB)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="postal">Postal Code</Label>
                  <Input id="postal" placeholder="T5K 2M5" />
                </div>
              </div>
              <div className="space-y-2">
                <Label>Availability</Label>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="available-from">Available From</Label>
                    <Input id="available-from" type="date" />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="available-to">Available To</Label>
                    <Input id="available-to" type="date" />
                  </div>
                </div>
              </div>
            </>
          )}

          {currentStep === 3 && (
            <>
              <div className="space-y-4">
                <Label>Upload Photos</Label>
                <div 
                  className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-[var(--primary)] transition-colors"
                  onClick={() => document.getElementById('file-upload')?.click()}
                >
                  <Upload className="w-12 h-12 mx-auto mb-4" style={{ color: "var(--text-muted)" }} />
                  <p className="mb-2">Click to upload or drag and drop</p>
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    PNG, JPG or WEBP (max. 5MB each)
                  </p>
                  <input
                    id="file-upload"
                    type="file"
                    multiple
                    accept="image/*"
                    className="hidden"
                    onChange={handleImageUpload}
                  />
                </div>

                {uploadedImages.length > 0 && (
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {uploadedImages.map((image, index) => (
                      <div key={index} className="relative aspect-square rounded-lg overflow-hidden bg-muted">
                        <img src={image} alt={`Upload ${index + 1}`} className="w-full h-full object-cover" />
                        <button
                          onClick={() => removeImage(index)}
                          className="absolute top-2 right-2 w-6 h-6 rounded-full bg-destructive text-white flex items-center justify-center hover:bg-destructive/90"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}

          <div className="flex gap-3 pt-4">
            {currentStep > 1 && (
              <Button 
                variant="outline"
                onClick={() => setCurrentStep((currentStep - 1) as Step)}
              >
                Back
              </Button>
            )}
            {currentStep < 3 ? (
              <Button 
                className="bg-[var(--primary)] hover:bg-[var(--primary-hover)] ml-auto"
                style={{ color: "var(--primary-foreground)" }}
                onClick={() => setCurrentStep((currentStep + 1) as Step)}
              >
                Next
              </Button>
            ) : (
              <Button 
                className="bg-[var(--primary)] hover:bg-[var(--primary-hover)] ml-auto"
                style={{ color: "var(--primary-foreground)" }}
              >
                Publish Listing
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}