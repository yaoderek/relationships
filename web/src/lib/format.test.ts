import { describe, expect, it } from "vitest";
import { fmtDuration, fmtPercent } from "./format";

describe("fmtDuration", () => {
  it("scales units", () => {
    expect(fmtDuration(45)).toBe("45s");
    expect(fmtDuration(120)).toBe("2m");
    expect(fmtDuration(5400)).toBe("1.5h");
    expect(fmtDuration(172800)).toBe("2.0d");
    expect(fmtDuration(null)).toBe("—");
  });
});

describe("fmtPercent", () => {
  it("rounds", () => {
    expect(fmtPercent(0.335)).toBe("34%");
    expect(fmtPercent(null)).toBe("—");
  });
});
