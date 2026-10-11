import { describe, expect, it } from "vitest";
import { formatWorkModes } from "./work_modes";

describe("formatWorkModes", () => {
  it("formats remote correctly", () => {
    expect(formatWorkModes(["remote"])).toBe("Remote");
    expect(formatWorkModes(["REMOTE"])).toBe("Remote");
  });

  it("formats hybrid correctly", () => {
    expect(formatWorkModes(["hybrid"])).toBe("Hybrid");
    expect(formatWorkModes(["Hybrid"])).toBe("Hybrid");
  });

  it("formats onsite variations as On-site", () => {
    expect(formatWorkModes(["onsite"])).toBe("On-site");
    expect(formatWorkModes(["on-site"])).toBe("On-site");
    expect(formatWorkModes(["on_site"])).toBe("On-site");
    expect(formatWorkModes(["in_office"])).toBe("On-site");
  });

  it("formats multiple work modes separated by slash", () => {
    expect(formatWorkModes(["remote", "hybrid"])).toBe("Remote / Hybrid");
  });

  it("returns empty string when array is empty, null, or undefined", () => {
    expect(formatWorkModes([])).toBe("");
    expect(formatWorkModes(null)).toBe("");
    expect(formatWorkModes(undefined)).toBe("");
  });

  it("never returns 'undefined' or empty string values", () => {
    expect(formatWorkModes(["undefined"])).toBe("");
    expect(formatWorkModes([undefined as any])).toBe("");
    expect(formatWorkModes([null as any])).toBe("");
    expect(formatWorkModes([""])).toBe("");
  });
});
