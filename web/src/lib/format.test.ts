// Contract for web/src/lib/format.ts — copy to web/src/lib/format.test.ts unchanged.
import { describe, expect, it } from "vitest";
import { formatSalary, relativeTime, timeBucket } from "./format";

const NOW = new Date("2026-10-11T12:00:00Z");

describe("relativeTime", () => {
  it.each([
    ["2026-10-11T11:59:40Z", "just now"],
    ["2026-10-11T11:58:00Z", "2 min ago"],
    ["2026-10-11T10:00:00Z", "2 h ago"],
    ["2026-10-10T08:00:00Z", "yesterday"],
    ["2026-10-07T12:00:00Z", "4 days ago"],
  ])("%s → %s", (iso, want) => {
    expect(relativeTime(iso, NOW)).toBe(want);
  });
});

describe("timeBucket", () => {
  it("groups by freshness", () => {
    expect(timeBucket("2026-10-11T11:30:00Z", NOW)).toBe("last hour");
    expect(timeBucket("2026-10-11T03:00:00Z", NOW)).toBe("earlier today");
    expect(timeBucket("2026-10-10T20:00:00Z", NOW)).toBe("yesterday");
    expect(timeBucket("2026-10-05T20:00:00Z", NOW)).toBe("this week");
    expect(timeBucket("2026-09-01T20:00:00Z", NOW)).toBe("older");
  });
});

describe("formatSalary", () => {
  const rates = { INR: 1, USD: 84, EUR: 91, GBP: 108 }; // INR per unit

  it("formats INR yearly as LPA", () => {
    expect(formatSalary({ min: 1800000, max: 2400000, currency: "INR", period: "yearly" }, "native", rates)).toBe("₹18–24 LPA");
    expect(formatSalary({ min: 650000, max: 900000, currency: "INR", period: "yearly" }, "native", rates)).toBe("₹6.5–9 LPA");
    expect(formatSalary({ min: 2500000, max: null, currency: "INR", period: "yearly" }, "native", rates)).toBe("₹25 LPA");
  });

  it("formats INR monthly with Indian grouping", () => {
    expect(formatSalary({ min: 50000, max: 70000, currency: "INR", period: "monthly" }, "native", rates)).toBe("₹50,000–70,000 / month");
    expect(formatSalary({ min: 150000, max: null, currency: "INR", period: "monthly" }, "native", rates)).toBe("₹1,50,000 / month");
  });

  it("formats other currencies natively in k", () => {
    expect(formatSalary({ min: 120000, max: 150000, currency: "USD", period: "yearly" }, "native", rates)).toBe("$120k–150k / yr");
    expect(formatSalary({ min: 60000, max: null, currency: "EUR", period: "yearly" }, "native", rates)).toBe("€60k / yr");
  });

  it("converts to INR (as LPA) or USD on request, marked approximate", () => {
    expect(formatSalary({ min: 120000, max: 150000, currency: "USD", period: "yearly" }, "INR", rates)).toBe("≈ ₹100.8–126 LPA");
    expect(formatSalary({ min: 1800000, max: 2400000, currency: "INR", period: "yearly" }, "USD", rates)).toBe("≈ $21k–29k / yr");
  });

  it("returns null when there is no salary", () => {
    expect(formatSalary(null, "native", rates)).toBeNull();
  });
});
