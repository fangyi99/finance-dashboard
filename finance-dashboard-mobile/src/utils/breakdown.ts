import { CHART_PALETTE } from "@/constants/chartColors";

// One bucket as returned by GET /summary/category-breakdown.
export interface BreakdownItem {
  category_id: string;
  category_name: string;
  total: string;
}

export interface BreakdownRow {
  categoryId: string;
  name: string;
  amount: number;
  percent: number;
  color: string;
  isOthersBucket: boolean; // the synthetic "Others" bucket (hidden categories folded together)
}

// Mirrors how Cash Flow prepares the same data: a category's colour comes from its
// position in the API response (before sorting) and the percentage is rounded with
// toFixed(0). Doing it identically is what makes a category look the same on both screens.
export function rankBreakdown(items: BreakdownItem[]): BreakdownRow[] {
  const total = items.reduce((sum, item) => sum + Number(item.total), 0);
  return items
    .map((item, i) => ({
      categoryId: item.category_id,
      name: item.category_name,
      amount: Number(item.total),
      percent:
        total > 0 ? Number(((Number(item.total) / total) * 100).toFixed(0)) : 0,
      color: CHART_PALETTE[i % CHART_PALETTE.length],
      isOthersBucket: item.category_id === "others",
    }))
    .sort((a, b) => b.amount - a.amount);
}

export interface OtherSummary {
  count: number;
  amount: number;
  percent: number;
}

// The first `n` rows, plus one combined summary of everything after them (or null if
// there's nothing after them).
export function summarizeTop(
  rows: BreakdownRow[],
  n: number,
): { top: BreakdownRow[]; other: OtherSummary | null } {
  const top = rows.slice(0, n);
  const rest = rows.slice(n);
  if (rest.length === 0) return { top, other: null };

  const amount = rest.reduce((sum, row) => sum + row.amount, 0);
  const total = rows.reduce((sum, row) => sum + row.amount, 0);
  return {
    top,
    other: {
      count: rest.length,
      amount,
      percent: total > 0 ? Number(((amount / total) * 100).toFixed(0)) : 0,
    },
  };
}

export function otherLabel(count: number): string {
  return `+${count} other ${count === 1 ? "category" : "categories"}`;
}
