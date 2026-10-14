import { formatNumber } from "@/utils/format";

// One budget as the API sends it. Amounts arrive as strings ("1234.50") so parse before maths.
export interface Budget {
  id: string;
  name: string;
  amount: string; // the monthly limit
  spent: string; // so far this month
  remaining: string; // amount - spent; negative once exceeded
  category_id: string | null; // null: it tracks all spending
  category_name: string | null;
  month: string; // "2026-10"
}

// "$1,234.50", and "-$20.00" for a negative.
export function formatDollars(
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined) return "—";
  const num = Number(value);
  return `${num < 0 ? "-" : ""}$${formatNumber(Math.abs(num))}`;
}

// ---- the bar -------------------------------------------------------------------------------

export type BudgetStatus = "ok" | "warning" | "danger";

export const BUDGET_COLORS: Record<BudgetStatus, string> = {
  ok: "#1a9e4b", // plenty left
  warning: "#e08a00", // getting close
  danger: "#d93025", // used up, or over
};

// The bar turns amber from here, and red once the budget is fully used.
export const WARNING_AT = 75;

export interface BudgetProgress {
  percent: number; // the true figure: can be 0 or above 100
  fill: number; // how much of the bar to colour: 0 to 100
  label: number; // the whole number written on the bar
  status: BudgetStatus;
}

export function budgetProgress(
  spent: string | number,
  amount: string | number,
): BudgetProgress {
  const spentNum = Number(spent);
  const amountNum = Number(amount);
  const percent = amountNum > 0 ? (spentNum / amountNum) * 100 : 0;

  let label = Math.round(Math.max(0, percent));
  // 99.6% rounds to 100%, which reads as "used up" while there's still money left.
  if (spentNum < amountNum && label >= 100) label = 99;

  return {
    percent,
    fill: Math.max(0, Math.min(100, percent)),
    label,
    status:
      percent >= 100 ? "danger" : percent >= WARNING_AT ? "warning" : "ok",
  };
}

// ---- the add / edit form -------------------------------------------------------------------

export interface BudgetFormState {
  name: string;
  amount: string; // as typed
  categoryId: string | null; // null: all spending
}

export const EMPTY_BUDGET_FORM: BudgetFormState = {
  name: "",
  amount: "",
  categoryId: null,
};

// What's wrong with the form, in the words to show the user — or null if it's fine.
export function validateBudgetForm(form: BudgetFormState): string | null {
  if (!form.name.trim()) return "Add a budget name.";
  if (!(Number(form.amount) > 0)) return "Enter an amount above zero.";
  return null;
}

export function buildBudgetPayload(userId: string, form: BudgetFormState) {
  return {
    user_id: userId,
    name: form.name.trim(),
    amount: Number(form.amount).toFixed(2),
    category_id: form.categoryId,
  };
}

// For an edit. category_id is always sent, so choosing "All spending" (null) clears it.
export function buildBudgetUpdate(form: BudgetFormState) {
  return {
    name: form.name.trim(),
    amount: Number(form.amount).toFixed(2),
    category_id: form.categoryId,
  };
}

export function formFromBudget(
  budget: Pick<Budget, "name" | "amount" | "category_id">,
): BudgetFormState {
  return {
    name: budget.name,
    amount: Number(budget.amount).toFixed(2),
    categoryId: budget.category_id,
  };
}

// ---- the dashboard widget -------------------------------------------------------------------

// How many budgets the dashboard widget lists; the rest fold into "+N other budgets".
export const WIDGET_BUDGET_COUNT = 3;

// Closest to the limit first: the highest percentage used leads, so anything over budget is
// always on top. Equal percentages fall back to alphabetical, so the order never jumps about.
export function rankBudgets(budgets: Budget[]): Budget[] {
  return [...budgets].sort((a, b) => {
    const difference =
      budgetProgress(b.spent, b.amount).percent -
      budgetProgress(a.spent, a.amount).percent;
    return difference !== 0 ? difference : a.name.localeCompare(b.name);
  });
}

export interface BudgetSummary {
  top: Budget[]; // the ones to list
  otherCount: number; // how many more there are
  over: number; // budgets that have gone past their limit (across ALL of them, listed or not)
  near: number; // budgets at 75% or more that haven't gone past it
}

export function summarizeBudgets(
  budgets: Budget[],
  n: number = WIDGET_BUDGET_COUNT,
): BudgetSummary {
  const ranked = rankBudgets(budgets);
  let over = 0;
  let near = 0;
  for (const budget of ranked) {
    if (Number(budget.remaining) < 0) over += 1;
    else if (budgetProgress(budget.spent, budget.amount).percent >= WARNING_AT)
      near += 1;
  }
  return {
    top: ranked.slice(0, n),
    otherCount: Math.max(0, ranked.length - n),
    over,
    near,
  };
}

export function otherBudgetsLabel(count: number): string {
  return `+${count} other ${count === 1 ? "budget" : "budgets"}`;
}

export interface StatusPart {
  text: string;
  tone: BudgetStatus; // picks the colour, same as the bars
}

// The line under the widget's title: a count of what needs attention, instead of a total
// (budgets overlap, and a total would hide one overspent budget behind comfortable ones).
// When nothing needs attention there's nothing to say, so it's empty and no line is drawn.
export function budgetStatusParts(over: number, near: number): StatusPart[] {
  const parts: StatusPart[] = [];
  if (over > 0) parts.push({ text: `${over} over budget`, tone: "danger" });
  if (near > 0)
    parts.push({ text: `${near} close to the limit`, tone: "warning" });
  return parts;
}

// What's left, in words: "$375.00 left", or "$20.00 over" once it's been exceeded. A bare
// number in a small row would be ambiguous (is it what I've spent?).
export function remainingWords(remaining: string | number): {
  text: string;
  over: boolean;
} {
  const amount = Number(remaining);
  return amount < 0
    ? { text: `${formatDollars(Math.abs(amount))} over`, over: true }
    : { text: `${formatDollars(amount)} left`, over: false };
}
