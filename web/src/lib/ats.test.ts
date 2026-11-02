import { describe, expect, it } from "vitest";
import { formatAtsName } from "./ats";

describe("formatAtsName", () => {
  it("maps greenhouse to Greenhouse", () => {
    expect(formatAtsName("greenhouse")).toBe("Greenhouse");
    expect(formatAtsName("Greenhouse")).toBe("Greenhouse");
  });

  it("maps lever to Lever", () => {
    expect(formatAtsName("lever")).toBe("Lever");
  });

  it("maps ashby to Ashby", () => {
    expect(formatAtsName("ashby")).toBe("Ashby");
  });

  it("maps workday to Workday", () => {
    expect(formatAtsName("workday")).toBe("Workday");
  });

  it("maps smartrecruiters to SmartRecruiters", () => {
    expect(formatAtsName("smartrecruiters")).toBe("SmartRecruiters");
  });

  it("maps workable to Workable", () => {
    expect(formatAtsName("workable")).toBe("Workable");
  });

  it("maps crawler/scraper types and generic sources to 'Career site'", () => {
    expect(formatAtsName("dom")).toBe("Career site");
    expect(formatAtsName("sitemap")).toBe("Career site");
    expect(formatAtsName("nextdata")).toBe("Career site");
    expect(formatAtsName("api_sniffer")).toBe("Career site");
    expect(formatAtsName("inline")).toBe("Career site");
  });

  it("maps null, undefined, and empty string to 'Career site'", () => {
    expect(formatAtsName(null)).toBe("Career site");
    expect(formatAtsName(undefined)).toBe("Career site");
    expect(formatAtsName("")).toBe("Career site");
    expect(formatAtsName("   ")).toBe("Career site");
  });
});
