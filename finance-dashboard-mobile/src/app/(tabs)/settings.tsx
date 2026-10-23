import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { useRouter } from "expo-router";

// A browser shows nothing for Alert.alert, so without this the "Are you sure?" below would never appear on web.
// (Installing it is harmless on a phone and when it's already installed.)
import "@/utils/web-alert";
import {
  enterSandbox,
  leaveSandbox,
  resetSandbox,
  useSession,
} from "@/utils/session";

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
        href: "/recurring",
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

// What to tell someone when a request to the backend fails.
function friendly(e: unknown): string {
  const message = e instanceof Error ? e.message : String(e);
  if (/network request failed|failed to fetch|network error/i.test(message)) {
    return "Couldn't reach the server. Check that the backend is running and your phone is on the same Wi-Fi.";
  }
  return message;
}

export default function SettingsScreen() {
  const router = useRouter();
  const session = useSession();

  async function onToggleSandbox(next: boolean) {
    try {
      if (next) await enterSandbox();
      else leaveSandbox();
    } catch (e) {
      Alert.alert("Couldn't start sandbox mode", friendly(e));
    }
  }

  function onResetSandbox() {
    const inSandbox = session.sandbox;
    Alert.alert(
      "Reset sandbox data?",
      inSandbox
        ? "Anything you've changed in the sandbox is thrown away and the sample data goes back to how it started. Your real data isn't affected."
        : "The sample data is rebuilt from scratch. Your real data isn't affected, and sandbox mode stays off.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Reset",
          style: "destructive",
          onPress: async () => {
            try {
              await resetSandbox();
              Alert.alert(
                "Sandbox reset",
                inSandbox
                  ? "The sample data is back to how it started."
                  : "The sample data has been rebuilt. Switch sandbox mode on to see it.",
              );
            } catch (e) {
              Alert.alert("Couldn't reset the sandbox", friendly(e));
            }
          },
        },
      ],
    );
  }

  return (
    <ScrollView style={styles.page} contentContainerStyle={{ padding: 16 }}>
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>Sandbox</Text>
        <View style={styles.row}>
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Sandbox mode</Text>
            <Text style={styles.sublabel}>
              {session.sandbox
                ? "You're using sample data. Switch it off to go back to your own accounts."
                : "Try the app with sample data. Your real accounts aren't touched."}
            </Text>
          </View>
          {session.busy ? (
            <ActivityIndicator />
          ) : (
            <Switch value={session.sandbox} onValueChange={onToggleSandbox} />
          )}
        </View>
        <Pressable
          style={styles.row}
          onPress={onResetSandbox}
          disabled={session.busy}
        >
          <View style={{ flex: 1 }}>
            <Text style={styles.label}>Reset sandbox data</Text>
            <Text style={styles.sublabel}>
              {session.sandbox
                ? "Put the sample data back the way it started"
                : "Rebuild the sample data. Sandbox mode stays off."}
            </Text>
          </View>
          <Text style={styles.chevron}>›</Text>
        </Pressable>
      </View>

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
