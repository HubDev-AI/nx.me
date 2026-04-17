/**
 * MemoryList — user memories with add and swipe-to-delete.
 *
 * Mirrors ChatView's layout: list fills the tab, composer sits at the
 * bottom of the screen, KeyboardAvoidingView lifts the composer with
 * the keyboard, and the floating tab-bar is cleared via bottomPadding.
 * The Goals / Notes subtabs sit at the top as a list filter — each tab
 * has its own draft, error, and isAdding state so submitting on one
 * never locks the other. The actual input is the shared AdvisorComposer
 * at the bottom, bound to the active tab's draft.
 *
 * Memories are things Ada remembers about the user: goals, notes,
 * accepted suggestions, etc. The Goals / Notes tabs only show
 * user-authored rows; system-authored insights / accepted /
 * dismissed suggestions are hidden via a server-side type filter.
 * Swipe left on a row to reveal delete.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  FlatList,
  Text,
  Pressable,
  Alert,
  Animated,
  ActivityIndicator,
  Platform,
  StyleSheet,
  PanResponder,
} from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { showToast } from "../../lib/toast";
import { ADVISOR_CONFIG, MIN_TOUCH_TARGET } from "../../constants/config";
import { useAdvisorComposerLayout } from "../../hooks/useAdvisorComposerLayout";
import { fetchMemories, addMemory, deleteMemory } from "../../lib/advisor";
import type { UserMemory, MemoryType } from "../../lib/advisor";
import { AdvisorComposer } from "./AdvisorComposer";
import { AdvisorEmptyOverlay } from "./AdvisorEmptyOverlay";
import { PressableScale } from "../ui/PressableScale";
import { Caption } from "../ui/Text";

const SWIPE_DELETE_THRESHOLD = -80;
const DELETE_BUTTON_WIDTH = 80;

/** Extract a display string from a memory content object. */
function memoryContentText(content: Record<string, unknown>): string {
  if (typeof content.text === "string") return content.text;
  if (typeof content.summary === "string") return content.summary;
  return JSON.stringify(content);
}

// ---------------------------------------------------------------------------
// Memory type display helpers
// ---------------------------------------------------------------------------

/**
 * Icon glyph for each memory type. Only `goal` and `user_note` ever
 * surface in the UI today (system-authored types are server-filtered),
 * but the helper keeps every branch covered so a future "What Ada knows"
 * surface can reuse it without touching the row component.
 */
function memoryTypeIcon(
  type: MemoryType,
): React.ComponentProps<typeof Ionicons>["name"] {
  switch (type) {
    case "goal":
      return "flag-outline";
    case "user_note":
      return "document-text-outline";
    case "accepted_suggestion":
      return "checkmark-circle-outline";
    case "dismissed_suggestion":
      return "close-circle-outline";
    case "analysis_insight":
      return "analytics-outline";
    default:
      return "bookmark-outline";
  }
}

// ---------------------------------------------------------------------------
// SwipeableMemoryRow
// ---------------------------------------------------------------------------

interface SwipeableRowProps {
  memory: UserMemory;
  onDelete: (id: string) => void;
  /**
   * Whether THIS row is the currently-open one (trash button revealed).
   * MemoryList tracks the single open id; flipping this to false
   * triggers the row to spring back to the resting position so taps on
   * other rows / chrome / a sibling row's swipe close the open row
   * automatically.
   */
  isOpen: boolean;
  /** Notify parent that this row opened (id) or closed (null). */
  onOpenChange: (id: string | null) => void;
}

/**
 * Single memory row with swipe-to-delete. The left icon container is
 * the only visual cue for the row's type — the textual label was
 * dropped because each tab's content is uniform, so the label was
 * redundant chrome.
 *
 * Open state is lifted to ``MemoryList`` so only one row can be open
 * at a time and taps anywhere else (sibling row, subtabs, list
 * background) close it.
 */
