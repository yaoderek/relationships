import { describe, expect, it } from "vitest";
import { mergeSeries } from "./ArcsChart";

describe("mergeSeries", () => {
  it("pivots person series into bucket rows, sorted", () => {
    const merged = mergeSeries([
      { person_id: 1, display_name: "A",
        series: [{ bucket: "2024-02", total: 3 }, { bucket: "2024-01", total: 1 }] },
      { person_id: 2, display_name: "B", series: [{ bucket: "2024-01", total: 5 }] },
    ]);
    expect(merged).toEqual([
      { bucket: "2024-01", A: 1, B: 5 },
      { bucket: "2024-02", A: 3 },
    ]);
  });
});
