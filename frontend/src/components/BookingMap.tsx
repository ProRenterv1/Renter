import { MapPin } from "lucide-react";

interface BookingMapProps {
  postalCode: string;
  city?: string;
  country?: string;
}

export function BookingMap({
  postalCode,
  city,
  country = "Canada",
}: BookingMapProps) {
  const segments = [
    postalCode?.trim(),
    city?.trim(),
    country?.trim(),
  ].filter((segment): segment is string => Boolean(segment));

  if (segments.length === 0) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-4 text-center text-muted-foreground">
        <MapPin className="h-8 w-8" />
        <p className="text-sm font-medium">Location details not provided</p>
      </div>
    );
  }

  const query = segments.join(", ");

  return (
    <iframe
      src={`https://www.google.com/maps?q=${encodeURIComponent(query)}&output=embed`}
      title={`Map for ${query}`}
      className="h-full w-full"
      style={{ border: 0 }}
      loading="lazy"
      referrerPolicy="no-referrer-when-downgrade"
    />
  );
}