function SwipeableMemoryRow({
  memory,
  onDelete,
  isOpen,
  onOpenChange,
}: SwipeableRowProps) {
  const { theme } = useTheme();
  const translateX = useRef(new Animated.Value(0)).current;

  // When the parent flips isOpen to false (another row opened, or a
  // tap-outside fired), spring the trash button back behind the card.
  // Skipping the initial mount keeps the animation from firing on the
  // very first render of every row.
  const didMountRef = useRef(false);
  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true;
      return;
    }
    if (!isOpen) {
      Animated.spring(translateX, {
        toValue: 0,
        useNativeDriver: true,
        tension: 40,
        friction: 7,
      }).start();
    }
  }, [isOpen, translateX]);

  // PanResponder is recreated when ``onOpenChange`` identity changes
  // (it never does for setState's setter, but the closure is captured
  // here so the latest value is always used). The release handler
  // notifies the parent so the open id state updates atomically.
  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) => {
        // Defensive: a NaN dx slipping past the comparison would
        // cascade into translateX.setValue(NaN) below and surface
        // as a CoreGraphics "invalid numeric value" warning on iOS.
        if (!Number.isFinite(gesture.dx) || !Number.isFinite(gesture.dy)) {
          return false;
        }
        return (
          Math.abs(gesture.dx) > 10 && Math.abs(gesture.dx) > Math.abs(gesture.dy)
        );
      },
      onPanResponderMove: (_, gesture) => {
        if (!Number.isFinite(gesture.dx) || gesture.dx >= 0) return;
        translateX.setValue(Math.max(gesture.dx, -DELETE_BUTTON_WIDTH));
      },
      onPanResponderRelease: (_, gesture) => {
        const dx = Number.isFinite(gesture.dx) ? gesture.dx : 0;
        const willOpen = dx < SWIPE_DELETE_THRESHOLD;
        Animated.spring(translateX, {
          toValue: willOpen ? -DELETE_BUTTON_WIDTH : 0,
          useNativeDriver: true,
          tension: 40,
          friction: 7,
        }).start();
        onOpenChange(willOpen ? memory.id : null);
      },
    }),
  ).current;

  const handleDelete = useCallback(() => {
    Animated.timing(translateX, {
      toValue: -400,
      duration: 200,
      useNativeDriver: true,
    }).start(() => onDelete(memory.id));
  }, [memory.id, onDelete, translateX]);

  const dateStr = new Date(memory.created_at).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  // The wrapper stays a plain View so the row's PanResponder owns the
  // gesture cleanly — wrapping it in a Pressable claims the responder
  // on touch start before PanResponder.onMoveShouldSet has a chance,
  // which silently breaks every swipe. Tap-outside-close is handled
  // at MemoryList level via:
  //   - ListFooterComponent Pressable when a row is open
  //   - onScrollBeginDrag
  //   - handleTabChange (always resets, even on the active chip)
  //   - other-row swipe (parent state swap closes this one)
  return (
    <View style={rowStyles.wrapper}>
      <View style={rowStyles.deleteContainer}>
        <Pressable
          onPress={handleDelete}
          style={rowStyles.deleteButton}
          accessibilityLabel={`Delete memory: ${memoryContentText(memory.content)}`}
          accessibilityRole="button"
        >
          <Ionicons name="trash-outline" size={22} color={THEME.colors.white} />
        </Pressable>
      </View>

      <Animated.View
        style={[rowStyles.card, { transform: [{ translateX }] }]}
        {...panResponder.panHandlers}
      >
        <View style={[rowStyles.iconContainer, { backgroundColor: theme.accentMuted }]}>
          <Ionicons
            name={memoryTypeIcon(memory.type)}
            size={20}
            color={theme.accent}
          />
        </View>
        <View style={rowStyles.content}>
          <Text style={rowStyles.body} numberOfLines={3}>
            {memoryContentText(memory.content)}
          </Text>
          <Text style={rowStyles.date}>{dateStr}</Text>
        </View>
      </Animated.View>
    </View>
  );
}

