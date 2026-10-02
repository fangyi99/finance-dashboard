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
  source: "stripe" | "csv_import" | "pdf_import" | "manual" | null;
  display_name: string | null;
  institution_name: string | null;
  currency: string;
  balance: string | null;
  last_synced_at: string | null;
}

function formatDetail(detail: unknown): string {
  if (Array.isArray(detail)) return detail.map((d: any) => d.msg).join(", ");
  return typeof detail === "string" ? detail : "Something went wrong";
}

export default function AccountsScreen() {
  const router = useRouter();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    setError("");
    return fetch(`${API_URL}/accounts/${CURRENT_USER_ID}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Couldn't load accounts (${res.status})`);
        return res.json();
      })
      .then((data) => setAccounts(data))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  // Tab screens stay mounted, so a plain useEffect wouldn't refetch after adding an account.
  // useFocusEffect runs every time this tab comes back into view.
  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const runStripeSync = async (accountId: string) => {
    const res = await fetch(`${API_URL}/accounts/${accountId}/sync-stripe`, {
      method: "POST",
    });
    const data = await res.json();
    if (!res.ok) throw new Error(formatDetail(data.detail));
    await load();
    Alert.alert(
      "Synced",
      data.imported > 0
        ? `Imported ${data.imported} new transaction${data.imported === 1 ? "" : "s"}.`
        : "No new transactions since the last sync.",
    );
  };

  const runPdfImport = () => {
    // TODO: replace with the actual PDF e-statement upload flow once it's built.
    Alert.alert(
      "Upload e-statement",
      "This is where it will start. It is not built yet.",
    );
  };

  const lockMethodAndProceed = async (
    account: Account,
    method: "pdf_import" | "stripe",
  ) => {
    setBusyId(account.id);
    try {
      const res = await fetch(
        `${API_URL}/accounts/${account.id}/import-method`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ method }),
        },
      );
      const data = await res.json();
      if (!res.ok) throw new Error(formatDetail(data.detail));

      if (method === "stripe") {
        await runStripeSync(account.id);
      } else {
        await load();
        runPdfImport();
      }
    } catch (err: any) {
      Alert.alert("Couldn't set import method", err.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleSync = (account: Account) => {
    if (account.source === null) {
      Alert.alert(
        "Choose import method",
        "This choice is permanent for this account and can't be changed later.",
        [
          { text: "Cancel", style: "cancel" },
          {
            text: "E-statement (PDF)",
            onPress: () => lockMethodAndProceed(account, "pdf_import"),
          },
          {
            text: "Stripe",
            onPress: () => lockMethodAndProceed(account, "stripe"),
          },
        ],
      );
      return;
    }

    if (account.source === "stripe") {
      setBusyId(account.id);
      runStripeSync(account.id)
        .catch((err: any) => Alert.alert("Sync failed", err.message))
        .finally(() => setBusyId(null));
    } else {
      runPdfImport();
    }
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
                  disabled={busyId === item.id}
                  style={styles.iconButton}
                  accessibilityLabel={
                    item.source === null
                      ? "Choose import method"
                      : item.source === "stripe"
                        ? "Sync account"
                        : "Upload e-statement"
                  }
                >
                  {busyId === item.id ? (
                    <ActivityIndicator size="small" />
                  ) : (
                    <Text style={styles.iconText}>
                      {item.source === null
                        ? "+"
                        : item.source === "stripe"
                          ? "↻"
                          : "↑"}
                    </Text>
                  )}
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
              {item.source === null
                ? "Tap + to choose how to import transactions"
                : item.last_synced_at
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
    borderColor: "#eee",
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
