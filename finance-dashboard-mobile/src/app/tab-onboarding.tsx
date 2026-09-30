import { useEffect, useState } from "react";
import { View, Text, Pressable, Button, StyleSheet } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";

const LOCKED_TABS = new Set(["accounts", "settings"]);

const AVAILABLE_TABS = [
  { key: "dashboard", label: "Dashboard" },
  { key: "accounts", label: "Accounts" },
  { key: "cash_flow", label: "Cash Flow" },
  { key: "budget", label: "Budget" },
  { key: "settings", label: "Settings" },
];

const DEFAULT_SELECTED = ["dashboard", "accounts", "settings"];

export default function TabOnboardingScreen() {
  const router = useRouter();
  const { from } = useLocalSearchParams<{ from?: string }>();
  const [selected, setSelected] = useState<Set<string>>(
    new Set(DEFAULT_SELECTED),
  );
  const [loaded, setLoaded] = useState(false);

  // Same reasoning as the widget picker: load existing choices when this is reached
  // from Settings, rather than resetting to defaults on every visit.
  useEffect(() => {
    fetch(`${API_URL}/tab-preferences/${CURRENT_USER_ID}`)
      .then((res) => res.json())
      .then((prefs) => {
        if (Array.isArray(prefs) && prefs.length > 0) {
          setSelected(
            new Set(
              prefs.filter((p: any) => p.is_enabled).map((p: any) => p.tab_key),
            ),
          );
        }
      })
      .catch((err) =>
        console.error("Failed to load existing tab preferences", err),
      )
      .finally(() => setLoaded(true));
  }, []);

  const toggle = (key: string) => {
    if (LOCKED_TABS.has(key)) return;
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  };

  const handleContinue = async () => {
    const preferences = AVAILABLE_TABS.map((tab, index) => ({
      tab_key: tab.key,
      is_enabled: selected.has(tab.key),
      display_order: index,
    }));

    try {
      await fetch(`${API_URL}/tab-preferences`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: CURRENT_USER_ID, preferences }),
      });
      // First-time setup continues into the app; reached from Settings, just go back.
      if (from === "settings") {
        router.back();
      } else {
        router.replace("/");
      }
    } catch (err) {
      console.error("Failed to save tab preferences", err);
    }
  };

  if (!loaded) return null;

  return (
    <View style={{ padding: 20, paddingTop: 60 }}>
      <Text style={{ fontSize: 22, fontWeight: "bold", marginBottom: 8 }}>
        Customize your tabs
      </Text>
      <Text style={{ color: "#666", marginBottom: 20 }}>
        Accounts and Settings are always available
      </Text>

      {AVAILABLE_TABS.map((tab) => {
        const isSelected = selected.has(tab.key);
        const isLocked = LOCKED_TABS.has(tab.key);
        return (
          <Pressable
            key={tab.key}
            onPress={() => toggle(tab.key)}
            disabled={isLocked}
            style={[
              styles.tabRow,
              isSelected && styles.tabRowSelected,
              isLocked && styles.tabRowLocked,
            ]}
          >
            <Text style={{ fontWeight: "600" }}>{tab.label}</Text>
            {isLocked && (
              <Text style={{ color: "#999", fontSize: 12 }}>Always on</Text>
            )}
          </Pressable>
        );
      })}

      <View style={{ marginTop: 20 }}>
        <Button title="Continue" onPress={handleContinue} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  tabRow: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
  },
  tabRowSelected: { borderColor: "#007AFF", backgroundColor: "#EAF3FF" },
  tabRowLocked: { backgroundColor: "#f5f5f5", opacity: 0.7 },
});