const rowStyles = StyleSheet.create({
  wrapper: {
    // overflow:hidden + borderRadius:lg clips the card+button composite
    // to a single rounded shape. The card's right corners and the
    // trash button's left corners are intentionally SQUARE (see styles
    // below) so the seam between them at the swiped position is a
    // clean vertical line — the card and the button read as one
    // continuous control split in two, not as two separate pills.
    position: "relative",
    overflow: "hidden",
    borderRadius: THEME.radius.lg,
  },
  deleteContainer: {
    // Anchor to the right edge with a fixed width and stretch the
    // child via flex instead of `height: "100%"`. Percentage heights
    // resolve to NaN on iOS during the first layout pass when the
    // parent's measured height is briefly undefined, surfacing as
    // CoreGraphics "invalid numeric value" warnings.
    position: "absolute",
    top: 0,
    bottom: 0,
    right: 0,
    width: DELETE_BUTTON_WIDTH,
    alignItems: "stretch",
    justifyContent: "center",
  },
  deleteButton: {
    // Square left corners so the button merges flush with the card's
    // square right corners. The wrapper's overflow:hidden clips the
    // outer right edge to match the wrapper's borderRadius.
    flex: 1,
    backgroundColor: THEME.colors.destructive,
    alignItems: "center",
    justifyContent: "center",
  },
  card: {
    // Square right corners for the same merge. The outer left corners
    // get rounded by the wrapper's clip.
    flexDirection: "row",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
    ...THEME.shadow.glass,
  },
  iconContainer: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.xs / 2,
  },
  content: {
    flex: 1,
    gap: THEME.spacing.xs,
  },
  date: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
    marginTop: THEME.spacing.xs,
  },
  body: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    fontSize: 14,
    lineHeight: 20,
    color: THEME.colors.textPrimary,
  },
});

// ---------------------------------------------------------------------------
// SubTabs — Goals / Notes switcher. Filters the list and binds the
// composer to the active tab's draft. Styled as a chip pair to match
// the rest of the advisor surface; semantically a tablist for VoiceOver.
// ---------------------------------------------------------------------------

/** Tab values double as the server-side type filter (`?type=goal|user_note`). */
type Tab = "goal" | "user_note";

const SUB_TABS: { value: Tab; label: string }[] = [
  { value: "goal", label: "Goals" },
  { value: "user_note", label: "Notes" },
];

interface SubTabsProps {
  activeTab: Tab;
  onChange: (tab: Tab) => void;
}

function SubTabs({ activeTab, onChange }: SubTabsProps) {
  const { theme } = useTheme();
  return (
    <View style={chipStyles.row} accessibilityRole="tablist">
      {SUB_TABS.map((t) => {
        const isActive = activeTab === t.value;
        return (
          <PressableScale
            key={t.value}
            scale={0.94}
            haptic={false}
            onPress={() => onChange(t.value)}
            style={[
              chipStyles.chip,
              isActive && {
                backgroundColor: theme.accent + "1A",
                borderColor: theme.accent,
                ...THEME.shadow.glow(theme.accent),
              },
            ]}
            accessibilityLabel={t.label}
            accessibilityRole="tab"
            accessibilityState={{ selected: isActive }}
          >
            <Ionicons
              name={memoryTypeIcon(t.value)}
              size={18}
              color={isActive ? theme.accent : THEME.colors.textSecondary}
            />
            <Caption
              weight={isActive ? "semibold" : "medium"}
              color={isActive ? theme.accent : "secondary"}
            >
              {t.label}
            </Caption>
          </PressableScale>
        );
      })}
    </View>
  );
}

const chipStyles = StyleSheet.create({
  row: {
    flexDirection: "row",
    gap: THEME.spacing.sm,
    paddingHorizontal: THEME.spacing.md,
    paddingTop: THEME.spacing.md,
    paddingBottom: THEME.spacing.sm,
  },
  chip: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
    paddingVertical: THEME.spacing.sm + 2,
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    minHeight: MIN_TOUCH_TARGET,
    ...THEME.shadow.glass,
  },
});

