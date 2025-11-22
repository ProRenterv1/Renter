import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Upload, X, Image as ImageIcon } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import { Textarea } from "../ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Alert, AlertDescription } from "../ui/alert";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../ui/alert-dialog";
import { Separator } from "../ui/separator";
import {
  listingsAPI,
  type JsonError,
  type Listing,
  type ListingPhoto,
  type UpdateListingPayload,
} from "@/lib/api";
import { ListingPromotionCheckout } from "./ListingPromotionCheckout";

const MAX_PHOTOS = 6;

const normalizePostalCodeInput = (value: string) => {
  const alphanumeric = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!alphanumeric) return "";
  if (alphanumeric.length <= 3) return alphanumeric;
  return `${alphanumeric.slice(0, 3)} ${alphanumeric.slice(3, 6)}`.trim();
};

const sanitizePostalCodeForPayload = (value: string) => normalizePostalCodeInput(value).trim();

function isJsonError(error: unknown): error is JsonError {
  return (
    typeof error === "object" &&
    error !== null &&
    "status" in error &&
    typeof (error as { status?: unknown }).status === "number"
  );
}

function parseJsonError(error: JsonError | null, fallback: string) {
  if (!error || typeof error.data !== "object" || error.data === null) {
    return fallback;
  }
  const data = error.data as Record<string, unknown>;
  if (typeof data.detail === "string") {
    return data.detail;
  }
  for (const value of Object.values(data)) {
    if (Array.isArray(value) && typeof value[0] === "string") {
      return value[0];
    }
  }
  return fallback;
}

type FormState = {
  title: string;
  description: string;
  pricePerDay: string;
  damageDeposit: string;
  replacementValue: string;
  postalCode: string;
  city: string;
};

const mapListingToFormState = (data: Listing): FormState => ({
  title: data.title ?? "",
  description: data.description ?? "",
  pricePerDay: data.daily_price_cad ? String(data.daily_price_cad) : "",
  damageDeposit: data.damage_deposit_cad ? String(data.damage_deposit_cad) : "",
  replacementValue: data.replacement_value_cad ? String(data.replacement_value_cad) : "",
  postalCode: normalizePostalCodeInput(data.postal_code ?? ""),
  city: data.city ?? "",
});

interface EditListingProps {
  listing: Listing;
  onBackToListings: () => void;
  onListingUpdated?: (listing: Listing) => void;
  onListingDeleted?: (listing: Listing) => void;
}

