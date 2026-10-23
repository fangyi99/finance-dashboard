// The review queue: transactions the app couldn't place, grouped by payee so one answer covers many.
// The backend does the grouping (see app/review.py); this file is the API calls and the small decisions
// the screens make about what to show.

import { Alert } from "react-native";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { Category } from "@/utils/categoryTree";
import { formatDate, formatNumber } from "@/utils/format";

export interface ReviewSuggestion {
  category_id: string | null;
  category_name: string;
  exists: boolean; // false: you don't have this category yet, so accepting creates it
  strong: boolean; // false: a last-resort guess, which is wrong more often than right
  reason: string | null;
  votes: number;
}

export interface ReviewSample {
  id: string;
  date: string;
  description: string;
  amount: string;
}

export interface ReviewGroup {
  key: string;
  label: string;
  direction: "in" | "out";
  count: number;
  total: string;
  average: string;
  currency: string;
  first_date: string;
  last_date: string;
  suggestion: ReviewSuggestion | null;
  both_directions: boolean; // you also have this payee going the other way
  samples: ReviewSample[];
}

export interface ReviewSummary {
  groups: number;
  transactions: number;
  spend_total: string;
  currency: string;
  skipped_groups: number;
  skipped_transactions: number;
}

export interface QuickChoice {
  id: string;
  name: string;
  type: string;
}

export interface ReviewData {
  groups: ReviewGroup[];
  summary: ReviewSummary;
  quick_choices: { out: QuickChoice[]; in: QuickChoice[] };
}

export interface ReviewReply {
  summary: ReviewSummary;
  resolved?: number;
  category?: { id: string; name: string };
  created_category?: boolean;
  rule?: string | null;
  also_filed?: number;
}

export type Choice = { categoryId: string } | { newCategory: string };

// ---- the API ---------------------------------------------------------------------------------------------
async function errorText(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
  } catch {
    // not JSON: fall through
  }
  return `The server returned an error (${res.status}).`;
}

export class ReviewRequestError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, init);
  if (!res.ok) throw new ReviewRequestError(await errorText(res), res.status);
  return res.json();
}

const post = <T>(path: string, body: object) =>
  request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const loadReview = (skipped = false) =>
  request<ReviewData>(`/review/${CURRENT_USER_ID}?skipped=${skipped}`);
export const loadReviewSummary = () =>
  request<ReviewSummary>(`/review/${CURRENT_USER_ID}/summary`);

export const resolveGroup = (
  groupKey: string,
  choice: Choice,
  applyToAll: boolean,
) =>
  post<ReviewReply>("/review/resolve", {
    user_id: CURRENT_USER_ID,
    group_key: groupKey,
    apply_to_all: applyToAll,
    ...("categoryId" in choice
      ? { category_id: choice.categoryId }
      : { new_category: { name: choice.newCategory } }),
  });

export const skipGroup = (groupKey: string) =>
  post<ReviewReply>("/review/skip", {
    user_id: CURRENT_USER_ID,
    group_key: groupKey,
  });
export const unskipGroup = (groupKey: string) =>
  post<ReviewReply>("/review/unskip", {
    user_id: CURRENT_USER_ID,
    group_key: groupKey,
  });

// What to tell someone when a request fails. A dropped connection is the usual cause, so say that in plain words.
export function describeError(e: unknown): string {
  const message = e instanceof Error ? e.message : String(e);
  if (/network request failed|failed to fetch|network error/i.test(message)) {
    return "Couldn't reach the server. Check that the backend is running and your phone is on the same Wi-Fi.";
  }
  return message;
}

// ---- what to show ------------------------------------------------------------------------------------------
export type Offer =
  | { kind: "use"; categoryId: string; name: string; reason: string | null } // a suggestion with evidence, and you have the category
  | { kind: "create"; name: string; reason: string | null } // a suggestion with evidence, but you don't have the category yet
  | { kind: "choose" }; // nothing worth pre-selecting: ask the person

// A weak guess is NOT offered as the answer: the last-resort "Shopping" has been right well under half the time,
// so pre-selecting it would be a trap. The person is asked to choose instead.
export function offerFor(group: ReviewGroup): Offer {
  const s = group.suggestion;
  if (!s || !s.strong) return { kind: "choose" };
  if (s.exists && s.category_id)
    return {
      kind: "use",
      categoryId: s.category_id,
      name: s.category_name,
      reason: s.reason,
    };
  return { kind: "create", name: s.category_name, reason: s.reason };
}

// "Always file future payments here" starts ON, except where the same payee also appears going the other way
// (a friend you pay and who pays you back): one rule for both directions could be wrong.
export const defaultApplyToAll = (group: ReviewGroup) => !group.both_directions;

// A payee with no usable name (a fully masked one, or none) can't be turned into a rule.
export const canLearn = (group: ReviewGroup) =>
  group.label !== "Unnamed payee" && group.label !== "No description";

export function groupMeta(group: ReviewGroup): {
  headline: string;
  detail: string;
} {
  const noun =
    group.direction === "out"
      ? group.count === 1
        ? "payment"
        : "payments"
      : group.count === 1
        ? "deposit"
        : "deposits";
  const headline = `${group.count} ${noun} · ${formatNumber(group.total)} ${group.currency}`;
  const range =
    group.first_date === group.last_date
      ? formatDate(group.first_date)
      : `${formatDate(group.first_date)} – ${formatDate(group.last_date)}`;
  const average =
    group.count > 1 ? `avg ${formatNumber(group.average)} · ` : "";
  return { headline, detail: `${average}${range}` };
}

// The categories that make sense for this group: spending categories for money out, income-type for money in.
export function categoriesFor(
  group: ReviewGroup,
  categories: Category[],
): Category[] {
  const wanted =
    group.direction === "out"
      ? ["expense", "transfer"]
      : ["income", "transfer"];
  return categories.filter(
    (c) =>
      wanted.includes(c.type) &&
      !(c.name === "Uncategorized" && c.user_id === null),
  );
}

// After an import, tell the person if some of what they just brought in needs a category. Never blocks the
// import and never complains: if the check fails, it just stays quiet.
export async function promptReviewAfterImport(router: {
  push: (href: any) => void;
}): Promise<void> {
  try {
    const summary = await loadReviewSummary();
    if (summary.transactions === 0) return;
    const things =
      summary.groups === 1
        ? "1 group of transactions needs"
        : `${summary.groups} groups of transactions need`;
    Alert.alert(
      "Some transactions need a category",
      `${things} a category before they count in your budgets.`,
      [
        { text: "Later", style: "cancel" },
        { text: "Review now", onPress: () => router.push("/review") },
      ],
    );
  } catch {
    // quiet on purpose
  }
}