// ---------------------------------------------------------------------------
// MemoryList (main export)
// ---------------------------------------------------------------------------

/** Skeleton for initial loading state */
function MemorySkeleton() {
  return (
    <View style={memSkeletonStyles.container}>
      {[1, 2, 3].map((i) => (
        <View key={i} style={memSkeletonStyles.card}>
          <View style={memSkeletonStyles.icon} />
          <View style={memSkeletonStyles.lines}>
            <View style={[memSkeletonStyles.line, { width: "40%" }]} />
            <View style={[memSkeletonStyles.line, { width: "80%" }]} />
          </View>
        </View>
      ))}
    </View>
  );
}

const memSkeletonStyles = StyleSheet.create({
  container: {
    flex: 1,
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  card: {
    flexDirection: "row",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  icon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: THEME.colors.glass,
  },
  lines: {
    flex: 1,
    gap: THEME.spacing.sm,
  },
  line: {
    height: 12,
    borderRadius: THEME.radius.sm,
    backgroundColor: THEME.colors.surface,
  },
});

const MemorySeparator = () => <View style={styles.separator} />;

// ---------------------------------------------------------------------------
// Per-tab copy — kept in one place so SubTabs, composer, and empty
// overlay all read from the same source of truth.
// ---------------------------------------------------------------------------

interface TabCopy {
  placeholder: string;
  composerA11yLabel: string;
  emptyTitle: string;
  emptyDescription: string;
}

const TAB_COPY: Record<Tab, TabCopy> = {
  goal: {
    // Kept pithy — the old copy wrapped to two lines inside the
    // composer input on the standard iPhone width, which reads as
    // a broken multi-line field.
    placeholder: "e.g. Grow my hair out",
    composerA11yLabel: "Goal content",
    emptyTitle: "No goals yet",
    emptyDescription: "Tell Ada what you're working toward.",
  },
  user_note: {
    placeholder: "e.g. I prefer minimal jewelry",
    composerA11yLabel: "Note content",
    emptyTitle: "No notes yet",
    emptyDescription: "Jot anything Ada should know about you.",
  },
};

/** First tab shown on mount. Persists within session via `activeTab` state. */
const DEFAULT_TAB: Tab = "goal";

interface TabState {
  draft: string;
  error: string | null;
  isAdding: boolean;
}

const INITIAL_TAB_STATE: TabState = { draft: "", error: null, isAdding: false };

export function MemoryList() {
  const {
    keyboardVerticalOffset,
    inputBottomPadding,
    screenAnchorRef,
    onScreenAnchorLayout,
  } = useAdvisorComposerLayout();

  // -------------------------------------------------------------------------
  // State — see plan §High-Level Technical Design
  // -------------------------------------------------------------------------
  const [activeTab, setActiveTab] = useState<Tab>(DEFAULT_TAB);
  const [memories, setMemories] = useState<UserMemory[]>([]);
  const [byTab, setByTab] = useState<Record<Tab, TabState>>({
    goal: INITIAL_TAB_STATE,
    user_note: INITIAL_TAB_STATE,
  });
  const [initialLoading, setInitialLoading] = useState(true);
  const [refetching, setRefetching] = useState(false);
  // Single open swipe row at a time. Lifted from SwipeableMemoryRow so
  // tapping any other row, the subtabs chips, the empty list area, or
  // swiping a different row closes the previously-open one.
  const [openMemoryId, setOpenMemoryId] = useState<string | null>(null);

  // Monotonic request counter + activeTab ref. A fetch that resolves
  // after a later fetch, or after the tab was switched, is discarded
  // — prevents a stale Goals response from overwriting Notes' data.
  // `activeTabRef` also gates `handleAdd`'s prepend so a row submitted
  // on Goals doesn't land in the Notes list if the user switches tabs
  // before the POST resolves.
  const requestIdRef = useRef(0);
  const activeTabRef = useRef<Tab>(DEFAULT_TAB);
  activeTabRef.current = activeTab;

  // Abort controller for the current in-flight list fetch. A rapid
  // tab tap cancels the prior request instead of firing a second
  // network round-trip, and the effect cleanup aborts the initial
  // load (relevant under React StrictMode's double-invoke in dev).
  const abortRef = useRef<AbortController | null>(null);

  const updateTab = useCallback(
    (tab: Tab, patch: Partial<TabState>) =>
      setByTab((prev) => ({ ...prev, [tab]: { ...prev[tab], ...patch } })),
    [],
  );

  // -------------------------------------------------------------------------
  // Unified load path — used by initial mount, tab switch, and retry.
  // Stale responses (user switched tabs mid-fetch) are dropped via the
  // request-id guard; only the most recent call for the currently-active
  // tab is allowed to mutate `memories`.
  // -------------------------------------------------------------------------
  const loadTab = useCallback(
    async (tab: Tab, { showRefetchIndicator = true } = {}) => {
      // Cancel any prior in-flight fetch so fast tab tapping does
      // not fire N parallel round-trips.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const reqId = ++requestIdRef.current;
      if (showRefetchIndicator) setRefetching(true);
      updateTab(tab, { error: null });
      try {
        const response = await fetchMemories({
          type: tab,
          signal: controller.signal,
        });
        if (reqId !== requestIdRef.current || activeTabRef.current !== tab) return;
        setMemories(response.memories);
      } catch (err) {
        // Aborted fetches are expected when the user switches tabs
        // mid-request or the effect cleans up — swallow silently.
        if (err instanceof Error && err.name === "AbortError") return;
        if (reqId !== requestIdRef.current || activeTabRef.current !== tab) return;
        const message =
          err instanceof Error ? err.message : "We couldn't load your memories.";
        updateTab(tab, { error: message });
        setMemories([]);
      } finally {
        if (reqId === requestIdRef.current) setRefetching(false);
      }
    },
    [updateTab],
  );

  // -------------------------------------------------------------------------
  // Initial load — first mount only. Cleanup aborts the in-flight
  // fetch so React StrictMode's dev-only double-invoke doesn't fire
  // two identical network calls.
  // -------------------------------------------------------------------------
  useEffect(() => {
    (async () => {
      await loadTab(DEFAULT_TAB, { showRefetchIndicator: false });
      setInitialLoading(false);
    })();
    return () => abortRef.current?.abort();
  }, [loadTab]);

  // -------------------------------------------------------------------------
  // Tab switching — refetch the new tab's rows via loadTab. We keep the
  // previous list visible and show a subtle indicator (see plan) instead
  // of the full-screen skeleton on every tap. Drafts are intentionally
  // not cleared on switch — that's the whole point of per-tab state.
  // -------------------------------------------------------------------------
  const handleTabChange = useCallback(
    (tab: Tab) => {
      // Always close any open swipe row on a chip tap — even when the
      // tap is on the already-active chip — so the chip row works as
      // an extra dismiss surface for the open trash button.
      setOpenMemoryId(null);
      if (tab === activeTab) return;
      setActiveTab(tab);
      activeTabRef.current = tab;
      void loadTab(tab);
    },
    [activeTab, loadTab],
  );

  // -------------------------------------------------------------------------
  // Add memory — scoped to the active tab. Clears ONLY the active
  // tab's draft on success so the other tab's in-progress text stays
  // put. Errors surface via toast and leave the draft intact for retry.
  // -------------------------------------------------------------------------
  const activeState = byTab[activeTab];

  const handleAdd = useCallback(async () => {
    const trimmed = activeState.draft.trim();
    if (!trimmed || activeState.isAdding) return;
    const tab = activeTab;
    updateTab(tab, { isAdding: true });
    try {
      const newMemory = await addMemory(tab, { text: trimmed });
      // The draft belongs to `tab`; clearing it is always safe. But
      // `memories` reflects whichever tab is currently visible — only
      // prepend if the user is still on the tab they submitted from.
      // Otherwise the row would land in the wrong list visually until
      // the next refetch of `tab`.
      updateTab(tab, { draft: "", error: null });
      if (activeTabRef.current === tab) {
        setMemories((prev) => [newMemory, ...prev]);
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Couldn't save that memory.";
      updateTab(tab, { error: message });
      showToast({ kind: "error", message });
    } finally {
      updateTab(tab, { isAdding: false });
    }
  }, [activeState.draft, activeState.isAdding, activeTab, updateTab]);

  const handleDraftChange = useCallback(
    (text: string) => updateTab(activeTab, { draft: text }),
    [activeTab, updateTab],
  );

  // -------------------------------------------------------------------------
  // Delete memory — unchanged behavior: Alert.alert confirm, optimistic
  // removal, restore-on-failure.
  // -------------------------------------------------------------------------
  const memoriesRef = useRef(memories);
  memoriesRef.current = memories;

  const handleDelete = useCallback((memoryId: string) => {
    Alert.alert(
      "Delete Memory",
      "Are you sure you want to delete this memory? Ada will no longer remember this.",
      [
        { text: "Cancel", style: "cancel", onPress: () => setOpenMemoryId(null) },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
            setOpenMemoryId(null);
            const deletedItem = memoriesRef.current.find((m) => m.id === memoryId);
            setMemories((prev) => prev.filter((m) => m.id !== memoryId));
            try {
              await deleteMemory(memoryId);
            } catch {
              if (deletedItem) {
                setMemories((prev) =>
                  [...prev, deletedItem].sort(
                    (a, b) =>
                      new Date(b.created_at).getTime() -
                      new Date(a.created_at).getTime(),
                  ),
                );
              }
              showToast({ kind: "error", message: "Couldn't delete that memory. Try again." });
            }
          },
        },
      ],
    );
  }, []);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------
  const keyExtractor = useCallback((item: UserMemory) => item.id, []);

  const renderItem = useCallback(
    ({ item }: { item: UserMemory }) => (
      <SwipeableMemoryRow
        memory={item}
        onDelete={handleDelete}
        isOpen={openMemoryId === item.id}
        onOpenChange={setOpenMemoryId}
      />
    ),
    [handleDelete, openMemoryId],
  );

  const copy = TAB_COPY[activeTab];

  // `key={activeTab}` forces AdvisorComposer to remount on tab switch
  // so its focus state resets and the keyboard dismisses cleanly —
  // otherwise the previous tab's focused input stays live under the
  // new tab's draft value.
  const composer = (
    <AdvisorComposer
      key={activeTab}
      value={activeState.draft}
      onChangeText={handleDraftChange}
      onSubmit={handleAdd}
      placeholder={copy.placeholder}
      disabled={activeState.isAdding}
      submitIcon="add"
      maxLength={ADVISOR_CONFIG.MEMORY_MAX_LENGTH}
      accessibilityLabel={copy.composerA11yLabel}
      submitAccessibilityLabel="Add memory"
      bottomPadding={inputBottomPadding}
    />
  );

  const subTabs = <SubTabs activeTab={activeTab} onChange={handleTabChange} />;

  if (initialLoading) {
    return (
      <View
        ref={screenAnchorRef}
        onLayout={onScreenAnchorLayout}
        style={styles.container}
        collapsable={false}
      >
        <KeyboardAvoidingView
          style={styles.container}
          behavior="padding"
          keyboardVerticalOffset={keyboardVerticalOffset}
          enabled={Platform.OS !== "web"}
        >
          {subTabs}
          <MemorySkeleton />
          {composer}
        </KeyboardAvoidingView>
      </View>
    );
  }

  return (
    <View
      ref={screenAnchorRef}
      onLayout={onScreenAnchorLayout}
      style={styles.container}
      collapsable={false}
    >
    <KeyboardAvoidingView
      style={styles.container}
      behavior="padding"
      keyboardVerticalOffset={keyboardVerticalOffset}
      enabled={Platform.OS !== "web"}
    >
      {/* listArea spans FROM subtabs-top TO composer-top — the same
          vertical region the Chat tab's listArea covers. The overlay
          children use StyleSheet.absoluteFill, so they're centered in
          THIS box. If the overlay sat one level deeper (sibling of the
          FlatList only, BELOW the subtabs row), the centering box
          would be ~64pt shorter at the top and the hero would float
          ~32pt above where Chat's hero sits — visually crammed against
          the subtabs chips. Wrapping subtabs + the row scroll area in
          one listArea pins the hero to the same screen-Y as Chat.

          accessibilityLiveRegion is Android-only; iOS VoiceOver
          ignores it. A future polish pass could call
          AccessibilityInfo.announceForAccessibility on tab change. */}
      <View style={styles.listArea} accessibilityLiveRegion="polite">
        {subTabs}

        <View style={styles.rowsArea}>
          <FlatList
            data={memories}
            keyExtractor={keyExtractor}
            renderItem={renderItem}
            showsVerticalScrollIndicator={false}
            contentContainerStyle={styles.listContent}
            ItemSeparatorComponent={MemorySeparator}
            ListFooterComponent={
              openMemoryId !== null ? (
                <Pressable
                  style={styles.dismissFooter}
                  onPress={() => setOpenMemoryId(null)}
                  accessibilityElementsHidden
                  importantForAccessibility="no"
                />
              ) : null
            }
            onScrollBeginDrag={() => {
              if (openMemoryId !== null) setOpenMemoryId(null);
            }}
          />
        </View>

        {/* Tab-switch spinner — overlay; list stays rendered underneath. */}
        {refetching && (
          <View style={styles.refetchIndicator} pointerEvents="none">
            <ActivityIndicator size="small" color={THEME.colors.textSecondary} />
          </View>
        )}

        {/* Error overlay — scoped to the active tab; subtabs above stay
            interactive so the user can switch away from a failed tab
            (overlays use pointerEvents="box-none"). Retry reuses
            loadTab so the stale-response guard applies. */}
        {activeState.error && memories.length === 0 && (
          <AdvisorEmptyOverlay
            icon="alert-circle-outline"
            title="Could not load memories"
            description={activeState.error}
            action={{
              label: "Try Again",
              onPress: () => void loadTab(activeTab),
              accessibilityLabel: "Retry loading memories",
            }}
          />
        )}

        {/* Empty overlay — per-tab copy. */}
        {!activeState.error && !refetching && memories.length === 0 && (
          <AdvisorEmptyOverlay
            icon={memoryTypeIcon(activeTab)}
            title={copy.emptyTitle}
            description={copy.emptyDescription}
          />
        )}
      </View>

      {composer}
    </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "transparent",
  },
  listArea: {
    flex: 1,
  },
  /**
   * Hosts the FlatList only — sits BELOW subtabs inside listArea.
   * flex:1 lets the rows fill the space below subtabs while the empty/
   * error overlays absoluteFill listArea (the wider region) so they
   * land at the same screen-Y as the Chat tab's empty hero.
   */
  rowsArea: {
    flex: 1,
  },
  listContent: {
    flexGrow: 1,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md,
    paddingBottom: THEME.spacing.lg,
  },
  /**
   * Tappable footer rendered only when a swipe row is open. flex:1
   * stretches it to fill the empty space below the last row, so a tap
   * anywhere in the list-but-not-on-a-row closes the open row. Min
   * height keeps it tappable when the rows already fill the viewport.
   */
  dismissFooter: {
    flex: 1,
    minHeight: 80,
  },
  separator: {
    height: THEME.spacing.md - 2,
  },
  refetchIndicator: {
    position: "absolute",
    top: THEME.spacing.md,
    left: 0,
    right: 0,
    alignItems: "center",
  },
});
