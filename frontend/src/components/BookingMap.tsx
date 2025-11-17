/// <reference types="@types/google.maps" />

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import { Circle, GoogleMap, useLoadScript } from "@react-google-maps/api";
import { MapPin } from "lucide-react";
import { listingsAPI } from "@/lib/api";

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

const geocodeCache = new Map<string, google.maps.LatLngLiteral>();

export function BookingMap({
  postalCode,
  city = DEFAULT_CITY,
  region = DEFAULT_REGION,
}: BookingMapProps) {
  const sanitizedPostalCode = postalCode ? postalCode.trim() : "";
  const sanitizedCity = city.trim() || DEFAULT_CITY;
  const sanitizedRegion = region.trim() || DEFAULT_REGION;
  const cacheKey = useMemo(() => {
    if (!sanitizedPostalCode) {
      return "";
    }
    const normalizedPostal = sanitizedPostalCode.replace(/\s+/g, "").toUpperCase();
    const normalizedCity = sanitizedCity.toLowerCase();
    const normalizedRegion = sanitizedRegion.toLowerCase();
    return `${normalizedPostal}|${normalizedCity}|${normalizedRegion}`;
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
    if (!sanitizedPostalCode) {
      setCenter(null);
      setGeocodeFailed(false);
      return;
    }

    if (!cacheKey) {
      setCenter(null);
      setGeocodeFailed(true);
      return;
    }

    const cachedCenter = geocodeCache.get(cacheKey);
    if (cachedCenter) {
      setCenter(cachedCenter);
      setGeocodeFailed(false);
      return;
    }

    const controller = new AbortController();
    let active = true;
    setCenter(null);
    setGeocodeFailed(false);

    listingsAPI
      .geocodeLocation(
        {
          postalCode: sanitizedPostalCode,
          city: sanitizedCity,
          region: sanitizedRegion,
        },
        { signal: controller.signal },
      )
      .then((response) => {
        if (!active) return;
        const nextCenter = response.location;
        geocodeCache.set(cacheKey, nextCenter);
        setCenter(nextCenter);
      })
      .catch((error) => {
        if (!active) return;
        if (
          error &&
          typeof error === "object" &&
          "name" in error &&
          (error as { name?: string }).name === "AbortError"
        ) {
          return;
        }
        console.warn("Failed to geocode booking map address", error);
        setGeocodeFailed(true);
      });

    return () => {
      active = false;
      controller.abort();
    };
  }, [cacheKey, sanitizedCity, sanitizedPostalCode, sanitizedRegion]);

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
