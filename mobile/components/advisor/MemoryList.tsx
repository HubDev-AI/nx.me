/**
 * MemoryList — user memories with add and swipe-to-delete.
 *
 * Mirrors ChatView's layout: list fills the tab, composer sits at the
 * bottom of the screen, KeyboardAvoidingView lifts the composer with
 * the keyboard, and the floating tab-bar is cleared via bottomPadding.
 * The Goal / Note type chips sit at the top as a type selector — the
 * actual input is the shared AdvisorComposer at the bottom.
 *
 * Memories are things Ada remembers about the user: goals, notes,
 * accepted suggestions, etc. Swipe left on a row to reveal delete.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  FlatList,
  Text,
  Pressable,
  Alert,
  Animated,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  PanResponder,
} from "react-native";
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

function memoryTypeLabel(type: MemoryType): string {
  switch (type) {
    case "goal":
      return "Goal";
    case "user_note":
      return "Note";
    case "accepted_suggestion":
      return "Accepted";
    case "dismissed_suggestion":
      return "Dismissed";
    case "analysis_insight":
      return "Insight";
    default:
      return "Memory";
  }
}

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
}

function SwipeableMemoryRow({ memory, onDelete }: SwipeableRowProps) {
  const { theme } = useTheme();
  const translateX = useRef(new Animated.Value(0)).current;

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gesture) =>
        Math.abs(gesture.dx) > 10 && Math.abs(gesture.dx) > Math.abs(gesture.dy),
      onPanResponderMove: (_, gesture) => {
        if (gesture.dx < 0) {
          translateX.setValue(Math.max(gesture.dx, -DELETE_BUTTON_WIDTH));
        }
      },
      onPanResponderRelease: (_, gesture) => {
        if (gesture.dx < SWIPE_DELETE_THRESHOLD) {
          Animated.spring(translateX, {
            toValue: -DELETE_BUTTON_WIDTH,
            useNativeDriver: true,
            tension: 40,
            friction: 7,
          }).start();
        } else {
          Animated.spring(translateX, {
            toValue: 0,
            useNativeDriver: true,
            tension: 40,
            friction: 7,
          }).start();
        }
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
          <Text style={[rowStyles.typeLabel, { color: theme.accent }]}>
            {memoryTypeLabel(memory.type)}
          </Text>
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
    position: "relative",
    overflow: "hidden",
    borderRadius: THEME.radius.lg,
  },
  deleteContainer: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "center",
    alignItems: "flex-end",
  },
  deleteButton: {
    width: DELETE_BUTTON_WIDTH,
    height: "100%",
    backgroundColor: THEME.colors.destructive,
    borderTopRightRadius: THEME.radius.lg,
    borderBottomRightRadius: THEME.radius.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  card: {
    flexDirection: "row",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
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
  typeLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 13,
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
// Type selector row — sits at top, picks what kind of memory gets added
// when the user submits the composer at the bottom.
// ---------------------------------------------------------------------------

interface TypeChipsProps {
  selectedType: MemoryType;
  onSelect: (type: MemoryType) => void;
}

const ADDABLE_TYPES: { value: MemoryType; label: string }[] = [
  { value: "goal", label: "Goal" },
  { value: "user_note", label: "Note" },
];

function TypeChips({ selectedType, onSelect }: TypeChipsProps) {
  const { theme } = useTheme();
  return (
    <View style={chipStyles.row}>
      {ADDABLE_TYPES.map((t) => {
        const isActive = selectedType === t.value;
        return (
          <PressableScale
            key={t.value}
            scale={0.94}
            haptic={false}
            onPress={() => onSelect(t.value)}
            style={[
              chipStyles.chip,
              isActive && {
                backgroundColor: theme.accent + "1A",
                borderColor: theme.accent,
                ...THEME.shadow.glow(theme.accent),
              },
            ]}
            accessibilityLabel={`Memory type: ${t.label}`}
            accessibilityRole="button"
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

export function MemoryList() {
  const { keyboardVerticalOffset, inputBottomPadding } =
    useAdvisorComposerLayout();

  // List + form state
  const [memories, setMemories] = useState<UserMemory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);
  const [content, setContent] = useState("");
  const [selectedType, setSelectedType] = useState<MemoryType>("goal");

  // -------------------------------------------------------------------------
  // Load memories
  // -------------------------------------------------------------------------
  const loadMemories = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchMemories();
      setMemories(response.memories);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "We couldn't load your memories.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  // -------------------------------------------------------------------------
  // Add memory
  // -------------------------------------------------------------------------
  const handleAdd = useCallback(async () => {
    const trimmed = content.trim();
    if (!trimmed || isAdding) return;
    setIsAdding(true);
    try {
      const newMemory = await addMemory(selectedType, { text: trimmed });
      setMemories((prev) => [newMemory, ...prev]);
      setContent("");
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Couldn't save that memory.";
      showToast({ kind: "error", message });
    } finally {
      setIsAdding(false);
    }
  }, [content, isAdding, selectedType]);

  // -------------------------------------------------------------------------
  // Delete memory
  // -------------------------------------------------------------------------
  const memoriesRef = useRef(memories);
  memoriesRef.current = memories;

  const handleDelete = useCallback((memoryId: string) => {
    Alert.alert(
      "Delete Memory",
      "Are you sure you want to delete this memory? Ada will no longer remember this.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Delete",
          style: "destructive",
          onPress: async () => {
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
      <SwipeableMemoryRow memory={item} onDelete={handleDelete} />
    ),
    [handleDelete],
  );

  const placeholder =
    selectedType === "goal"
      ? "e.g. Grow out my hair to shoulder length"
      : "e.g. I prefer minimal jewelry";

  const composer = (
    <AdvisorComposer
      value={content}
      onChangeText={setContent}
      onSubmit={handleAdd}
      placeholder={placeholder}
      disabled={isAdding}
      submitIcon="add"
      maxLength={ADVISOR_CONFIG.MEMORY_MAX_LENGTH}
      accessibilityLabel="Memory content"
      submitAccessibilityLabel="Add memory"
      bottomPadding={inputBottomPadding}
      separator
    />
  );

  if (isLoading) {
    return (
      <KeyboardAvoidingView
        style={styles.container}
        behavior={
          Platform.OS === "ios" ? "padding" : Platform.OS === "web" ? undefined : "height"
        }
        keyboardVerticalOffset={keyboardVerticalOffset}
      >
        <TypeChips selectedType={selectedType} onSelect={setSelectedType} />
        <MemorySkeleton />
        {composer}
      </KeyboardAvoidingView>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={
        Platform.OS === "ios" ? "padding" : Platform.OS === "web" ? undefined : "height"
      }
      keyboardVerticalOffset={keyboardVerticalOffset}
    >
      <TypeChips selectedType={selectedType} onSelect={setSelectedType} />

      <FlatList
        data={memories}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        ItemSeparatorComponent={MemorySeparator}
      />

      {/* Error overlay — centered with Try Again button. */}
      {error && memories.length === 0 && (
        <AdvisorEmptyOverlay
          icon="alert-circle-outline"
          title="Could not load memories"
          description={error}
          action={{
            label: "Try Again",
            onPress: loadMemories,
            accessibilityLabel: "Retry loading memories",
          }}
        />
      )}

      {/* Empty overlay — shown when no memories exist. */}
      {!error && memories.length === 0 && (
        <AdvisorEmptyOverlay
          icon="bookmark-outline"
          title="No memories yet"
          description="Add goals or notes so Ada can personalise her advice"
        />
      )}

      {composer}
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "transparent",
  },
  listContent: {
    flexGrow: 1,
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
  },
  separator: {
    height: THEME.spacing.md - 2,
  },
});
