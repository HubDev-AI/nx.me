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

import {
  BG_PAGE,
  BG_CARD,
  BG_ELEVATED,
  INPUT_FILL,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  CTA_PRESSED,
  ERROR_DARK,
  BORDER_DEFAULT,
  ADA_BUBBLE_BORDER,
} from "../../constants/colors";
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
          <Ionicons name="trash-outline" size={22} color="#FFFFFF" />
        </Pressable>
      </View>

      {/* Card on top, swipeable */}
      <Animated.View
        style={[rowStyles.card, { transform: [{ translateX }] }]}
        {...panResponder.panHandlers}
      >
        <View style={rowStyles.iconContainer}>
          <Ionicons
            name={memoryTypeIcon(memory.type)}
            size={20}
            color={ADA_BUBBLE_BORDER}
          />
        </View>
        <View style={rowStyles.content}>
          <View style={rowStyles.header}>
            <Text style={rowStyles.typeLabel}>
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
    borderRadius: 14,
  },
  deleteContainer: {
    ...StyleSheet.absoluteFillObject,
    justifyContent: "center",
    alignItems: "flex-end",
  },
  deleteButton: {
    width: DELETE_BUTTON_WIDTH,
    height: "100%",
    backgroundColor: ERROR_DARK,
    borderTopRightRadius: 14,
    borderBottomRightRadius: 14,
    alignItems: "center",
    justifyContent: "center",
  },
  card: {
    flexDirection: "row",
    backgroundColor: BG_CARD,
    borderRadius: 14,
    padding: 14,
    gap: 12,
  },
  iconContainer: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(244,63,94,0.08)",
    alignItems: "center",
    justifyContent: "center",
    marginTop: 2,
  },
  content: {
    flex: 1,
    gap: 4,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  typeLabel: {
    fontSize: 12,
    fontWeight: "600",
    color: ADA_BUBBLE_BORDER,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  date: {
    fontSize: 12,
    color: TEXT_SECONDARY,
  },
  body: {
    fontSize: 14,
    lineHeight: 20,
    color: TEXT_PRIMARY,
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
              selectedType === t.value && formStyles.typeChipActive,
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
          placeholderTextColor={TEXT_DISABLED}
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
            <ActivityIndicator size="small" color="#FFFFFF" />
          ) : (
            <Ionicons
              name="add"
              size={24}
              color={content.trim() ? "#FFFFFF" : TEXT_DISABLED}
            />
          )}
        </Pressable>
      </View>
    </View>
  );
}

const formStyles = StyleSheet.create({
  container: {
    paddingHorizontal: 16,
    paddingBottom: 12,
    gap: 10,
  },
  typeRow: {
    flexDirection: "row",
    gap: 8,
  },
  typeChip: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 16,
    backgroundColor: BG_ELEVATED,
    minHeight: 44,
    justifyContent: "center",
  },
  typeChipActive: {
    backgroundColor: CTA_PRIMARY,
  },
  typeChipText: {
    fontSize: 13,
    fontWeight: "500",
    color: TEXT_SECONDARY,
  },
  typeChipTextActive: {
    color: "#FFFFFF",
    fontWeight: "600",
  },
  inputRow: {
    flexDirection: "row",
    gap: 8,
    alignItems: "flex-end",
  },
  input: {
    flex: 1,
    backgroundColor: INPUT_FILL,
    borderRadius: 14,
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 10,
    fontSize: 14,
    color: TEXT_PRIMARY,
    maxHeight: 80,
    minHeight: MIN_TOUCH_TARGET,
  },
  addButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: MIN_TOUCH_TARGET / 2,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: BORDER_DEFAULT,
  },
  addButtonActive: {
    backgroundColor: CTA_PRIMARY,
  },
  addButtonPressed: {
    backgroundColor: CTA_PRESSED,
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
    padding: 16,
    gap: 12,
  },
  card: {
    flexDirection: "row",
    backgroundColor: BG_CARD,
    borderRadius: 14,
    padding: 14,
    gap: 12,
  },
  icon: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.05)",
  },
  lines: {
    flex: 1,
    gap: 8,
  },
  line: {
    height: 12,
    borderRadius: 6,
    backgroundColor: "rgba(255,255,255,0.05)",
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
            // Optimistic removal
            setMemories((prev) => prev.filter((m) => m.id !== memoryId));
            try {
              await deleteMemory(memoryId);
            } catch {
              // Re-load on failure
              loadMemories();
            }
          },
        },
      ],
    );
  }, [loadMemories]);

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
          <Ionicons name="alert-circle-outline" size={48} color={TEXT_SECONDARY} />
          <Text style={styles.errorTitle}>Could not load memories</Text>
          <Text style={styles.errorSubtitle}>{error}</Text>
          <Pressable
            onPress={loadMemories}
            style={styles.retryButton}
            accessibilityLabel="Retry loading memories"
            accessibilityRole="button"
          >
            <Ionicons name="refresh-outline" size={18} color="#FFFFFF" />
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
            <Ionicons name="bookmark-outline" size={48} color={TEXT_SECONDARY} />
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
    backgroundColor: BG_PAGE,
    paddingTop: 12,
  },
  listContent: {
    flexGrow: 1,
    paddingHorizontal: 16,
    paddingBottom: 16,
  },
  separator: {
    height: 10,
  },
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    paddingTop: 60,
    gap: 8,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginTop: 12,
  },
  emptySubtitle: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    textAlign: "center",
    lineHeight: 20,
  },
  errorContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    gap: 8,
  },
  errorTitle: {
    fontSize: 18,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginTop: 12,
  },
  errorSubtitle: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    textAlign: "center",
    lineHeight: 20,
  },
  retryButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginTop: 16,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: CTA_PRIMARY,
    minHeight: MIN_TOUCH_TARGET,
  },
  retryButtonText: {
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
  },
});
