export interface Category {
  id: string;
  user_id: string | null; // null = system default
  name: string;
  parent_category_id: string | null;
  type: "income" | "expense" | "transfer";
  is_system_default: boolean;
}

export interface CategoryGroup {
  parent: Category;
  children: Category[];
}

// Flat list -> [{parent, children}], both levels sorted by name, matching the
// two-level cap the backend enforces (a category with a parent can't itself be one).
export function buildCategoryTree(categories: Category[]): CategoryGroup[] {
  const parents = categories
    .filter((c) => c.parent_category_id === null)
    .sort((a, b) => a.name.localeCompare(b.name));

  return parents.map((parent) => ({
    parent,
    children: categories
      .filter((c) => c.parent_category_id === parent.id)
      .sort((a, b) => a.name.localeCompare(b.name)),
  }));
}
