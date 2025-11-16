/// <reference types="@types/google.maps" />

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Circle, GoogleMap, useLoadScript } from "@react-google-maps/api";
import { MapPin } from "lucide-react";

type BookingMapProps = {
  postalCode: string;
  city?: string;
  region?: string;
};

const DEFAULT_CITY = "Edmonton";
const DEFAULT_REGION = "AB, Canada";
const MAP_ZOOM = 13;
const CIRCLE_RADIUS_METERS = 2000;
const MAP_CONTAINER_STYLE: CSSProperties = {
  width: "100%",
  height: "100%",
};
const MAP_OPTIONS: google.maps.MapOptions = {
  disableDefaultUI: true,
  zoomControl: true,
  draggable: true,
  scrollwheel: false,
  keyboardShortcuts: false,
};
const CIRCLE_OPTIONS: google.maps.CircleOptions = {
  strokeColor: "#5B8CA6",
  strokeOpacity: 0.9,
  strokeWeight: 2,
  fillColor: "#5B8CA6",
  fillOpacity: 0.18,
  clickable: false,
};

export function BookingMap({
  postalCode,
  city = DEFAULT_CITY,
  region = DEFAULT_REGION,
}: BookingMapProps) {
  const sanitizedPostalCode = postalCode ? postalCode.trim() : "";
  const sanitizedCity = city.trim() || DEFAULT_CITY;
  const sanitizedRegion = region.trim() || DEFAULT_REGION;
  const address = useMemo(() => {
    if (!sanitizedPostalCode) {
      return "";
    }
    return `${sanitizedPostalCode}, ${sanitizedCity}, ${sanitizedRegion}`;
  }, [sanitizedPostalCode, sanitizedCity, sanitizedRegion]);
  const [center, setCenter] = useState<google.maps.LatLngLiteral | null>(null);
  const [geocodeFailed, setGeocodeFailed] = useState(false);

  const googleMapsApiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;
  const missingApiKey = !googleMapsApiKey;
  const { isLoaded, loadError } = useLoadScript({
    id: "booking-map-script",
    googleMapsApiKey: googleMapsApiKey ?? "",
  });

  useEffect(() => {
    if (!isLoaded || !address || typeof window === "undefined") {
      return;
    }

    let cancelled = false;
    setCenter(null);
    setGeocodeFailed(false);

    const geocoder = new google.maps.Geocoder();
    geocoder.geocode({ address }, (results, status) => {
      if (cancelled) return;

      const resultLocation = results?.[0]?.geometry?.location;
      if (status === "OK" && resultLocation) {
        const { lat, lng } = resultLocation.toJSON();
        setCenter({ lat, lng });
        return;
      }

      console.warn("Failed to geocode booking map address", {
        address,
        status,
        results,
      });
      setGeocodeFailed(true);
    });

    return () => {
      cancelled = true;
    };
  }, [address, isLoaded]);

  if (!sanitizedPostalCode) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-2 px-4 text-center text-muted-foreground">
        <MapPin className="h-8 w-8" />
        <p className="text-sm font-medium">Location details not provided</p>
      </div>
    );
  }

  if (missingApiKey || loadError || geocodeFailed) {
    return (
      <div className="flex h-full w-full items-center justify-center rounded-xl border border-border bg-background text-sm text-muted-foreground">
        Map failed to load
      </div>
    );
  }

  if (!isLoaded || !center) {
    return (
      <div
        className="h-full w-full animate-pulse rounded-xl border border-border bg-muted"
        aria-label="Loading map"
      />
    );
  }

  return (
    <GoogleMap
      mapContainerStyle={MAP_CONTAINER_STYLE}
      center={center}
      zoom={MAP_ZOOM}
      options={MAP_OPTIONS}
    >
      <Circle center={center} radius={CIRCLE_RADIUS_METERS} options={CIRCLE_OPTIONS} />
    </GoogleMap>
  );
}
