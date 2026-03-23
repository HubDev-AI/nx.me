/**
 * MemoryList — user memories with add and swipe-to-delete.
 *
 * Memories are things Ada remembers about the user: goals, notes, accepted suggestions, etc.
 * Users can add goals/notes and delete any memory. Swipe left to reveal delete action.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  FlatList,
  Text,
  TextInput,
  Pressable,
  Alert,
  Animated,
  ActivityIndicator,
  StyleSheet,
  PanResponder,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { fetchMemories, addMemory, deleteMemory } from "../../lib/advisor";
import type { UserMemory, MemoryType } from "../../lib/advisor";

const SWIPE_DELETE_THRESHOLD = -80;
const DELETE_BUTTON_WIDTH = 80;

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
          // Snap to reveal delete
          Animated.spring(translateX, {
            toValue: -DELETE_BUTTON_WIDTH,
            useNativeDriver: true,
            tension: 40,
            friction: 7,
          }).start();
        } else {
          // Snap back
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
    // Animate out then delete
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
      {/* Delete button behind */}
      <View style={rowStyles.deleteContainer}>
        <Pressable
          onPress={handleDelete}
          style={rowStyles.deleteButton}
          accessibilityLabel={`Delete memory: ${memory.content}`}
          accessibilityRole="button"
        >
          <Ionicons name="trash-outline" size={22} color={THEME.colors.white} />
        </Pressable>
      </View>

      {/* Card on top, swipeable */}
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
          <View style={rowStyles.header}>
            <Text style={[rowStyles.typeLabel, { color: theme.accent }]}>
              {memoryTypeLabel(memory.type)}
            </Text>
            <Text style={rowStyles.date}>{dateStr}</Text>
          </View>
          <Text style={rowStyles.body} numberOfLines={3}>
            {memory.content}
          </Text>
        </View>
      </Animated.View>
    </View>
  );
}

