import { Stack } from "expo-router";

export default function RootLayout() {
  return (
    <Stack>
      <Stack.Screen name="onboarding" options={{ headerShown: false }} />
      <Stack.Screen name="tab-onboarding" options={{ headerShown: false }} />
      <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      <Stack.Screen
        name="add-transaction"
        options={{ presentation: "modal", title: "Add Transaction" }}
      />
      <Stack.Screen name="import-csv" options={{ title: "Import CSV" }} />
      <Stack.Screen name="account/[id]/index" options={{ title: "Account" }} />
      <Stack.Screen
        name="account/[id]/edit"
        options={{ presentation: "modal" }}
      />
      <Stack.Screen name="account/[id]/transactions" options={{}} />
      <Stack.Screen name="manage-categories" options={{}} />
      <Stack.Screen name="category-form" options={{ presentation: "modal" }} />
    </Stack>
  );
}
