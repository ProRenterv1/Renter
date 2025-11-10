export type ListingCategory =
  | "Power Tools"
  | "Ladders"
  | "Landscaping"
  | "Cleaning"
  | "Renovation"
  | "Automotive";

export interface Listing {
  id: string;
  title: string;
  category: ListingCategory;
  pricePerDay: number;
  location: string;
  rating: number;
  reviews: number;
  promoted?: boolean;
  availability: string;
  imageUrl: string;
}

export const listings: Listing[] = [
  {
    id: "drill-kit",
    title: "DeWalt XR Hammer Drill Kit",
    category: "Power Tools",
    pricePerDay: 28,
    location: "Garneau · Edmonton",
    rating: 4.9,
    reviews: 76,
    promoted: true,
    availability: "Pick up today",
    imageUrl:
      "https://images.unsplash.com/photo-1504148455328-c376907d081c?auto=format&fit=crop&w=900&q=80",
  },
  {
    id: "rotary-laser",
    title: "Hilti Rotary Laser Level",
    category: "Renovation",
    pricePerDay: 55,
    location: "Strathearn · Edmonton",
    rating: 4.8,
    reviews: 41,
    promoted: true,
    availability: "Same-day available",
    imageUrl:
      "https://images.unsplash.com/photo-1504149215112-3a0e1f2faa5c?auto=format&fit=crop&w=900&q=80",
  },
  {
    id: "ladder",
    title: "32' Fiberglass Extension Ladder",
    category: "Ladders",
    pricePerDay: 22,
    location: "Highlands · Edmonton",
    rating: 4.7,
    reviews: 53,
    imageUrl:
      "https://images.unsplash.com/photo-1523419409543-0c1df022bddb?auto=format&fit=crop&w=900&q=80",
    availability: "Tomorrow",
  },
  {
    id: "aerator",
    title: "Manual Lawn Aerator",
    category: "Landscaping",
    pricePerDay: 18,
    location: "Ritchie · Edmonton",
    rating: 4.6,
    reviews: 24,
    imageUrl:
      "https://images.unsplash.com/photo-1501004318641-b39e6451bec6?auto=format&fit=crop&w=900&q=80",
    availability: "Fri 9AM",
  },
  {
    id: "pressure-washer",
    title: "Gas Pressure Washer 3200 PSI",
    category: "Cleaning",
    pricePerDay: 40,
    location: "Magrath Heights · Edmonton",
    rating: 4.9,
    reviews: 66,
    promoted: true,
    availability: "Pick up today",
    imageUrl:
      "https://images.unsplash.com/photo-1505739775417-85cb3315c3ae?auto=format&fit=crop&w=900&q=80",
  },
  {
    id: "tile-saw",
    title: "Wet Tile Saw 7\" with stand",
    category: "Renovation",
    pricePerDay: 32,
    location: "Oliver · Edmonton",
    rating: 4.8,
    reviews: 38,
    availability: "Weekend only",
    imageUrl:
      "https://images.unsplash.com/photo-1504148401347-5a80fc19243c?auto=format&fit=crop&w=900&q=80",
  },
  {
    id: "air-compressor",
    title: "Quiet 6 Gal Air Compressor",
    category: "Power Tools",
    pricePerDay: 25,
    location: "Bonnie Doon · Edmonton",
    rating: 4.5,
    reviews: 18,
    availability: "Pick up Thu",
    imageUrl:
      "https://images.unsplash.com/photo-1441632285151-3364e7e71e32?auto=format&fit=crop&w=900&q=80",
  },
  {
    id: "car-dolly",
    title: "Low-Profile Car Dolly Set",
    category: "Automotive",
    pricePerDay: 20,
    location: "Belgravia · Edmonton",
    rating: 4.4,
    reviews: 14,
    availability: "Weekend",
    imageUrl:
      "https://images.unsplash.com/photo-1503736334956-4c8f8e92946d?auto=format&fit=crop&w=900&q=80",
  },
  {
    id: "impact-driver",
    title: "Milwaukee Fuel Impact Driver",
    category: "Power Tools",
    pricePerDay: 26,
    location: "Glenora · Edmonton",
    rating: 5,
    reviews: 52,
    availability: "Pick up today",
    imageUrl:
      "https://images.unsplash.com/photo-1563170423-18f482d82cc8?auto=format&fit=crop&w=900&q=80",
  },
  {
    id: "log-splitter",
    title: "Electric Log Splitter 5 Ton",
    category: "Landscaping",
    pricePerDay: 38,
    location: "Capilano · Edmonton",
    rating: 4.6,
    reviews: 31,
    availability: "Next-day",
    imageUrl:
      "https://images.unsplash.com/photo-1455906876003-298dd8c44b0f?auto=format&fit=crop&w=900&q=80",
  },
];