export function EditListing({
  listing,
  onBackToListings,
  onListingUpdated,
  onListingDeleted,
}: EditListingProps) {
  const [currentListing, setCurrentListing] = useState<Listing>(listing);
  const [formData, setFormData] = useState<FormState>(() => mapListingToFormState(listing));
  const [photos, setPhotos] = useState<ListingPhoto[]>(listing.photos ?? []);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [photoUploading, setPhotoUploading] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [mode, setMode] = useState<"edit" | "promote">("edit");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [photosLoading, setPhotosLoading] = useState(true);
  const isMountedRef = useRef(true);
  const isPromoteMode = mode === "promote";

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    setMode("edit");
  }, [listing.id]);

  const refreshPhotos = useCallback(async (slug: string) => {
    if (!slug) return;
    if (isMountedRef.current) {
      setPhotosLoading(true);
    }
    try {
      const allPhotos = await listingsAPI.photos(slug);
      if (isMountedRef.current) {
        setPhotos(allPhotos ?? []);
      }
    } catch {
      // Best-effort; ignore errors.
    } finally {
      if (isMountedRef.current) {
        setPhotosLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    setCurrentListing(listing);
    setFormData(mapListingToFormState(listing));
    setPhotos(listing.photos ?? []);
  }, [listing]);

  function hydrateListing(
    data: Listing,
    options: { resetForm?: boolean; notifyParent?: boolean } = {},
  ) {
    setCurrentListing(data);
    setPhotos(data.photos ?? []);
    if (options.resetForm) {
      setFormData(mapListingToFormState(data));
    }
    if (options.notifyParent) {
      onListingUpdated?.(data);
    }
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    const loadListing = async () => {
      try {
        const data = await listingsAPI.retrieve(listing.slug);
        if (!active) return;
        hydrateListing(data, { resetForm: true });
        setLoadError(null);
         refreshPhotos(data.slug);
      } catch (err) {
        if (!active) return;
        const message = isJsonError(err)
          ? parseJsonError(err, "We could not load this listing. Please try again.")
          : "We could not load this listing. Please try again.";
        setLoadError(message);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    loadListing();
    return () => {
      active = false;
    };
  }, [listing.slug, refreshPhotos]);

  const handleInputChange = (
    event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    const { name, value } = event.target;
    setFormData((prev) => ({
      ...prev,
      [name]: name === "postalCode" ? normalizePostalCodeInput(value) : value,
    }));
  };

  const handleSave = async () => {
    setFormError(null);
    if (!formData.title.trim()) {
      setFormError("Title is required.");
      return;
    }
    if (!formData.description.trim()) {
      setFormError("Description is required.");
      return;
    }
    const price = Number(formData.pricePerDay);
    if (!Number.isFinite(price) || price <= 0) {
      setFormError("Price per day must be greater than zero.");
      return;
    }
    const replacementValue = Number(formData.replacementValue);
    if (!Number.isFinite(replacementValue) || replacementValue <= 0) {
      setFormError("Replacement value must be greater than zero.");
      return;
    }
    const deposit = Number(formData.damageDeposit);
    if (!Number.isFinite(deposit) || deposit < 0) {
      setFormError("Damage deposit cannot be negative.");
      return;
    }
    const normalizedPostalCode = sanitizePostalCodeForPayload(formData.postalCode);
    if (!normalizedPostalCode) {
      setFormError("Postal code is required.");
      return;
    }
    setSaving(true);
    try {
      const payload: UpdateListingPayload = {
        title: formData.title.trim(),
        description: formData.description.trim(),
        daily_price_cad: price,
        replacement_value_cad: replacementValue,
        damage_deposit_cad: deposit,
        city: formData.city.trim(),
        postal_code: normalizedPostalCode,
      };
      const updated = await listingsAPI.update(currentListing.slug, payload);
      hydrateListing(updated, { resetForm: true, notifyParent: true });
      onBackToListings();
    } catch (err) {
      const message = isJsonError(err)
        ? parseJsonError(err, "We couldn't save your changes. Please try again.")
        : "We couldn't save your changes. Please try again.";
      setFormError(message);
    } finally {
      setSaving(false);
    }
  };

  const handleRemovePhoto = async (photoId: number) => {
    setFormError(null);
    try {
      await listingsAPI.deletePhoto(currentListing.slug, photoId);
      setPhotos((prevPhotos) => {
        const nextPhotos = prevPhotos.filter((photo) => photo.id !== photoId);
        setCurrentListing((prev) => {
          const nextListing = { ...prev, photos: nextPhotos };
          onListingUpdated?.(nextListing);
          return nextListing;
        });
        return nextPhotos;
      });
      refreshPhotos(currentListing.slug);
    } catch (err) {
      const message = isJsonError(err)
        ? parseJsonError(err, "Could not delete that photo. Please try again.")
        : "Could not delete that photo. Please try again.";
      setFormError(message);
    }
  };

  const handleUploadPhoto = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setFormError(null);
    setPhotoUploading(true);
    try {
      const presign = await listingsAPI.presignPhoto(currentListing.id, {
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size: file.size,
      });
      const uploadHeaders: Record<string, string> = {
        ...presign.headers,
      };
      if (file.type) {
        uploadHeaders["Content-Type"] = file.type;
      }
      const uploadResponse = await fetch(presign.upload_url, {
        method: "PUT",
        headers: uploadHeaders,
        body: file,
      });
      if (!uploadResponse.ok) {
        throw new Error("Could not upload that photo. Please try again.");
      }
      const etagHeader =
        uploadResponse.headers.get("ETag") ?? uploadResponse.headers.get("etag") ?? "";
      await listingsAPI.completePhoto(currentListing.id, {
        key: presign.key,
        etag: etagHeader.replace(/"/g, ""),
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        size: file.size,
      });
      await refreshPhotos(currentListing.slug);
    } catch (err) {
      if (err instanceof Error && err.message) {
        setFormError(err.message);
      } else {
        const message = isJsonError(err)
          ? parseJsonError(err, "Could not upload that photo. Please try again.")
          : "Could not upload that photo. Please try again.";
        setFormError(message);
      }
    } finally {
      setPhotoUploading(false);
      if (event.target) {
        event.target.value = "";
      }
    }
  };

  const handleDeleteDialogOpenChange = (open: boolean) => {
    if (deleting) return;
    setDeleteDialogOpen(open);
    if (!open) {
      setDeleteError(null);
    }
  };

  const handleDeleteListing = async () => {
    setDeleteError(null);
    setDeleting(true);
    try {
      await listingsAPI.delete(currentListing.slug);
      onListingDeleted?.(currentListing);
      setDeleteDialogOpen(false);
      onBackToListings();
    } catch (err) {
      const message = isJsonError(err)
        ? parseJsonError(err, "We couldn't delete this listing. Please try again.")
        : "We couldn't delete this listing. Please try again.";
      setDeleteError(message);
    } finally {
      setDeleting(false);
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={onBackToListings} className="rounded-full">
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Listings
          </Button>
        </div>
        <p className="text-sm text-muted-foreground">Loading listing details...</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {!isPromoteMode && (
        <>
          <div className="flex items-center gap-4">
            <Button variant="ghost" size="sm" onClick={onBackToListings} className="rounded-full">
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
        </>
      )}

      {isPromoteMode ? (
        <ListingPromotionCheckout listing={currentListing} onBack={() => setMode("edit")} />
      ) : (
        <>
          {loadError && (
            <Alert variant="destructive">
              <AlertDescription>{loadError}</AlertDescription>
            </Alert>
          )}
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>Listing Images</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                {photosLoading && photos.length === 0 && (
                  <div className="col-span-2 flex items-center justify-center rounded-xl border-2 border-dashed border-border p-6 text-sm text-muted-foreground">
                    Loading photos...
                  </div>
                )}
                {!photosLoading && photos.length === 0 && (
                  <div className="col-span-2 flex flex-col items-center justify-center rounded-xl border-2 border-dashed border-border p-6 text-center text-muted-foreground">
                    <ImageIcon className="w-8 h-8 mb-2" />
                    <p>No photos yet. Upload to showcase your listing.</p>
                  </div>
                )}
                {photos.map((photo, index) => (
                  <div
                    key={photo.id}
                    className="relative aspect-video rounded-xl overflow-hidden bg-muted border border-border group"
                  >
                    <img
                      src={photo.url}
                      alt={`Listing photo ${index + 1}`}
                      className="w-full h-full object-cover"
                    />
                    {index === 0 && (
                      <div className="absolute top-2 left-2 bg-primary text-primary-foreground px-2 py-1 rounded-md text-xs">
                        Primary
                      </div>
                    )}
                    <button
                      onClick={() => handleRemovePhoto(photo.id)}
                      className="absolute top-2 right-2 bg-destructive text-destructive-foreground p-1.5 rounded-full opacity-0 group-hover:opacity-100 transition-opacity"
                      aria-label="Remove photo"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                ))}

                {photos.length < MAX_PHOTOS && (
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={photoUploading}
                    className="aspect-video rounded-xl border-2 border-dashed border-border hover:border-primary hover:bg-primary/5 transition-colors flex flex-col items-center justify-center gap-2 disabled:opacity-60"
                  >
                    <Upload className="w-6 h-6 text-muted-foreground" />
                    <span className="text-sm text-muted-foreground">
                      {photoUploading ? "Uploading..." : "Add Image"}
                    </span>
                  </button>
                )}
              </div>

              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                className="hidden"
                onChange={handleUploadPhoto}
              />
              <p className="text-sm text-muted-foreground">
                Upload up to 6 images. New uploads may take a moment to appear while we finish
                processing them.
              </p>
            </CardContent>
          </Card>

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

          <Card>
            <CardHeader>
              <CardTitle>Location</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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

        <div className="space-y-6">
          <Card className="sticky top-24">
            <CardHeader>
              <CardTitle>Pricing</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="pricePerDay">Price per Day</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$
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
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$
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
                <p className="text-xs text-muted-foreground">Refundable security deposit</p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="replacementValue">Replacement Value</Label>
                <div className="relative">
                  <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground">$
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
                <p className="text-xs text-muted-foreground">Cost to replace if damaged or lost</p>
              </div>

              <Separator className="my-6" />

              <div className="space-y-3">
                <Button onClick={handleSave} className="w-full rounded-full" size="lg" disabled={saving}>
                  {saving ? "Saving..." : "Save Changes"}
                </Button>
                <Button onClick={onBackToListings} variant="outline" className="w-full rounded-full">
                  Cancel
                </Button>
                <div className="flex flex-col gap-3 sm:flex-row">
                  <AlertDialog open={deleteDialogOpen} onOpenChange={handleDeleteDialogOpenChange}>
                    <AlertDialogTrigger asChild>
                      <Button
                        type="button"
                        variant="destructive"
                        className="w-full rounded-full sm:flex-1"
                      >
                        Delete Listing
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete this listing?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This action cannot be undone and will remove the listing for
                          "{currentListing.title}" permanently.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      {deleteError && (
                        <p className="text-sm text-destructive">{deleteError}</p>
                      )}
                      <AlertDialogFooter>
                        <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
                        <Button
                          type="button"
                          className="rounded-full bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          onClick={handleDeleteListing}
                          disabled={deleting}
                        >
                          {deleting ? "Deleting..." : "Delete"}
                        </Button>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                  <Button
                    type="button"
                    variant="secondary"
                    className="w-full rounded-full sm:flex-1"
                    onClick={() => setMode("promote")}
                  >
                    Promote
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
        </>
      )}
    </div>
  );
}
