import { describe, expect, it } from "vitest";

import { __testables } from "./YourRentals";

const { parseLocalDate, startOfToday, isStartDay } = __testables;

describe("YourRentals pickup visibility helpers", () => {
  it("detects start day correctly", () => {
    const today = startOfToday();
    const isoToday = today.toISOString().slice(0, 10);
    const isoTomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000)
      .toISOString()
      .slice(0, 10);

    expect(isStartDay(isoToday)).toBe(true);
    expect(isStartDay(isoTomorrow)).toBe(false);
  });

  it("parses local date consistently", () => {
    const date = parseLocalDate("2024-12-25");
    expect(date.getFullYear()).toBe(2024);
    expect(date.getMonth()).toBe(11);
    expect(date.getDate()).toBe(25);
  });
});
