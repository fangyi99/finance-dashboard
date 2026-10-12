// The named options a suggestion arrives with (the detector only finds these).
export type Frequency = "weekly" | "biweekly" | "monthly" | "yearly";

// ---- repeat as "every N <unit>" ------------------------------------------------------------

export type Unit = "day" | "week" | "month" | "year";

export const UNITS: Unit[] = ["day", "week", "month", "year"];

// How many the number wheel offers for each unit. Wide enough for the real cases (every
// 6 months, every 12 weeks, every 30 days) without offering silly ones like every 40 years.
const MAX_COUNT: Record<Unit, number> = {
  day: 30,
  week: 12,
  month: 12,
  year: 5,
};

export function maxCount(unit: Unit): number {
  return MAX_COUNT[unit];
}

// What the unit wheel shows: always "day(s)", "week(s)"... — it doesn't change with the
// number beside it, so there's no singular/plural to work out.
export function unitOptionLabel(unit: Unit): string {
  return `${unit}(s)`;
}

// The name shown for a repeat: the familiar one where there is one, else "Every 3 months".
export function repeatLabel(count: number, unit: Unit): string {
  if (count === 1) {
    return { day: "Daily", week: "Weekly", month: "Monthly", year: "Yearly" }[
      unit
    ];
  }
  if (count === 2 && unit === "week") return "Every 2 weeks";
  // A count of 1 was handled above (Daily, Weekly...), so anything here is 2 or more: always plural.
  return `Every ${count} ${unit}s`;
}

// Lower-cased, for the middle of a sentence: "Repeats every 3 months from this date."
export function repeatPhrase(count: number, unit: Unit): string {
  return repeatLabel(count, unit).toLowerCase();
}

// An ISO date ("2026-11-05") as a local calendar date. Parsing the string with `new Date()`
// treats it as midnight UTC, which can land on the wrong day depending on the time zone.
function localDate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

// "Today", "Tomorrow", "in 4 days", or a plain date once it's a week or more away.
export function dueLabel(iso: string, now: Date = new Date()): string {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const days = Math.round(
    (localDate(iso).getTime() - today.getTime()) / 86400000,
  );

  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days > 1 && days < 7) return `in ${days} days`;
  return localDate(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
  });
}

// "Seen 5 times" etc. for a suggestion.
export function seenLabel(occurrences: number): string {
  return `Seen ${occurrences} times`;
}

// ---- the "add a recurring transaction" form ----------------------------------------------

export type Kind = "expense" | "income" | "transfer";
export type Direction = "out" | "in";

export const KIND_OPTIONS: { value: Kind; label: string }[] = [
  { value: "expense", label: "Expense" },
  { value: "income", label: "Income" },
  { value: "transfer", label: "Transfer" },
];

export const DIRECTION_OPTIONS: { value: Direction; label: string }[] = [
  { value: "out", label: "Money out" },
  { value: "in", label: "Money in" },
];

// Typed as DD/MM/YYYY, matching how Singapore statements write dates. Slashes are added as
// you type, so only digits are ever needed.
export function formatDateInput(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 8);
  return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)]
    .filter(Boolean)
    .join("/");
}

