import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Button,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { formatDate, formatMoney } from "@/utils/format";

interface Account {
  id: string;
  source: "stripe" | "csv_import" | "pdf_import" | "manual";
  display_name: string | null;
  institution_name: string | null;
  currency: string;
  balance: string | null;
  last_synced_at: string | null;
}

export default function AccountsScreen() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Tab screens stay mounted, so a plain useEffect wouldn't refetch after adding an account.
  // useFocusEffect runs every time this tab comes back into view.
  useFocusEffect(
    useCallback(() => {
      let active = true;
      setError("");
      fetch(`${API_URL}/accounts/${CURRENT_USER_ID}`)
        .then((res) => {
          if (!res.ok)
            throw new Error(`Couldn't load accounts (${res.status})`);
          return res.json();
        })
        .then((data) => {
          if (active) setAccounts(data);
        })
        .catch((err) => {
          if (active) setError(err.message);
        })
        .finally(() => {
          if (active) setLoading(false);
        });
      return () => {
        active = false;
      };
    }, []),
  );

  // Stripe can pull fresh data itself; bank accounts need a new e-statement uploaded.
  const handleSync = (account: Account) => {
    // TODO: replace with the PDF e-statement upload (bank accounts) and Stripe sync once built.
    Alert.alert(
      account.source === "stripe" ? "Sync from Stripe" : "Upload e-statement",
      "This is where it will start. It is not built yet.",
    );
  };

  return (
    <View style={styles.container}>
      <Button title="Add account" onPress={() => router.push("/add-account")} />

      {loading && <ActivityIndicator style={{ marginTop: 20 }} />}
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <FlatList
        style={{ marginTop: 16 }}
        data={accounts}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={
          !loading && !error ? (
            <Text style={styles.empty}>
              No accounts yet. Add one to get started.
            </Text>
          ) : null
        }
        renderItem={({ item }) => (
          <View style={styles.card}>
            <View style={styles.cardTop}>
              <Text style={styles.cardTitle} numberOfLines={1}>
                {item.display_name || item.institution_name || "Account"}
              </Text>
              <View style={styles.actions}>
                <Pressable
                  onPress={() => handleSync(item)}
                  style={styles.iconButton}
                  accessibilityLabel={
                    item.source === "stripe"
                      ? "Sync account"
                      : "Upload e-statement"
                  }
                >
                  <Text style={styles.iconText}>
                    {item.source === "stripe" ? "↻" : "↑"}
                  </Text>
                </Pressable>
                <Pressable
                  onPress={() =>
                    router.push({
                      pathname: "/account/[id]",
                      params: { id: item.id },
                    })
                  }
                  style={styles.iconButton}
                  accessibilityLabel="View account details"
                >
                  <Text style={styles.iconText}>›</Text>
                </Pressable>
              </View>
            </View>

            <Text style={styles.balance}>
              {formatMoney(item.balance, item.currency)}
            </Text>
            <Text style={styles.lastSync}>
              {item.last_synced_at
                ? `Last synced ${formatDate(item.last_synced_at)}`
                : "Not synced yet"}
            </Text>
          </View>
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, padding: 16 },
  card: {
    borderWidth: 1,
    borderColor: "#ddd",
    borderRadius: 10,
    padding: 16,
    marginBottom: 12,
  },
  cardTop: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  cardTitle: { fontSize: 16, fontWeight: "bold", flex: 1, marginRight: 8 },
  actions: { flexDirection: "row", gap: 8 },
  iconButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: "#ddd",
    alignItems: "center",
    justifyContent: "center",
  },
  iconText: { fontSize: 18 },
  balance: { fontSize: 22, fontWeight: "600", marginTop: 10 },
  lastSync: { color: "#999", fontSize: 11, marginTop: 4 },
  empty: { color: "#999", textAlign: "center", marginTop: 32 },
  error: { color: "red", marginTop: 16 },
});
