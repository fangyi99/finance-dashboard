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
    </Stack>
  );
}
