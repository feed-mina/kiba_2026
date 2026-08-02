import assert from "node:assert/strict";
import test from "node:test";

import {
  calendarDays,
  calendarRange,
  entriesForDate,
  normalizeScheduleEntry,
  shiftCalendar,
  toDateKey,
} from "./schedule.js";

test("builds Monday-first week and six-row month ranges", () => {
  const cursor = new Date(2026, 7, 2);
  const week = calendarRange(cursor, "week");
  assert.equal(toDateKey(week.start), "2026-07-27");
  assert.equal(toDateKey(week.end), "2026-08-02");
  const month = calendarRange(cursor, "month");
  assert.equal(month.days, 42);
  assert.equal(toDateKey(month.start), "2026-07-27");
  assert.equal(toDateKey(month.end), "2026-09-06");
});

test("normalizes schedule entries and rejects reversed ranges", () => {
  assert.equal(normalizeScheduleEntry({ startDate: "2026-08-03", endDate: "2026-08-02" }), null);
  assert.deepEqual(normalizeScheduleEntry({
    repository: "feed-mina/kiba_2026",
    issue: "12",
    title: " 주간 보고 ",
    startDate: "2026-08-03",
    startTime: "09:30:00",
  }), {
    repository: "feed-mina/kiba_2026",
    issue: 12,
    title: "주간 보고",
    startDate: "2026-08-03",
    endDate: "2026-08-03",
    startTime: "09:30",
    endTime: "",
    note: "",
    updatedAt: "",
  });
});

test("places multi-day entries on each day and filters by repository", () => {
  const entries = [
    { repository: "example/one", issue: 1, title: "Release", startDate: "2026-08-03", endDate: "2026-08-05", startTime: "10:00" },
    { repository: "example/two", issue: 2, title: "Review", startDate: "2026-08-03", endDate: "2026-08-03" },
  ];
  assert.deepEqual(entriesForDate(entries, "2026-08-04").map((entry) => entry.issue), [1]);
  assert.deepEqual(entriesForDate(entries, "2026-08-03", "example/two").map((entry) => entry.issue), [2]);
  assert.equal(calendarDays(new Date(2026, 7, 3), "week", entries).length, 7);
});

test("moves week and month cursors by the selected view", () => {
  assert.equal(toDateKey(shiftCalendar(new Date(2026, 7, 3), "week", 1)), "2026-08-10");
  assert.equal(toDateKey(shiftCalendar(new Date(2026, 7, 3), "month", -1)), "2026-07-01");
});
