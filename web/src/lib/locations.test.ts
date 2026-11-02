import { describe, expect, it } from "vitest";
import { orderLocations } from "./locations";
import { LocationItem } from "./types";

describe("orderLocations", () => {
  const houstonUS: LocationItem = { id: 1, name: "Houston, United States", country: "US", type: "onsite" };
  const jaipurIN: LocationItem = { id: 2, name: "Jaipur, India", country: "IN", type: "onsite" };
  const bangaloreIN: LocationItem = { id: 1277333, name: "Bangalore, India", country: "IN", type: "onsite" };
  const noidaNCR: LocationItem = { id: 4, name: "Noida, India", country: "IN", type: "onsite" };
  const berlinDE: LocationItem = { id: 5, name: "Berlin, Germany", country: "DE", type: "onsite" };
  const tokyoJP: LocationItem = { id: 6, name: "Tokyo, Japan", country: "JP", type: "onsite" };
  const parisFR: LocationItem = { id: 7, name: "Paris, France", country: "FR", type: "onsite" };

  it("prioritizes Indian location when filtered by India / IN (example from brief)", () => {
    const locations = [houstonUS, jaipurIN];
    const ordered = orderLocations(locations, "India");
    expect(ordered[0].name).toBe("Jaipur, India");
    expect(ordered[1].name).toBe("Houston, United States");

    const orderedWithCode = orderLocations(locations, "IN");
    expect(orderedWithCode[0].name).toBe("Jaipur, India");

    const orderedWithPrefix = orderLocations(locations, "in:");
    expect(orderedWithPrefix[0].name).toBe("Jaipur, India");
  });

  it("prioritizes US location when filtered by US", () => {
    const locations = [jaipurIN, houstonUS];
    const ordered = orderLocations(locations, "US");
    expect(ordered[0].name).toBe("Houston, United States");
    expect(ordered[1].name).toBe("Jaipur, India");

    const orderedPrefix = orderLocations(locations, "us:");
    expect(orderedPrefix[0].name).toBe("Houston, United States");
  });

  it("prioritizes EU member state locations under EU filter", () => {
    const locations = [houstonUS, berlinDE, tokyoJP, parisFR];
    const ordered = orderLocations(locations, "EU");
    // Berlin and Paris are EU member states, Houston and Tokyo are not
    expect(ordered.slice(0, 2)).toEqual([berlinDE, parisFR]);
    expect(ordered.slice(2)).toEqual([houstonUS, tokyoJP]);

    const orderedPrefix = orderLocations(locations, "eu:");
    expect(orderedPrefix.slice(0, 2)).toEqual([berlinDE, parisFR]);
  });

  it("leaves order unchanged when no locations match EU filter", () => {
    const locations = [tokyoJP, houstonUS];
    const ordered = orderLocations(locations, "EU");
    expect(ordered).toEqual([tokyoJP, houstonUS]);
  });

  it("prioritizes matching city by name", () => {
    const locations = [jaipurIN, bangaloreIN];
    const ordered = orderLocations(locations, "Bengaluru");
    expect(ordered[0].name).toBe("Bangalore, India");
    expect(ordered[1].name).toBe("Jaipur, India");
  });

  it("handles city filter via slug or location ID", () => {
    const locations = [jaipurIN, bangaloreIN];
    const orderedSlug = orderLocations(locations, "in:blr");
    expect(orderedSlug[0].name).toBe("Bangalore, India");

    const orderedId = orderLocations(locations, "in:1277333");
    expect(orderedId[0].name).toBe("Bangalore, India");

    const orderedObj = orderLocations(locations, { location: 1277333 });
    expect(orderedObj[0].name).toBe("Bangalore, India");
  });

  it("matches NCR cities like Noida or Gurgaon when filtered by Delhi NCR", () => {
    const locations = [jaipurIN, noidaNCR];
    const ordered = orderLocations(locations, "Delhi NCR");
    expect(ordered[0].name).toBe("Noida, India");
    expect(ordered[1].name).toBe("Jaipur, India");

    const orderedSlug = orderLocations(locations, "in:ncr");
    expect(orderedSlug[0].name).toBe("Noida, India");
  });

  it("preserves order when filter is worldwide, all, empty, or undefined", () => {
    const locations = [houstonUS, jaipurIN];
    expect(orderLocations(locations, "all:")).toEqual([houstonUS, jaipurIN]);
    expect(orderLocations(locations, "")).toEqual([houstonUS, jaipurIN]);
    expect(orderLocations(locations, undefined)).toEqual([houstonUS, jaipurIN]);
    expect(orderLocations(locations, null)).toEqual([houstonUS, jaipurIN]);
  });

  it("handles edge cases: empty array or single-element array", () => {
    expect(orderLocations([])).toEqual([]);
    expect(orderLocations([jaipurIN], "US")).toEqual([jaipurIN]);
    expect(orderLocations(null, "IN")).toEqual([]);
  });
});
