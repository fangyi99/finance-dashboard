import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";

interface Row {
  label: string;
  sublabel: string;
  href?: string;
  params?: Record<string, string>;
  comingSoon?: boolean;
}

const SECTIONS: { title: string; rows: Row[] }[] = [
  {
    title: "Payments & Accounts",
    rows: [
      {
        label: "Accounts",
        sublabel: "Manage your linked accounts",
        href: "/accounts",
      },
      {
        label: "Recurring Transactions",
        sublabel: "Subscriptions and other regular charges",
        comingSoon: true,
      },
    ],
  },
  {
    title: "Organisation",
    rows: [
      {
        label: "Categories",
        sublabel: "Manage spending and income categories",
        href: "/manage-categories",
      },
    ],
  },
  {
    title: "Display & Preferences",
    rows: [
      {
        label: "Currency",
        sublabel: "Your default display currency",
        comingSoon: true,
      },
      {
        label: "Dashboard Widgets",
        sublabel: "Choose what shows on your dashboard",
        href: "/onboarding",
        params: { from: "settings" },
      },
      {
        label: "Tabs",
        sublabel: "Choose which tabs are visible",
        href: "/tab-onboarding",
        params: { from: "settings" },
      },
    ],
  },
];

export default function SettingsScreen() {
  const router = useRouter();

  return (
    <ScrollView style={styles.page} contentContainerStyle={{ padding: 16 }}>
      {SECTIONS.map((section) => (
        <View key={section.title} style={styles.section}>
          <Text style={styles.sectionHeader}>{section.title}</Text>
          {section.rows.map((row) => (
            <Pressable
              key={row.label}
              style={[styles.row, row.comingSoon && styles.rowDisabled]}
              onPress={() => {
                if (row.comingSoon) {
                  Alert.alert(row.label, "This isn't built yet.");
                } else if (row.href) {
                  router.push({
                    pathname: row.href,
                    params: row.params,
                  } as any);
                }
              }}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>{row.label}</Text>
                <Text style={styles.sublabel}>{row.sublabel}</Text>
              </View>
              {row.comingSoon ? (
                <Text style={styles.soon}>Coming soon</Text>
              ) : (
                <Text style={styles.chevron}>›</Text>
              )}
            </Pressable>
          ))}
        </View>
      ))}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  section: { marginBottom: 20 },
  sectionHeader: {
    fontSize: 13,
    fontWeight: "700",
    color: "#666",
    backgroundColor: "#f2f2f2",
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 8,
    marginBottom: 8,
    textTransform: "uppercase",
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 10,
    padding: 16,
    marginBottom: 10,
  },
  rowDisabled: { opacity: 0.6 },
  label: { fontSize: 16, fontWeight: "600" },
  sublabel: { color: "#999", fontSize: 12, marginTop: 2 },
  chevron: { fontSize: 20, color: "#ccc", marginLeft: 8 },
  soon: { color: "#999", fontSize: 11 },
});
