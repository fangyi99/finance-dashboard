import { useCallback, useRef, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  View,
} from "react-native";
import { Stack, useFocusEffect } from "expo-router";

import { API_URL, CURRENT_USER_ID } from "@/constants/config";
import { buildCategoryTree, Category } from "@/utils/categoryTree";
import { formatDate, formatMoney, formatNumber } from "@/utils/format";
import {
  canLearn,
  categoriesFor,
  Choice,
  defaultApplyToAll,
  describeError,
  groupMeta,
  loadReview,
  offerFor,
  resolveGroup,
  ReviewData,
  ReviewGroup,
  ReviewReply,
  ReviewRequestError,
  skipGroup,
  unskipGroup,
} from "@/utils/review";
import { useSession } from "@/utils/session";

type ViewName = "todo" | "skipped";

function filedNotice(reply: ReviewReply, group: ReviewGroup): string {
  const n = reply.resolved ?? 0;
  let text = `Filed ${n} ${n === 1 ? "transaction" : "transactions"} under ${reply.category?.name}.`;
  if (reply.created_category)
    text += ` Created the “${reply.category?.name}” category.`;
  if (reply.rule)
    text += ` Future ones from ${group.label} will go there automatically.`;
  if (reply.also_filed)
    text += ` Also filed ${reply.also_filed} earlier ${reply.also_filed === 1 ? "one" : "ones"}.`;
  return text;
}

