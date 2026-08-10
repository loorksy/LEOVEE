import { describe, expect, it } from "vitest";
import { formatPlanLabel } from "./AdminEntitlementsPanel";

describe("formatPlanLabel", () => {
  it("combines plan name and code", () => {
    expect(
      formatPlanLabel({
        plan_code: "FREE",
        plan_name: "Free",
      }),
    ).toBe("Free (FREE)");
  });
});
