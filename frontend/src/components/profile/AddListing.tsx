import { useEffect, useRef, useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../ui/card";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../ui/select";
import { Alert, AlertDescription, AlertTitle } from "../ui/alert";
import { Upload, X } from "lucide-react";
import {
  listingsAPI,
  type CreateListingPayload,
  type ListingCategory,
  type JsonError,
} from "@/lib/api";
import { AuthStore } from "@/lib/auth";

type Step = 1 | 2 | 3;
type UploadImage = { file: File; previewUrl: string };

export function AddListing() {
  const [currentStep, setCurrentStep] = useState<Step>(1);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [categorySlug, setCategorySlug] = useState<CreateListingPayload["category"]>(
    undefined,
  );
  const [pricePerDay, setPricePerDay] = useState("");
  const [replacementValue, setReplacementValue] = useState("");
  const [damageDeposit, setDamageDeposit] = useState("");
  const [city, setCity] = useState<CreateListingPayload["city"]>("Edmonton");
  const [postalCode, setPostalCode] = useState(() => AuthStore.getCurrentUser()?.postal_code ?? "");
  const [categories, setCategories] = useState<ListingCategory[]>([]);
  const [loadingCategories, setLoadingCategories] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [uploadedImages, setUploadedImages] = useState<UploadImage[]>([]);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoadingCategories(true);
    listingsAPI
      .categories()
      .then((data) => {
        if (mounted) {
          setCategories(data);
        }
      })
      .catch(() => {
        // Swallow errors to avoid crashing the flow.
      })
      .finally(() => {
        if (mounted) {
          setLoadingCategories(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const profile = AuthStore.getCurrentUser();
    if (profile?.postal_code) {
      setPostalCode((prev) => (prev ? prev : profile.postal_code ?? ""));
    }
  }, []);

  const goToNextStep = () => {
    setError(null);
    setSuccess(null);
    if (currentStep === 1) {
      if (!title.trim()) {
        setError("Title is required.");
        return;
      }
      if (!description.trim()) {
        setError("Description is required.");
        return;
      }
      setCurrentStep(2);
      return;
    }

    if (currentStep === 2) {
      const price = Number(pricePerDay);
      if (!price || price <= 0) {
        setError("Price per day must be greater than zero.");
        return;
      }
      if (!replacementValue.trim()) {
        setError("Replacement value is required.");
        return;
      }
      const replacement = Number(replacementValue);
      if (!Number.isFinite(replacement) || replacement < 0) {
        setError("Replacement value cannot be negative.");
        return;
      }
      if (!damageDeposit.trim()) {
        setError("Damage deposit is required.");
        return;
      }
      const deposit = Number(damageDeposit);
      if (!Number.isFinite(deposit) || deposit < 0) {
        setError("Damage deposit cannot be negative.");
        return;
      }
      if (!city.trim()) {
        setError("City is required.");
        return;
      }
      if (!postalCode.trim()) {
        setError("Postal code is required.");
        return;
      }
      setCurrentStep(3);
    }
  };

  const goToPreviousStep = () => {
    setError(null);
    setSuccess(null);
    setCurrentStep((step) => {
      if (step <= 1) {
        return 1;
      }
      return (step - 1) as Step;
    });
  };

  const handleImageUpload = (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files) {
      return;
    }
    const newUploads = Array.from(files).map((file) => ({
      file,
      previewUrl: URL.createObjectURL(file),
    }));
    setUploadedImages((prev) => [...prev, ...newUploads]);
    event.target.value = "";
  };

  const removeImage = (index: number) => {
    setUploadedImages((prev) => {
      const toRemove = prev[index];
      if (toRemove) {
        URL.revokeObjectURL(toRemove.previewUrl);
      }
      return prev.filter((_, i) => i !== index);
    });
  };

  const resetForm = () => {
    setTitle("");
    setDescription("");
    setCategorySlug(undefined);
    setPricePerDay("");
    setReplacementValue("");
    setDamageDeposit("");
    setCity("Edmonton");
    setPostalCode("");
    setError(null);
    setCurrentStep(1);
    setUploadedImages((prev) => {
      prev.forEach((img) => URL.revokeObjectURL(img.previewUrl));
      return [];
    });
  };

  const handlePublish = async () => {
    setError(null);
    setSuccess(null);
    const price = Number(pricePerDay);
    if (!price || price <= 0) {
      setError("Price per day must be greater than zero.");
      return;
    }
    if (!replacementValue.trim()) {
      setError("Replacement value is required.");
      return;
    }
    const parsedReplacement = Number(replacementValue);
    if (!Number.isFinite(parsedReplacement) || parsedReplacement < 0) {
      setError("Replacement value cannot be negative.");
      return;
    }
    if (!damageDeposit.trim()) {
      setError("Damage deposit is required.");
      return;
    }
    const parsedDeposit = Number(damageDeposit);
    if (!Number.isFinite(parsedDeposit) || parsedDeposit < 0) {
      setError("Damage deposit cannot be negative.");
      return;
    }
    if (!postalCode.trim()) {
      setError("Postal code is required.");
      return;
    }
    if (uploadedImages.length === 0) {
      setError("Please upload at least one photo before publishing.");
      return;
    }
    setSubmitting(true);
    try {
      const replacementNumber = parsedReplacement;
      const depositNumber = parsedDeposit;
      const payload: CreateListingPayload = {
        title: title.trim(),
        description: description.trim(),
        category: categorySlug ?? null,
        daily_price_cad: price,
        replacement_value_cad: replacementNumber,
        damage_deposit_cad: depositNumber,
        city: city.trim() || "Edmonton",
        is_available: true,
      };
      const listing = await listingsAPI.create(payload);

      for (const upload of uploadedImages) {
        try {
          const presign = await listingsAPI.presignPhoto(listing.id, {
            filename: upload.file.name,
            content_type: upload.file.type || "application/octet-stream",
            size: upload.file.size,
          });
          const uploadHeaders: Record<string, string> = {
            ...presign.headers,
          };
          if (upload.file.type) {
            uploadHeaders["Content-Type"] = upload.file.type;
          }
          const uploadResponse = await fetch(presign.upload_url, {
            method: "PUT",
            headers: uploadHeaders,
            body: upload.file,
          });
          if (!uploadResponse.ok) {
            console.warn("Photo upload failed", uploadResponse.statusText);
            continue;
          }
          const etagHeader = uploadResponse.headers.get("ETag") ?? uploadResponse.headers.get("etag") ?? "";
          await listingsAPI.completePhoto(listing.id, {
            key: presign.key,
            etag: etagHeader.replace(/"/g, ""),
            filename: upload.file.name,
            content_type: upload.file.type || "application/octet-stream",
            size: upload.file.size,
          });
        } catch (photoError) {
          console.warn("Photo upload error", photoError);
        }
      }

      setSuccess("Listing added successfully.");
      resetForm();
    } catch (publishError) {
      console.error(publishError);
      let message =
        "Something went wrong while publishing your listing. Please try again.";
      const err = publishError as JsonError;
      if (err?.data && typeof err.data === "object" && err.data !== null) {
        const data = err.data as {
          detail?: string;
          non_field_errors?: string[];
        };
        if (data.detail) {
          message = data.detail;
        } else if (Array.isArray(data.non_field_errors) && data.non_field_errors[0]) {
          message = data.non_field_errors[0];
        }
      }
      setError(message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl">Add New Listing</h1>
        <p className="mt-2" style={{ color: "var(--text-muted)" }}>
          List your tool for rent
        </p>
      </div>

      {success && (
        <Alert className="border-green-200 bg-green-50 text-green-900">
          <AlertTitle>Success</AlertTitle>
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

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
            {currentStep === 2 && "Step 2: Pricing & Location"}
            {currentStep === 3 && "Step 3: Upload Photos"}
          </CardTitle>
          <CardDescription>
            {currentStep === 1 && "Tell us about your tool"}
            {currentStep === 2 && "Set your pricing and location"}
            {currentStep === 3 && "Add photos of your tool"}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {error && <p className="text-sm text-destructive">{error}</p>}
          {currentStep === 1 && (
            <>
              <div className="space-y-2">
                <Label htmlFor="title">Tool Title</Label>
                <Input
                  id="title"
                  placeholder="e.g., DeWalt 20V Cordless Drill"
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Description</Label>
                <Textarea
                  id="description"
                  placeholder="Describe your tool, its condition, and any accessories included..."
                  rows={5}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="category">Category</Label>
                <Select value={categorySlug ?? undefined} onValueChange={setCategorySlug}>
                  <SelectTrigger>
                    <SelectValue
                      placeholder={loadingCategories ? "Loading categories..." : "Select a category"}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {!loadingCategories &&
                      categories.map((category) => (
                        <SelectItem key={category.id} value={category.slug}>
                          {category.name}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            </>
          )}

          {currentStep === 2 && (
            <>
              <div className="space-y-2">
                <Label htmlFor="price">Price per Day ($)</Label>
                <Input
                  id="price"
                  type="number"
                  placeholder="25"
                  value={pricePerDay}
                  onChange={(event) => setPricePerDay(event.target.value)}
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="city">City</Label>
                  <Select value={city} onValueChange={setCity}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select your city" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="Edmonton">Edmonton</SelectItem>
                      <SelectItem value="Calgary">Calgary</SelectItem>
                      <SelectItem value="Other (AB)">Other (AB)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="postal">Postal Code</Label>
                  <Input
                    id="postal"
                    placeholder="T5K 2M5"
                    value={postalCode}
                    onChange={(event) => setPostalCode(event.target.value)}
                  />
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="replacement">Replacement Value ($)</Label>
                  <Input
                    id="replacement"
                    type="number"
                    placeholder="200"
                    min="0"
                    value={replacementValue}
                    onChange={(event) => setReplacementValue(event.target.value)}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="deposit">Damage Deposit ($)</Label>
                  <Input
                    id="deposit"
                    type="number"
                    placeholder="50"
                    min="0"
                    value={damageDeposit}
                    onChange={(event) => setDamageDeposit(event.target.value)}
                  />
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
                  onClick={() => fileInputRef.current?.click()}
                >
                  <Upload
                    className="w-12 h-12 mx-auto mb-4"
                    style={{ color: "var(--text-muted)" }}
                  />
                  <p className="mb-2">Click to upload or drag and drop</p>
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>
                    PNG, JPG or WEBP (max. 5MB each)
                  </p>
                  <input
                    ref={fileInputRef}
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
                      <div
                        key={`${image.file.name}-${index}`}
                        className="relative aspect-square rounded-lg overflow-hidden bg-muted"
                      >
                        <img
                          src={image.previewUrl}
                          alt={`Upload ${index + 1}`}
                          className="w-full h-full object-cover"
                        />
                        <button
                          type="button"
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
                onClick={goToPreviousStep}
              >
                Back
              </Button>
            )}
            {currentStep < 3 ? (
              <Button
                className="bg-[var(--primary)] hover:bg-[var(--primary-hover)] ml-auto"
                style={{ color: "var(--primary-foreground)" }}
                onClick={goToNextStep}
                disabled={submitting}
              >
                Next
              </Button>
            ) : (
              <Button
                className="bg-[var(--primary)] hover:bg-[var(--primary-hover)] ml-auto"
                style={{ color: "var(--primary-foreground)" }}
                disabled={submitting}
                onClick={handlePublish}
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
