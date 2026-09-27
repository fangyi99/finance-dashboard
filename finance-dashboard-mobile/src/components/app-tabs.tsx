import { Tabs } from "expo-router";
import { useEffect, useState } from "react";
import { useColorScheme, Image } from "react-native";

import { Colors } from "@/constants/theme";
import { API_URL, CURRENT_USER_ID } from "@/constants/config";

export default function AppTabs() {
  const scheme = useColorScheme();
  const colors =
    Colors[scheme === "unspecified" ? "light" : (scheme ?? "light")];

  const [enabledTabs, setEnabledTabs] = useState<string[]>([
    "dashboard",
    "accounts",
    "settings",
  ]);

  useEffect(() => {
    fetch(`${API_URL}/tab-preferences/${CURRENT_USER_ID}`)
      .then((res) => res.json())
      .then((prefs) => {
        if (Array.isArray(prefs)) {
          setEnabledTabs(
            prefs.filter((p: any) => p.is_enabled).map((p: any) => p.tab_key),
          );
        }
      })
      .catch((err) => console.error("Failed to load tab preferences", err));
  }, []);

  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.text,
        tabBarStyle: { backgroundColor: colors.background },
        headerShown: true,
        headerStyle: { backgroundColor: colors.background },
        headerTintColor: colors.text,
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Dashboard",
          tabBarLabel: "Dashboard",
          href: enabledTabs.includes("dashboard") ? undefined : null,
          tabBarIcon: ({ color, size }) => (
            <Image
              source={require("@/assets/images/tabIcons/home.png")}
              style={{ width: size, height: size, tintColor: color }}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="accounts"
        options={{
          title: "Accounts",
          tabBarLabel: "Accounts",
          // no href override — always visible, never hidden
        }}
      />
      <Tabs.Screen
        name="cash-flow"
        options={{
          title: "Cash Flow",
          tabBarLabel: "Cash Flow",
          href: enabledTabs.includes("cash_flow") ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="budget"
        options={{
          title: "Budget",
          tabBarLabel: "Budget",
          href: enabledTabs.includes("budget") ? undefined : null,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: "Settings",
          tabBarLabel: "Settings",
          // no href override — always visible, never hidden
        }}
      />
    </Tabs>
  );
}
