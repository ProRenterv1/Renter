import { useState, KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Input } from "./ui/input";
import { Search, MapPin } from "lucide-react";

export function Hero() {
  const quickChips = ["Drills", "Lawn", "Ladders", "Pressure Washers"];
  const [search, setSearch] = useState("");
  const [city, setCity] = useState("Edmonton");
  const navigate = useNavigate();

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter") {
      return;
    }

    const trimmedQuery = search.trim();
    if (!trimmedQuery) {
      return;
    }

    navigate(
      `/feed?q=${encodeURIComponent(trimmedQuery)}&city=${encodeURIComponent(
        city.trim()
      )}`
    );
  };

  const handleChipClick = (chip: string) => {
    navigate(
      `/feed?q=${encodeURIComponent(chip)}&city=${encodeURIComponent(
        city.trim()
      )}`
    );
  };

  return (
    <section className="relative overflow-hidden py-16 pb-4 px-4 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl">
        <div className="text-center space-y-8">
          <div className="space-y-4">
            <h1 className="text-5xl font-semibold text-[#121a24] sm:text-6xl lg:text-7xl tracking-tight leading-tight">
              Rent tools from neighbours —{" "}
              <span className="font-semibold text-[#5f8fb3]">
                insured &amp; verified
              </span>
            </h1>
            <p className="text-xl text-[#6f7c8d] sm:text-2xl">
              Pick up today in Edmonton.
            </p>
          </div>
          
          <div className="max-w-4xl mx-auto pt-2 space-y-4">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                  placeholder="Search for tools..."
                  className="pl-12 pr-4 h-14 text-lg bg-card shadow-xl border-2 hover:border-[var(--primary)] transition-colors rounded-xl"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  onKeyDown={handleSearchKeyDown}
                />
              </div>
              <div className="relative sm:w-64">
                <MapPin className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                  value={city}
                  onChange={(event) => setCity(event.target.value)}
                  className="pl-12 pr-4 h-14 text-lg bg-card shadow-xl border-2 rounded-xl cursor-pointer hover:border-[var(--primary)] transition-colors"
                />
                <button className="absolute right-4 top-1/2 -translate-y-1/2 text-sm underline" style={{ color: 'var(--primary)' }}>
                  change
                </button>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-center gap-2">
              {quickChips.map((chip, index) => (
                <button
                  key={index}
                  className="px-4 py-2 rounded-full bg-card border-2 border-[var(--border)] hover:border-[var(--primary)] hover:shadow-md transition-all text-sm"
                  onClick={() => handleChipClick(chip)}
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