export default function ReviewScreen() {
  const { version } = useSession(); // reload when the data underneath changes (sandbox on/off, reset)
  const [view, setView] = useState<ViewName>("todo");
  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [categories, setCategories] = useState<Category[]>([]);
  const [picker, setPicker] = useState<ReviewGroup | null>(null);
  const [applyAll, setApplyAll] = useState<Record<string, boolean>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [busyKeys, setBusyKeys] = useState<string[]>([]);
  const inFlight = useRef(new Set<string>()); // a ref, so a second tap in the same instant is caught too

  const load = useCallback(async (which: ViewName) => {
    try {
      setData(await loadReview(which === "skipped"));
      setError("");
    } catch (e) {
      setError(describeError(e)); // the list already on screen stays: a failed refresh doesn't wipe it
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const loadCategories = useCallback(() => {
    fetch(`${API_URL}/categories/${CURRENT_USER_ID}`)
      .then((res) => res.json())
      .then((list) => setCategories(list))
      .catch(() => {});
  }, []);

  useFocusEffect(
    useCallback(() => {
      load(view);
      loadCategories();
    }, [load, loadCategories, view, version]),
  );

  function switchView(next: ViewName) {
    if (next === view) return;
    setView(next);
    setData(null);
    setLoading(true);
    setNotice("");
    setError("");
  }

  // Runs one change to one group. Guards double taps, drops the card on success, and keeps the numbers in step.
  async function act(
    group: ReviewGroup,
    work: () => Promise<ReviewReply>,
    describe: (reply: ReviewReply) => string,
  ) {
    if (inFlight.current.has(group.key)) return;
    inFlight.current.add(group.key);
    setBusyKeys([...inFlight.current]);
    try {
      const reply = await work();
      setData((d) =>
        d
          ? {
              ...d,
              groups: d.groups.filter((g) => g.key !== group.key),
              summary: reply.summary,
            }
          : d,
      );
      setNotice(describe(reply));
      if (reply.created_category) loadCategories();
    } catch (e) {
      if (e instanceof ReviewRequestError && e.status === 404) {
        Alert.alert("Already done", e.message); // dealt with elsewhere: show the current list
        load(view);
      } else {
        Alert.alert("Couldn't save that", describeError(e));
      }
    } finally {
      inFlight.current.delete(group.key);
      setBusyKeys([...inFlight.current]);
    }
  }

  const applyFor = (g: ReviewGroup) =>
    canLearn(g) && (applyAll[g.key] ?? defaultApplyToAll(g));
  const choose = (g: ReviewGroup, choice: Choice) =>
    act(
      g,
      () => resolveGroup(g.key, choice, applyFor(g)),
      (reply) => filedNotice(reply, g),
    );
  const skip = (g: ReviewGroup) =>
    act(
      g,
      () => skipGroup(g.key),
      () => `Skipped ${g.label}. You'll find it under Skipped.`,
    );
  const restore = (g: ReviewGroup) =>
    act(
      g,
      () => unskipGroup(g.key),
      () => `Moved ${g.label} back to review.`,
    );

  const summary = data?.summary;
  const headerOptions = { title: "Review" };

  if (loading && !data) {
    return (
      <View style={styles.page}>
        <Stack.Screen options={headerOptions} />
        <ActivityIndicator style={{ marginTop: 40 }} />
      </View>
    );
  }

  return (
    <View style={styles.page}>
      <Stack.Screen options={headerOptions} />

      <View style={styles.tabs}>
        {(["todo", "skipped"] as ViewName[]).map((name) => {
          const count =
            name === "todo" ? summary?.groups : summary?.skipped_groups;
          return (
            <Pressable
              key={name}
              style={[styles.tab, view === name && styles.tabActive]}
              onPress={() => switchView(name)}
            >
              <Text
                style={[styles.tabText, view === name && styles.tabTextActive]}
              >
                {name === "todo" ? "To review" : "Skipped"}
                {count !== undefined ? ` (${count})` : ""}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 40 }}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => {
              setRefreshing(true);
              load(view);
            }}
          />
        }
      >
        {error && !data ? (
          <View>
            <Text style={styles.error}>{error}</Text>
            <Pressable
              onPress={() => {
                setLoading(true);
                load(view);
              }}
            >
              <Text style={styles.link}>Try again</Text>
            </Pressable>
          </View>
        ) : null}
        {error && data ? (
          <Text style={styles.error}>Couldn't refresh: {error}</Text>
        ) : null}

        {view === "todo" && summary && summary.transactions > 0 ? (
          <Text style={styles.summary}>
            {Number(summary.spend_total) > 0
              ? `${formatMoney(summary.spend_total, summary.currency)} of spending isn't counted in your budgets yet. One answer covers a whole group.`
              : "These aren't in your budgets or summaries until they have a category. One answer covers a whole group."}
          </Text>
        ) : null}
        {notice ? <Text style={styles.notice}>{notice}</Text> : null}

        {data && data.groups.length === 0 ? (
          <View style={styles.emptyBox}>
            <Text style={styles.emptyTitle}>
              {view === "todo" ? "All caught up" : "Nothing skipped"}
            </Text>
            <Text style={styles.emptyText}>
              {view === "todo"
                ? summary && summary.skipped_groups > 0
                  ? `Nothing needs a category right now. You've skipped ${summary.skipped_groups} ${summary.skipped_groups === 1 ? "group" : "groups"}; find ${summary.skipped_groups === 1 ? "it" : "them"} under Skipped.`
                  : "Nothing needs a category right now."
                : "Groups you skip will wait here until you come back to them."}
            </Text>
          </View>
        ) : null}

        {(data?.groups ?? []).map((g) => {
          const offer = offerFor(g);
          const meta = groupMeta(g);
          const busy = busyKeys.includes(g.key);
          const choices = data?.quick_choices[g.direction] ?? [];
          const isOpen = !!expanded[g.key];
          return (
            <View key={g.key} style={[styles.card, busy && styles.cardBusy]}>
              <Text style={styles.label}>{g.label}</Text>
              <Text style={styles.meta}>{meta.headline}</Text>
              <Text style={styles.metaLight}>{meta.detail}</Text>

              <Pressable
                onPress={() =>
                  setExpanded((e) => ({ ...e, [g.key]: !e[g.key] }))
                }
              >
                <Text style={styles.link}>
                  {isOpen ? "Hide payments" : "Show payments"}
                </Text>
              </Pressable>
              {isOpen ? (
                <View style={styles.samples}>
                  {g.samples.map((s) => (
                    <View key={s.id} style={styles.sampleRow}>
                      <Text style={styles.sampleText} numberOfLines={1}>
                        {formatDate(s.date)} · {s.description}
                      </Text>
                      <Text style={styles.sampleAmount}>
                        {formatNumber(s.amount)}
                      </Text>
                    </View>
                  ))}
                  {g.count > g.samples.length ? (
                    <Text style={styles.metaLight}>
                      …and {g.count - g.samples.length} more
                    </Text>
                  ) : null}
                </View>
              ) : null}

              {offer.kind === "use" || offer.kind === "create" ? (
                <View style={{ marginTop: 10 }}>
                  <Pressable
                    style={[styles.primary, busy && styles.disabled]}
                    disabled={busy}
                    onPress={() =>
                      choose(
                        g,
                        offer.kind === "use"
                          ? { categoryId: offer.categoryId }
                          : { newCategory: offer.name },
                      )
                    }
                  >
                    <Text style={styles.primaryText}>
                      {offer.kind === "use"
                        ? `Use “${offer.name}”`
                        : `Create “${offer.name}” and use it`}
                    </Text>
                  </Pressable>
                  {offer.reason ? (
                    <Text style={styles.reason}>Why: {offer.reason}</Text>
                  ) : null}
                  <Pressable disabled={busy} onPress={() => setPicker(g)}>
                    <Text style={styles.link}>Choose another…</Text>
                  </Pressable>
                </View>
              ) : (
                <View style={{ marginTop: 10 }}>
                  <Text style={styles.ask}>Not sure? Pick a category</Text>
                  <View style={styles.chips}>
                    {choices.map((c) => (
                      <Pressable
                        key={c.id}
                        style={[styles.chip, busy && styles.disabled]}
                        disabled={busy}
                        onPress={() => choose(g, { categoryId: c.id })}
                      >
                        <Text style={styles.chipText}>{c.name}</Text>
                      </Pressable>
                    ))}
                    <Pressable
                      style={[styles.chip, busy && styles.disabled]}
                      disabled={busy}
                      onPress={() => setPicker(g)}
                    >
                      <Text style={styles.chipText}>More…</Text>
                    </Pressable>
                  </View>
                </View>
              )}

              {canLearn(g) ? (
                <View style={styles.toggleRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.toggleLabel}>
                      Always file{" "}
                      {g.direction === "out" ? "payments to" : "deposits from"}{" "}
                      {g.label} the same way
                    </Text>
                    {g.both_directions ? (
                      <Text style={styles.toggleNote}>
                        You also have payments going the other way with this
                        payee, so this is off unless you turn it on.
                      </Text>
                    ) : null}
                  </View>
                  <Switch
                    value={applyFor(g)}
                    disabled={busy}
                    onValueChange={(v) =>
                      setApplyAll((a) => ({ ...a, [g.key]: v }))
                    }
                  />
                </View>
              ) : null}

              <Pressable
                disabled={busy}
                onPress={() => (view === "todo" ? skip(g) : restore(g))}
              >
                <Text style={styles.skip}>
                  {view === "todo"
                    ? "Skip — I don't know"
                    : "Move back to review"}
                </Text>
              </Pressable>
            </View>
          );
        })}
      </ScrollView>

      <Modal
        visible={picker !== null}
        animationType="slide"
        onRequestClose={() => setPicker(null)}
      >
        <View style={styles.modal}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Choose a category</Text>
            <Pressable onPress={() => setPicker(null)}>
              <Text style={styles.link}>Close</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: 16 }}>
            {picker && categories.length === 0 ? (
              <Text style={styles.metaLight}>No categories to show.</Text>
            ) : null}
            {picker &&
              buildCategoryTree(categoriesFor(picker, categories)).map(
                ({ parent, children }) =>
                  children.length === 0 ? (
                    <Pressable
                      key={parent.id}
                      style={styles.option}
                      onPress={() => {
                        setPicker(null);
                        choose(picker, { categoryId: parent.id });
                      }}
                    >
                      <Text style={styles.optionText}>{parent.name}</Text>
                    </Pressable>
                  ) : (
                    <View key={parent.id}>
                      <Text style={styles.optionHeader}>{parent.name}</Text>
                      {children.map((c) => (
                        <Pressable
                          key={c.id}
                          style={[styles.option, { paddingLeft: 24 }]}
                          onPress={() => {
                            setPicker(null);
                            choose(picker, { categoryId: c.id });
                          }}
                        >
                          <Text style={styles.optionText}>{c.name}</Text>
                        </Pressable>
                      ))}
                    </View>
                  ),
              )}
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  tabs: { flexDirection: "row", paddingHorizontal: 16, paddingTop: 12, gap: 8 },
  tab: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 18,
    backgroundColor: "#f2f2f2",
  },
  tabActive: { backgroundColor: "#1a73e8" },
  tabText: { fontSize: 13, fontWeight: "600", color: "#555" },
  tabTextActive: { color: "#fff" },
  summary: { fontSize: 13, color: "#666", marginBottom: 12 },
  notice: {
    fontSize: 13,
    color: "#1b6b2f",
    backgroundColor: "#e8f6ec",
    padding: 10,
    borderRadius: 8,
    marginBottom: 12,
  },
  error: { color: "#b00020", marginBottom: 8 },
  link: { color: "#1a73e8", fontSize: 13, fontWeight: "600", marginTop: 8 },
  emptyBox: { alignItems: "center", paddingVertical: 48 },
  emptyTitle: { fontSize: 18, fontWeight: "700" },
  emptyText: { color: "#888", marginTop: 6, textAlign: "center" },
  card: {
    borderWidth: 1,
    borderColor: "#eee",
    borderRadius: 12,
    padding: 14,
    marginBottom: 14,
  },
  cardBusy: { opacity: 0.6 },
  label: { fontSize: 17, fontWeight: "700" },
  meta: { fontSize: 13, color: "#444", marginTop: 2 },
  metaLight: { fontSize: 12, color: "#999", marginTop: 2 },
  samples: { marginTop: 6 },
  sampleRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 3,
  },
  sampleText: { flex: 1, fontSize: 12, color: "#666" },
  sampleAmount: { fontSize: 12, color: "#666", marginLeft: 8 },
  primary: {
    backgroundColor: "#1a73e8",
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
  },
  primaryText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  reason: { fontSize: 12, color: "#777", marginTop: 6 },
  ask: { fontSize: 13, color: "#666", marginBottom: 6 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: {
    borderWidth: 1,
    borderColor: "#cfd8e6",
    borderRadius: 16,
    paddingVertical: 7,
    paddingHorizontal: 12,
  },
  chipText: { fontSize: 13, color: "#1a73e8", fontWeight: "600" },
  disabled: { opacity: 0.5 },
  toggleRow: {
    flexDirection: "row",
    alignItems: "center",
    marginTop: 14,
    gap: 8,
  },
  toggleLabel: { fontSize: 13, color: "#444" },
  toggleNote: { fontSize: 11, color: "#999", marginTop: 2 },
  skip: { color: "#888", fontSize: 13, marginTop: 14, textAlign: "center" },
  modal: { flex: 1, backgroundColor: "#fff" },
  modalHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: "#eee",
  },
  modalTitle: { fontSize: 17, fontWeight: "700" },
  optionHeader: {
    fontSize: 12,
    fontWeight: "700",
    color: "#999",
    textTransform: "uppercase",
    marginTop: 14,
    marginBottom: 4,
  },
  option: {
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: "#f2f2f2",
  },
  optionText: { fontSize: 15 },
});
