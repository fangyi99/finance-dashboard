import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Stack, useFocusEffect, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { buildCategoryTree, Category } from "@/utils/categoryTree";
import { ActionMenu } from "@/components/ActionMenu";

const TYPES = ["expense", "income", "transfer"] as const;
type CategoryType = (typeof TYPES)[number];

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Something went wrong";
}

export default function ManageCategoriesScreen() {
  const router = useRouter();
  const [categories, setCategories] = useState<Category[]>([]);
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  const [activeType, setActiveType] = useState<CategoryType>("expense");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    setError("");
    Promise.all([
      fetch(`${API_URL}/categories/${CURRENT_USER_ID}`).then((res) => {
        if (!res.ok) throw new Error("Couldn't load categories");
        return res.json();
      }),
      fetch(`${API_URL}/categories/visibility/${CURRENT_USER_ID}`).then(
        (res) => {
          if (!res.ok) throw new Error("Couldn't load visibility settings");
          return res.json();
        },
      ),
    ])
      .then(([cats, hidden]) => {
        setCategories(cats);
        setHiddenIds(new Set(hidden.map((h: any) => h.category_id)));
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const toggleVisibility = async (category: Category) => {
    const nextVisible = hiddenIds.has(category.id);
    // Optimistic: flip immediately, roll back if the request fails.
    setHiddenIds((prev) => {
      const next = new Set(prev);
      nextVisible ? next.delete(category.id) : next.add(category.id);
      return next;
    });
    try {
      const res = await fetch(
        `${API_URL}/categories/${category.id}/visibility?user_id=${CURRENT_USER_ID}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ is_visible: nextVisible }),
        },
      );
      if (!res.ok) throw new Error();
    } catch {
      setHiddenIds((prev) => {
        const next = new Set(prev);
        nextVisible ? next.add(category.id) : next.delete(category.id);
        return next;
      });
      Alert.alert("Couldn't update visibility");
    }
  };

  const handleDelete = (category: Category) => {
    Alert.alert(
      "Delete category",
      `Delete "${category.name}"? Any transactions in it move to Uncategorized.`,
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            try {
              const res = await fetch(
                `${API_URL}/categories/${category.id}?user_id=${CURRENT_USER_ID}`,
                { method: "DELETE" },
              );
              if (!res.ok && res.status !== 204) {
                const data = await res.json().catch(() => ({}));
                throw new Error(formatDetail(data.detail));
              }
              load();
            } catch (err: any) {
              Alert.alert("Could not delete", err.message);
            }
          },
        },
      ],
    );
  };

  if (loading) return <ActivityIndicator style={{ marginTop: 40 }} />;

  const groups = buildCategoryTree(categories).filter(
    (g) => g.parent.type === activeType,
  );

  return (
    <>
      <Stack.Screen
        options={{
          title: "Categories",
          headerRight: () => (
            <Pressable
              onPress={() => router.push("/category-form")}
              hitSlop={8}
            >
              <Text style={styles.headerAdd}>+</Text>
            </Pressable>
          ),
        }}
      />
      <View style={styles.page}>
        <View style={styles.typeToggle}>
          {TYPES.map((t) => (
            <Pressable
              key={t}
              onPress={() => setActiveType(t)}
              style={[
                styles.typeButton,
                activeType === t && styles.typeButtonActive,
              ]}
            >
              <Text
                style={
                  activeType === t ? styles.typeTextActive : styles.typeText
                }
              >
                {t[0].toUpperCase() + t.slice(1)}
              </Text>
            </Pressable>
          ))}
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <Text style={styles.note}>
          Hidden categories are grouped under "Others" in the breakdown
          overview.
        </Text>

        <ScrollView style={{ marginTop: 8 }}>
          {groups.map(({ parent, children }) => (
            <View key={parent.id} style={styles.group}>
              <CategoryRow
                category={parent}
                hidden={hiddenIds.has(parent.id)}
                onToggleVisibility={() => toggleVisibility(parent)}
                onEdit={() =>
                  router.push({
                    pathname: "/category-form",
                    params: { id: parent.id },
                  })
                }
                onDelete={() => handleDelete(parent)}
              />
              {children.map((child) => (
                <View key={child.id} style={{ paddingLeft: 24 }}>
                  <CategoryRow
                    category={child}
                    hidden={hiddenIds.has(child.id)}
                    onToggleVisibility={() => toggleVisibility(child)}
                    onEdit={() =>
                      router.push({
                        pathname: "/category-form",
                        params: { id: child.id },
                      })
                    }
                    onDelete={() => handleDelete(child)}
                  />
                </View>
              ))}
            </View>
          ))}
          {groups.length === 0 && (
            <Text style={styles.empty}>No {activeType} categories yet.</Text>
          )}
        </ScrollView>
      </View>
    </>
  );
}

function CategoryRow({
  category,
  hidden,
  onToggleVisibility,
  onEdit,
  onDelete,
}: {
  category: Category;
  hidden: boolean;
  onToggleVisibility: () => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const locked = category.is_system_default;

  return (
    <View style={styles.row}>
      <Text style={[styles.name, hidden && styles.nameHidden]}>
        {category.name}
      </Text>
      <Pressable
        onPress={onToggleVisibility}
        hitSlop={8}
        style={{ marginRight: 12 }}
      >
        <Text style={styles.eye}>{hidden ? "🙈" : "👁️"}</Text>
      </Pressable>
      <ActionMenu
        disabledLabel={locked ? "Default category" : undefined}
        actions={[
          { label: "Edit", onPress: onEdit },
          { label: "Delete", onPress: onDelete, destructive: true },
        ]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: 16 },
  headerAdd: {
    fontSize: 24,
    color: "#007AFF",
    fontWeight: "400",
    marginRight: 4,
  },
  typeToggle: {
    flexDirection: "row",
    borderRadius: 8,
    overflow: "hidden",
    borderWidth: 1,
    borderColor: "#ddd",
  },
  typeButton: { flex: 1, paddingVertical: 10, alignItems: "center" },
  typeButtonActive: { backgroundColor: "#007AFF" },
  typeText: { color: "#333" },
  typeTextActive: { color: "#fff", fontWeight: "600" },
  note: { color: "#999", fontSize: 12, marginTop: 12 },
  group: { marginBottom: 4 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderColor: "#eee",
  },
  eye: { fontSize: 16 },
  name: { fontSize: 15, flex: 1 },
  nameHidden: { color: "#999" },
  empty: { color: "#999", textAlign: "center", marginTop: 32 },
  error: { color: "red", marginTop: 12 },
});