const rowStyles = StyleSheet.create({
  wrapper: {
    position: "relative",
    overflow: "hidden",
    borderRadius: THEME.radius.lg - 2,
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
    borderTopRightRadius: THEME.radius.lg - 2,
    borderBottomRightRadius: THEME.radius.lg - 2,
    alignItems: "center",
    justifyContent: "center",
  },
  card: {
    flexDirection: "row",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg - 2,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg - 2,
    gap: THEME.spacing.md,
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
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  typeLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: THEME.typography.caption.letterSpacing,
  },
  date: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
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
// Add Memory Form
// ---------------------------------------------------------------------------

interface AddMemoryFormProps {
  onAdd: (type: MemoryType, content: string) => void;
  isAdding: boolean;
}

function AddMemoryForm({ onAdd, isAdding }: AddMemoryFormProps) {
  const { theme } = useTheme();
  const [content, setContent] = useState("");
  const [selectedType, setSelectedType] = useState<MemoryType>("goal");

  const types: { value: MemoryType; label: string }[] = [
    { value: "goal", label: "Goal" },
    { value: "user_note", label: "Note" },
  ];

  const handleAdd = useCallback(() => {
    const trimmed = content.trim();
    if (!trimmed) return;
    onAdd(selectedType, trimmed);
    setContent("");
  }, [content, selectedType, onAdd]);

  return (
    <View style={formStyles.container}>
      {/* Type selector */}
      <View style={formStyles.typeRow}>
        {types.map((t) => (
          <Pressable
            key={t.value}
            onPress={() => setSelectedType(t.value)}
            style={[
              formStyles.typeChip,
              selectedType === t.value && [formStyles.typeChipActive, { backgroundColor: theme.accent }],
            ]}
            accessibilityLabel={`Memory type: ${t.label}`}
            accessibilityRole="button"
            accessibilityState={{ selected: selectedType === t.value }}
          >
            <Text
              style={[
                formStyles.typeChipText,
                selectedType === t.value && formStyles.typeChipTextActive,
              ]}
            >
              {t.label}
            </Text>
          </Pressable>
        ))}
      </View>

      {/* Input row */}
      <View style={formStyles.inputRow}>
        <TextInput
          style={formStyles.input}
          value={content}
          onChangeText={setContent}
          placeholder={
            selectedType === "goal"
              ? "e.g. Grow out my hair to shoulder length"
              : "e.g. I prefer minimal jewelry"
          }
          placeholderTextColor={THEME.colors.textDisabled}
          multiline
          maxLength={500}
          accessibilityLabel="Memory content"
        />
        <Pressable
          onPress={handleAdd}
          disabled={!content.trim() || isAdding}
          style={({ pressed }) => [
            formStyles.addButton,
            content.trim() && !isAdding && formStyles.addButtonActive,
            pressed && content.trim() && !isAdding && formStyles.addButtonPressed,
          ]}
          accessibilityLabel="Add memory"
          accessibilityRole="button"
        >
          {isAdding ? (
            <ActivityIndicator size="small" color={THEME.colors.bg} />
          ) : (
            <Ionicons
              name="add"
              size={24}
              color={content.trim() ? THEME.colors.bg : THEME.colors.textDisabled}
            />
          )}
        </Pressable>
      </View>
    </View>
  );
}

const formStyles = StyleSheet.create({
  container: {
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.md,
    gap: THEME.spacing.md - 2,
  },
  typeRow: {
    flexDirection: "row",
    gap: THEME.spacing.sm,
  },
  typeChip: {
    paddingHorizontal: THEME.spacing.lg - 2,
    paddingVertical: THEME.spacing.sm,
    borderRadius: THEME.radius.lg,
    backgroundColor: THEME.colors.surfaceElevated,
    minHeight: 44,
    justifyContent: "center",
  },
  typeChipActive: {
    // backgroundColor applied dynamically via inline style
  },
  typeChipText: {
    fontFamily: FONTS.bodyMedium,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },
  typeChipTextActive: {
    color: THEME.colors.bg,
    fontFamily: FONTS.bodySemiBold,
  },
  inputRow: {
    flexDirection: "row",
    gap: THEME.spacing.sm,
    alignItems: "flex-end",
  },
  input: {
    flex: 1,
    fontFamily: FONTS.body,
    backgroundColor: THEME.colors.surfaceElevated,
    borderRadius: THEME.radius.lg - 2,
    paddingHorizontal: THEME.spacing.lg - 2,
    paddingTop: THEME.spacing.md - 2,
    paddingBottom: THEME.spacing.md - 2,
    fontSize: 14,
    color: THEME.colors.textPrimary,
    maxHeight: 80,
    minHeight: MIN_TOUCH_TARGET,
  },
  addButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: MIN_TOUCH_TARGET / 2,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: THEME.colors.border,
  },
  addButtonActive: {
    backgroundColor: THEME.colors.textPrimary,
  },
  addButtonPressed: {
    opacity: 0.85,
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
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  card: {
    flexDirection: "row",
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.lg - 2,
    padding: THEME.spacing.lg - 2,
    gap: THEME.spacing.md,
  },
  icon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: THEME.colors.surfaceElevated,
  },
  lines: {
    flex: 1,
    gap: THEME.spacing.sm,
  },
  line: {
    height: 12,
    borderRadius: THEME.radius.sm - 2,
    backgroundColor: THEME.colors.surfaceElevated,
  },
});

const MemorySeparator = () => <View style={styles.separator} />;

export function MemoryList() {
  const [memories, setMemories] = useState<UserMemory[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isAdding, setIsAdding] = useState(false);

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
        err instanceof Error ? err.message : "Failed to load memories";
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
  const handleAdd = useCallback(
    async (type: MemoryType, content: string) => {
      setIsAdding(true);
      try {
        const newMemory = await addMemory(type, content);
        setMemories((prev) => [newMemory, ...prev]);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to add memory";
        Alert.alert("Error", message);
      } finally {
        setIsAdding(false);
      }
    },
    [],
  );

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
            // Read from ref to avoid stale closure over memories
            const deletedItem = memoriesRef.current.find((m) => m.id === memoryId);
            // Optimistic removal
            setMemories((prev) => prev.filter((m) => m.id !== memoryId));
            try {
              await deleteMemory(memoryId);
            } catch {
              // Re-insert on failure, preserving sort order
              if (deletedItem) {
                setMemories((prev) =>
                  [...prev, deletedItem].sort(
                    (a, b) =>
                      new Date(b.created_at).getTime() -
                      new Date(a.created_at).getTime(),
                  ),
                );
              }
              Alert.alert("Error", "Failed to delete memory. Please try again.");
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

  // -------------------------------------------------------------------------
  // States
  // -------------------------------------------------------------------------
  if (isLoading) {
    return (
      <View style={styles.container}>
        <AddMemoryForm onAdd={handleAdd} isAdding={isAdding} />
        <MemorySkeleton />
      </View>
    );
  }

  if (error && memories.length === 0) {
    return (
      <View style={styles.container}>
        <AddMemoryForm onAdd={handleAdd} isAdding={isAdding} />
        <View style={styles.errorContainer}>
          <Ionicons name="alert-circle-outline" size={48} color={THEME.colors.textSecondary} />
          <Text style={styles.errorTitle}>Could not load memories</Text>
          <Text style={styles.errorSubtitle}>{error}</Text>
          <Pressable
            onPress={loadMemories}
            style={styles.retryButton}
            accessibilityLabel="Retry loading memories"
            accessibilityRole="button"
          >
            <Ionicons name="refresh-outline" size={18} color={THEME.colors.bg} />
            <Text style={styles.retryButtonText}>Try Again</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <AddMemoryForm onAdd={handleAdd} isAdding={isAdding} />
      <FlatList
        data={memories}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="bookmark-outline" size={48} color={THEME.colors.textSecondary} />
            <Text style={styles.emptyTitle}>No memories yet</Text>
            <Text style={styles.emptySubtitle}>
              Add goals or notes so Ada can personalise her advice
            </Text>
          </View>
        }
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        ItemSeparatorComponent={MemorySeparator}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
    paddingTop: THEME.spacing.md,
  },
  listContent: {
    flexGrow: 1,
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
  },
  separator: {
    height: THEME.spacing.md - 2,
  },
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    paddingTop: THEME.spacing.xxxl * 2,
    gap: THEME.spacing.sm,
  },
  emptyTitle: {
    fontFamily: FONTS.display,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    marginTop: THEME.spacing.md,
  },
  emptySubtitle: {
    fontFamily: FONTS.displayItalic,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  errorContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    gap: THEME.spacing.sm,
  },
  errorTitle: {
    fontFamily: FONTS.display,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
    marginTop: THEME.spacing.md,
  },
  errorSubtitle: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  retryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    marginTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.md - 2,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.textPrimary,
    minHeight: MIN_TOUCH_TARGET,
  },
  retryButtonText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 14,
    color: THEME.colors.bg,
  },
});
