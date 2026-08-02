const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export function toDateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseDateKey(value) {
  if (!DATE_PATTERN.test(String(value || ""))) return null;
  const [year, month, day] = value.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  return toDateKey(date) === value ? date : null;
}

export function normalizeScheduleEntry(input = {}) {
  const startDate = String(input.startDate || "").trim();
  const endDate = String(input.endDate || startDate).trim();
  if (!parseDateKey(startDate) || !parseDateKey(endDate) || endDate < startDate) return null;
  return {
    repository: String(input.repository || "").trim(),
    issue: Number(input.issue),
    title: String(input.title || "").trim(),
    startDate,
    endDate,
    startTime: String(input.startTime || "").trim().slice(0, 5),
    endTime: String(input.endTime || "").trim().slice(0, 5),
    note: String(input.note || "").trim(),
    updatedAt: String(input.updatedAt || "").trim(),
  };
}

export function startOfWeek(input) {
  const date = new Date(input.getFullYear(), input.getMonth(), input.getDate());
  const offset = (date.getDay() + 6) % 7;
  date.setDate(date.getDate() - offset);
  return date;
}

export function calendarRange(cursor, view = "month") {
  if (view === "week") {
    const start = startOfWeek(cursor);
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    return { start, end, days: 7 };
  }
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const start = startOfWeek(first);
  const end = new Date(start);
  end.setDate(end.getDate() + 41);
  return { start, end, days: 42 };
}

export function entriesForDate(entries, dateKey, repository = "all") {
  return entries
    .map(normalizeScheduleEntry)
    .filter(Boolean)
    .filter((entry) => repository === "all" || entry.repository === repository)
    .filter((entry) => entry.startDate <= dateKey && entry.endDate >= dateKey)
    .sort((left, right) => `${left.startTime || "99:99"}${left.title}`.localeCompare(`${right.startTime || "99:99"}${right.title}`, "ko"));
}

export function calendarDays(cursor, view, entries = [], repository = "all") {
  const range = calendarRange(cursor, view);
  return Array.from({ length: range.days }, (_, index) => {
    const date = new Date(range.start);
    date.setDate(date.getDate() + index);
    const key = toDateKey(date);
    return { date, key, entries: entriesForDate(entries, key, repository) };
  });
}

export function shiftCalendar(cursor, view, amount) {
  const next = new Date(cursor.getFullYear(), cursor.getMonth(), cursor.getDate());
  if (view === "week") next.setDate(next.getDate() + (amount * 7));
  else next.setMonth(next.getMonth() + amount, 1);
  return next;
}
