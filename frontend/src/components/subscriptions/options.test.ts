import { describe, expect, it } from "vitest";

import { DEFAULT_VALUES, scheduleLabel, scheduleProblem, toSettings } from "./options";

describe("subscription schedule", () => {
  it("names the days and time", () => {
    expect(scheduleLabel([4, 0, 2], "18:00")).toBe("Mo, Mi und Fr um 18:00");
    expect(scheduleLabel([6], "06:30")).toBe("So um 6:30");
    expect(scheduleLabel([0, 1, 2, 3, 4, 5, 6], "07:05")).toBe("Täglich um 7:05");
  });

  it("is sent only when chosen", () => {
    expect(toSettings(DEFAULT_VALUES)).toMatchObject({ check_days: null, check_time: null });
    const scheduled = { ...DEFAULT_VALUES, scheduled: true, days: [4, 1], time: "20:15" };
    expect(toSettings(scheduled)).toMatchObject({
      check_interval_minutes: 360,
      check_days: [1, 4],
      check_time: "20:15",
    });
  });

  it("needs a day and a time", () => {
    expect(scheduleProblem(DEFAULT_VALUES)).toBeNull();
    expect(scheduleProblem({ ...DEFAULT_VALUES, scheduled: true })).toBe(
      "Wähle mindestens einen Tag.",
    );
    expect(scheduleProblem({ ...DEFAULT_VALUES, scheduled: true, days: [1], time: "" })).toBe(
      "Wähle eine Uhrzeit.",
    );
  });
});
