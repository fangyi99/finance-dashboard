// The one list of dashboard widgets. The picker (onboarding) and the dashboard both read
// this, so a widget's name or description can't drift between the two. Keys are what's
// stored in widget_preferences, so changing a key would orphan people's saved choices —
// change labels freely, but leave keys alone.
export const WIDGET_CATALOG = [
  {
    key: "balance_summary",
    label: "Total Balance",
    description: "Combined balance across all your bank accounts",
  },
  {
    key: "monthly_summary",
    label: "Financial Summary",
    description: "Income, expenses and savings for the month",
  },
  {
    key: "top_expenses",
    label: "Top Expenses",
    description: "Your biggest spending categories for the month",
  },
  {
    key: "upcoming_transactions",
    label: "Upcoming Transactions",
    description: "Recurring charges due soon",
  },
] as const;

export type WidgetKey = (typeof WIDGET_CATALOG)[number]["key"];

// What the dashboard shows if nothing has been chosen yet.
export const DEFAULT_WIDGETS: WidgetKey[] = [
  "balance_summary",
  "monthly_summary",
  "top_expenses",
];