// "05/11/2026" -> "2026-11-05", or null if it isn't a real calendar date (31/02, 13th month...).
export function parseDateInput(text: string): string | null {
  const match = /^(\d{2})\/(\d{2})\/(\d{4})$/.exec(text);
  if (!match) return null;
  const [day, month, year] = [
    Number(match[1]),
    Number(match[2]),
    Number(match[3]),
  ];
  if (year < 2000 || year > 2100) return null;

  const date = new Date(year, month - 1, day);
  if (
    date.getFullYear() !== year ||
    date.getMonth() !== month - 1 ||
    date.getDate() !== day
  )
    return null;
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

export function todayInput(now: Date = new Date()): string {
  return [
    String(now.getDate()).padStart(2, "0"),
    String(now.getMonth() + 1).padStart(2, "0"),
    now.getFullYear(),
  ].join("/");
}

// Digits and a single decimal point, at most two decimal places.
export function sanitizeAmount(text: string): string {
  const cleaned = text.replace(/[^\d.]/g, "");
  const [whole, ...rest] = cleaned.split(".");
  if (rest.length === 0) return whole;
  return `${whole}.${rest.join("").slice(0, 2)}`;
}

export interface RecurringFormState {
  kind: Kind;
  direction: Direction; // only used when kind is 'transfer'
  date: string; // as typed, DD/MM/YYYY
  intervalCount: number;
  intervalUnit: Unit;
  accountId: string | null;
  categoryId: string | null;
  description: string;
  amount: string;
}

// What's wrong with the form, in the words to show the user — or null if it's fine.
// A rule that follows real transactions has no date of its own, so its form has no date field
// and `dateRequired` is false.
export function validateForm(
  form: RecurringFormState,
  accountRequired: boolean,
  dateRequired = true,
): string | null {
  if (!form.description.trim()) return "Add a description.";
  if (!(Number(form.amount) > 0)) return "Enter an amount above zero.";
  if (dateRequired && !parseDateInput(form.date))
    return "Enter a valid date as DD/MM/YYYY.";
  if (accountRequired && !form.accountId) return "Choose an account.";
  return null;
}

export function buildManualPayload(userId: string, form: RecurringFormState) {
  return {
    user_id: userId,
    kind: form.kind,
    // Direction only means something for a transfer; an expense is always out, income in.
    direction: form.kind === "transfer" ? form.direction : "out",
    description: form.description.trim(),
    amount: Number(form.amount).toFixed(2),
    start_date: parseDateInput(form.date),
    interval_count: form.intervalCount,
    interval_unit: form.intervalUnit,
    account_id: form.accountId,
    category_id: form.categoryId,
  };
}

// ---- editing an existing rule ---------------------------------------------------------------

// "2026-11-05" -> "05/11/2026": how the form shows a date.
export function isoToInput(iso: string): string {
  const [year, month, day] = iso.split("-");
  return `${day}/${month}/${year}`;
}

// One rule as the Edit form receives it (GET /recurring/by-id/{id}).
export interface EditableRule {
  id: string;
  description: string | null;
  merchant_pattern?: string | null;
  expected_amount: string | null; // signed: negative is money out
  interval_count: number;
  interval_unit: Unit;
  next_due_date: string | null;
  account_id: string | null;
  category_id: string | null;
  category_name?: string | null;
  // True when its dates come from real transactions; false for one made by hand.
  follows_transactions: boolean;
  kind: Kind;
  direction: Direction;
}

// The form's starting values for a rule: the amount shows without its sign, because the
// type (and direction) say which way the money goes.
export function formFromRule(rule: EditableRule): RecurringFormState {
  return {
    kind: rule.kind,
    direction: rule.direction,
    date: rule.next_due_date ? isoToInput(rule.next_due_date) : "",
    intervalCount: rule.interval_count,
    intervalUnit: rule.interval_unit,
    accountId: rule.account_id,
    categoryId: rule.category_id,
    description: ruleTitle(rule),
    amount: rule.expected_amount
      ? Math.abs(Number(rule.expected_amount)).toFixed(2)
      : "",
  };
}

// What to send to save an edit. A rule that follows real transactions is sent no date:
// it has none to set (the server refuses one).
export function buildEditPayload(
  form: RecurringFormState,
  rule: Pick<EditableRule, "follows_transactions">,
) {
  return {
    description: form.description.trim(),
    kind: form.kind,
    // Direction only means something for a transfer.
    ...(form.kind === "transfer" ? { direction: form.direction } : {}),
    amount: Number(form.amount).toFixed(2),
    interval_count: form.intervalCount,
    interval_unit: form.intervalUnit,
    account_id: form.accountId,
    category_id: form.categoryId,
    ...(rule.follows_transactions
      ? {}
      : { next_due_date: parseDateInput(form.date) }),
  };
}

interface CategoryLike {
  id: string;
  name: string;
  parent_category_id: string | null;
  type: string;
}

// Only categories of the chosen type, parents and children both, children labelled with
// their parent ("Food › Dining") so the flat list stays unambiguous.
export function categoryChoices(
  categories: CategoryLike[],
  kind: Kind,
): { label: string; id: string }[] {
  const byId = new Map(categories.map((c) => [c.id, c]));
  return categories
    .filter((c) => c.type === kind)
    .map((c) => {
      const parent = c.parent_category_id
        ? byId.get(c.parent_category_id)
        : undefined;
      return {
        label: parent ? `${parent.name} › ${c.name}` : c.name,
        id: c.id,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

interface AccountLike {
  id: string;
  display_name: string | null;
  institution_name: string | null;
}

// A readable, unique label per account (two accounts can share a name).
export function accountChoices(
  accounts: AccountLike[],
): { label: string; id: string }[] {
  const seen = new Map<string, number>();
  return accounts.map((a) => {
    const base = a.display_name || a.institution_name || "Account";
    const count = (seen.get(base) ?? 0) + 1;
    seen.set(base, count);
    return { label: count === 1 ? base : `${base} (${count})`, id: a.id };
  });
}

// What to call a recurring item: its description, else its name. The description is what
// the user typed (or was filled in when they approved a suggestion), so it's nearly always
// there; the fallback is the name of the charge it was spotted from, and failing that its
// category. A hand-made rule's internal key ("manual:...") is never shown.
export function ruleTitle(rule: {
  description?: string | null;
  merchant_pattern?: string | null;
  category_name?: string | null;
}): string {
  const description = rule.description?.trim();
  if (description) return description;
  const pattern = rule.merchant_pattern?.trim();
  if (pattern && !pattern.startsWith("manual:")) {
    return pattern.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return rule.category_name || "Recurring transaction";
}
