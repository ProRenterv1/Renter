import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { format } from "date-fns";
import { Card, CardContent, CardHeader, CardTitle } from "../../components/ui/card";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Dialog, DialogContent } from "../../components/ui/dialog";
import {
  AlertCircle,
  ArrowLeft,
  Calendar,
  DollarSign,
  Shield,
  Edit,
  MapPin,
  Tag,
  User,
  X,
} from "lucide-react";
import {
  operatorAPI,
  type OperatorListingDetail,
  type OperatorListingOwner,
} from "../api";
import { Skeleton } from "../../components/ui/skeleton";
import { DeactivateListingModal } from "../components/modals/DeactivateListingModal";
import { MarkNeedsReviewModal } from "../components/modals/MarkNeedsReviewModal";
import { EmergencyEditModal } from "../components/modals/EmergencyEditModal";
import { toast } from "sonner";

export function ListingDetail() {
  const { listingId } = useParams();
  const navigate = useNavigate();
  const [listing, setListing] = useState<OperatorListingDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [lightboxImage, setLightboxImage] = useState("");
  const [deactivateModalOpen, setDeactivateModalOpen] = useState(false);
  const [needsReviewModalOpen, setNeedsReviewModalOpen] = useState(false);
  const [emergencyEditModalOpen, setEmergencyEditModalOpen] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const loadListing = async () => {
    if (!listingId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await operatorAPI.listingDetail(Number(listingId));
      setListing(data);
    } catch (err) {
      console.error("Failed to load listing", err);
      setError("Unable to load listing.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadListing();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listingId]);

  const handleOpenLightbox = (imageUrl: string) => {
    setLightboxImage(imageUrl);
    setLightboxOpen(true);
  };

  const handleDeactivate = async (reason: string) => {
    if (!listing) return;
    setActionLoading(true);
    try {
      await operatorAPI.deactivateListing(listing.id, { reason });
      toast.success("Listing deactivated");
      await loadListing();
    } catch (err) {
      console.error(err);
      toast.error("Failed to deactivate listing");
    } finally {
      setActionLoading(false);
      setDeactivateModalOpen(false);
    }
  };

  const handleActivate = async () => {
    if (!listing) return;
    setActionLoading(true);
    try {
      await operatorAPI.activateListing(listing.id, { reason: "Operator activation" });
      toast.success("Listing activated");
      await loadListing();
    } catch (err) {
      console.error(err);
      toast.error("Failed to activate listing");
    } finally {
      setActionLoading(false);
    }
  };

  const handleMarkNeedsReview = async (data: { reason: string; tag?: string }) => {
    if (!listing) return;
    setActionLoading(true);
    try {
      await operatorAPI.markListingNeedsReview(listing.id, { reason: data.reason, text: data.reason });
      toast.success("Listing marked for review");
      await loadListing();
    } catch (err) {
      console.error(err);
      toast.error("Failed to mark for review");
    } finally {
      setActionLoading(false);
      setNeedsReviewModalOpen(false);
    }
  };

  const handleEmergencyEdit = async (data: { title: string; description: string }) => {
    if (!listing) return;
    setActionLoading(true);
    try {
      await operatorAPI.emergencyEditListing(listing.id, {
        reason: "Operator emergency edit",
        title: data.title,
        description: data.description,
      });
      toast.success("Emergency edit applied");
      await loadListing();
    } catch (err) {
      console.error(err);
      toast.error("Failed to apply emergency edit");
    } finally {
      setActionLoading(false);
      setEmergencyEditModalOpen(false);
    }
  };

  const ownerLabel = useMemo(() => ownerDisplay(listing?.owner), [listing]);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-32" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !listing) {
    return (
      <div className="space-y-6">
        <Button variant="ghost" onClick={() => navigate("/operator/listings")}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back to Listings
        </Button>
        <Card>
          <CardContent className="p-12 text-center">
            <h2 className="mb-2">Listing Not Found</h2>
            <p className="text-muted-foreground">{error || "The requested listing could not be found."}</p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const priceLabel = listing.daily_price_cad ? `$${listing.daily_price_cad}` : "—";

  return (
    <div className="space-y-6">
      <Button variant="ghost" onClick={() => navigate("/operator/listings")}>
        <ArrowLeft className="w-4 h-4 mr-2" />
        Back to Listings
      </Button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-start justify-between gap-4 mb-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h1 className="m-0">{listing.title}</h1>
                    <Badge variant={listing.is_active ? "default" : "secondary"}>
                      {listing.is_active ? "Active" : "Inactive"}
                    </Badge>
                    {listing.needs_review && (
                      <Badge variant="outline" className="border-orange-500 text-orange-700">
                        <AlertCircle className="w-3 h-3 mr-1" />
                        Needs Review
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground m-0">#{listing.id}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Images</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {listing.photos?.length ? (
                  listing.photos.map((photo) => (
                    <button
                      key={photo.id}
                      onClick={() => handleOpenLightbox(photo.url)}
                      className="relative aspect-square rounded-lg overflow-hidden border border-border hover:ring-2 hover:ring-primary transition-all"
                    >
                      <img src={photo.url} alt={`${listing.title}`} className="w-full h-full object-cover" />
                    </button>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground col-span-full">No photos available.</p>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Listing Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <DetailRow icon={<User className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Owner">
                  <button
                    onClick={() => navigate(`/operator/users/${listing.owner?.id}`)}
                    className="text-primary hover:underline"
                  >
                    {ownerLabel}
                  </button>
                </DetailRow>

                <DetailRow icon={<MapPin className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Location">
                  {listing.city || "—"}
                  {listing.postal_code ? <div className="text-sm text-muted-foreground">{listing.postal_code}</div> : null}
                </DetailRow>

                <DetailRow icon={<Tag className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Category">
                  {listing.category?.name || listing.category?.slug || "—"}
                </DetailRow>

                <DetailRow icon={<DollarSign className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Price Per Day">
                  <div className="text-lg font-medium">{priceLabel}</div>
                </DetailRow>

                <DetailRow icon={<Shield className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Damage Deposit">
                  <div className="text-lg font-medium">
                    {listing.damage_deposit_cad ? `$${listing.damage_deposit_cad}` : "—"}
                  </div>
                </DetailRow>

                <DetailRow icon={<Shield className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Replacement Value">
                  <div className="text-lg font-medium">
                    {listing.replacement_value_cad ? `$${listing.replacement_value_cad}` : "—"}
                  </div>
                </DetailRow>

                <DetailRow icon={<Calendar className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Created">
                  {listing.created_at ? format(new Date(listing.created_at), "PP") : "—"}
                </DetailRow>

                <DetailRow icon={<Calendar className="w-5 h-5 text-muted-foreground mt-0.5" />} label="Availability">
                  {listing.is_available ? "Available" : "Unavailable"}
                </DetailRow>
              </div>

              <div className="pt-4 border-t border-border">
                <h3 className="mb-3">Description</h3>
                <p className="text-muted-foreground whitespace-pre-wrap m-0">{listing.description || "—"}</p>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Actions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {listing.is_active ? (
                <Button
                  variant="destructive"
                  className="w-full justify-start"
                  onClick={() => setDeactivateModalOpen(true)}
                  disabled={actionLoading}
                >
                  <AlertCircle className="w-4 h-4 mr-2" />
                  Deactivate Listing
                </Button>
              ) : (
                <Button className="w-full justify-start" onClick={handleActivate} disabled={actionLoading}>
                  <AlertCircle className="w-4 h-4 mr-2" />
                  Activate Listing
                </Button>
              )}
              <Button
                variant="outline"
                className="w-full justify-start"
                onClick={() => setNeedsReviewModalOpen(true)}
                disabled={actionLoading}
              >
                <AlertCircle className="w-4 h-4 mr-2" />
                Mark Needs Review
              </Button>
              <Button
                variant="ghost"
                className="w-full justify-start"
                onClick={() => setEmergencyEditModalOpen(true)}
                disabled={actionLoading}
              >
                <Edit className="w-4 h-4 mr-2" />
                Emergency Edit
              </Button>
            </CardContent>
          </Card>
        </div>
      </div>

      <Dialog open={lightboxOpen} onOpenChange={setLightboxOpen}>
        <DialogContent className="max-w-3xl p-0 overflow-hidden">
          <button
            className="absolute top-3 right-3 p-2 rounded-full bg-background/80 hover:bg-background"
            onClick={() => setLightboxOpen(false)}
          >
            <X className="w-4 h-4" />
          </button>
          {lightboxImage && <img src={lightboxImage} alt="Listing" className="w-full h-full object-contain" />}
        </DialogContent>
      </Dialog>

      <DeactivateListingModal
        open={deactivateModalOpen}
        onOpenChange={setDeactivateModalOpen}
        listingTitle={listing.title}
        onConfirm={handleDeactivate}
        loading={actionLoading}
      />

      <MarkNeedsReviewModal
        open={needsReviewModalOpen}
        onOpenChange={setNeedsReviewModalOpen}
        listingTitle={listing.title}
        onConfirm={handleMarkNeedsReview}
        loading={actionLoading}
      />

      <EmergencyEditModal
        open={emergencyEditModalOpen}
        onOpenChange={setEmergencyEditModalOpen}
        listingTitle={listing.title}
        defaultTitle={listing.title}
        defaultDescription={listing.description}
        onConfirm={handleEmergencyEdit}
        loading={actionLoading}
      />
    </div>
  );
}

function DetailRow({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3">
      {icon}
      <div className="flex-1">
        <div className="text-sm text-muted-foreground mb-1">{label}</div>
        <div>{children}</div>
      </div>
    </div>
  );
}

function ownerDisplay(owner?: OperatorListingOwner | null) {
  if (!owner) return "Owner";
  const name = owner.name && typeof owner.name === "string" ? owner.name.trim() : "";
  const email = owner.email && typeof owner.email === "string" ? owner.email.trim() : "";
  if (name) return name;
  if (email) return email;
  return `Owner #${owner.id}`;
}
