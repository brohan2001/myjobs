import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchJobs } from "./api";

describe("fetchJobs", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("passes sentence filters through and drops blanks", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ jobs: [], next_cursor: null }) });
    vi.stubGlobal("fetch", fetchMock);

    await fetchJobs({ country: "IN", company_type: "startup", max_years: "0", notice_days: " ", work_mode: "" });

    const url = new URL(fetchMock.mock.calls[0][0], "http://x");
    expect(url.searchParams.get("company_type")).toBe("startup");
    expect(url.searchParams.get("max_years")).toBe("0");
    expect(url.searchParams.has("notice_days")).toBe(false);
    expect(url.searchParams.has("work_mode")).toBe(false);
  });
});
