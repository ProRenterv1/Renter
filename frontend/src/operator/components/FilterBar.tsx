import { useMemo, useState } from "react";
import { Filter, Mail, Phone, Shield, SlidersHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Drawer, DrawerContent, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/components/ui/utils";

type FilterSelectOption = {
  label: string;
  value: string;
};

type AdvancedFiltersState = {
  canRent: boolean | null;
  canList: boolean | null;
  joinedAfter?: string;
  joinedBefore?: string;
};

type FilterBarProps = {
  searchPlaceholder?: string;
  searchValue: string;
  onSearchChange: (value: string) => void;
  cityValue: string;
  cityOptions: FilterSelectOption[];
  onCityChange: (value: string) => void;
  statusValue: string;
  onStatusChange: (value: string) => void;
  verifiedFilters: string[];
  onToggleVerified: (value: string) => void;
  advancedFilters: AdvancedFiltersState;
  onAdvancedChange: (value: Partial<AdvancedFiltersState>) => void;
  className?: string;
};

const VERIFIED_CONFIG = [
  { key: "email", label: "Email", icon: Mail },
  { key: "phone", label: "Phone", icon: Phone },
  { key: "identity", label: "Identity", icon: Shield },
] as const;

export function FilterBar({
  searchPlaceholder = "Search...",
  searchValue,
  onSearchChange,
  cityValue,
  cityOptions,
  onCityChange,
  statusValue,
  onStatusChange,
  verifiedFilters,
  onToggleVerified,
  advancedFilters,
  onAdvancedChange,
  className,
}: FilterBarProps) {
  const [drawerOpen, setDrawerOpen] = useState(false);

  const normalizedCities = useMemo(() => {
    const seen = new Set<string>();
    const options: FilterSelectOption[] = [];
    cityOptions.forEach((option) => {
      const value = option.value?.trim();
      if (!value) return;
      if (seen.has(value)) return;
      seen.add(value);
      options.push(option);
    });
    return options;
  }, [cityOptions]);

  const handleDateChange = (key: "joinedAfter" | "joinedBefore", value: string) => {
    onAdvancedChange({ [key]: value || undefined });
  };

  const resetAdvancedFilters = () => {
    onAdvancedChange({
      canList: null,
      canRent: null,
      joinedAfter: undefined,
      joinedBefore: undefined,
    });
  };

  return (
    <Card className={className}>
      <CardContent className="p-4">
        <div className="space-y-4">
          <div className="relative">
            <Filter className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={searchPlaceholder}
              value={searchValue}
              onChange={(e) => onSearchChange(e.target.value)}
              className="pl-10"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <Select value={cityValue} onValueChange={onCityChange}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="All Cities" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Cities</SelectItem>
                {normalizedCities.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select value={statusValue} onValueChange={onStatusChange}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="All Statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="active">Active</SelectItem>
                <SelectItem value="suspended">Suspended</SelectItem>
              </SelectContent>
            </Select>

            <div className="flex flex-wrap items-center gap-2">
              <span className="flex items-center gap-1 text-sm text-muted-foreground">
                <SlidersHorizontal className="h-4 w-4" />
                Verified:
              </span>
              {VERIFIED_CONFIG.map(({ key, label, icon: Icon }) => {
                const isActive = verifiedFilters.includes(key);
                return (
                  <Button
                    key={key}
                    variant={isActive ? "default" : "outline"}
                    size="sm"
                    onClick={() => onToggleVerified(key)}
                    className={cn(isActive && "shadow-sm")}
                  >
                    <Icon className="mr-1 h-3 w-3" />
                    {label}
                  </Button>
                );
              })}
            </div>

            <Drawer direction="right" open={drawerOpen} onOpenChange={setDrawerOpen}>
              <Button variant="outline" size="sm" onClick={() => setDrawerOpen(true)}>
                <SlidersHorizontal className="mr-2 h-4 w-4" />
                Advanced filters
              </Button>
              <DrawerContent className="bg-background sm:max-w-md">
                <DrawerHeader>
                  <DrawerTitle>Advanced filters</DrawerTitle>
                </DrawerHeader>
                <div className="space-y-4 p-4">
                  <div className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div>
                    <div className="font-medium">Can rent</div>
                    <div className="text-sm text-muted-foreground">
                      Only show users allowed to rent tools
                    </div>
                  </div>
                  <Switch
                      checked={advancedFilters.canRent ?? false}
                      onCheckedChange={(checked) => onAdvancedChange({ canRent: checked ? true : null })}
                    />
                </div>
                <div className="flex items-center justify-between rounded-lg border border-border p-3">
                  <div>
                    <div className="font-medium">Can list</div>
                      <div className="text-sm text-muted-foreground">
                        Only show users allowed to list tools
                      </div>
                  </div>
                  <Switch
                      checked={advancedFilters.canList ?? false}
                      onCheckedChange={(checked) => onAdvancedChange({ canList: checked ? true : null })}
                    />
                </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Joined after</div>
                      <Input
                        type="date"
                        value={advancedFilters.joinedAfter ?? ""}
                        onChange={(e) => handleDateChange("joinedAfter", e.target.value)}
                      />
                    </div>
                    <div className="space-y-1">
                      <div className="text-sm text-muted-foreground">Joined before</div>
                      <Input
                        type="date"
                        value={advancedFilters.joinedBefore ?? ""}
                        onChange={(e) => handleDateChange("joinedBefore", e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="flex justify-between pt-2">
                    <Button variant="ghost" onClick={resetAdvancedFilters}>
                      Reset
                    </Button>
                    <Button onClick={() => setDrawerOpen(false)}>Apply filters</Button>
                  </div>
                </div>
              </DrawerContent>
            </Drawer>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
