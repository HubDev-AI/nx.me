/**
 * ChatView — message list + text input for chatting with Ada.
 *
 * Premium-only: if a 402 is received on POST /advisor/messages,
 * the PaywallModal is shown. Includes auto-scroll to bottom,
 * typing indicator, skeleton loading, and KeyboardAvoidingView.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  FlatList,
  TextInput,
  Pressable,
  Text,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  StyleSheet,
  Dimensions,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { ADVISOR_CONFIG, MIN_TOUCH_TARGET } from "../../constants/config";
import {
  fetchMessages,
  sendMessage,
  isPremiumRequired,
} from "../../lib/advisor";
import type { AdvisorMessage } from "../../lib/advisor";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { PaywallModal } from "../paywall/PaywallModal";

const SCREEN_WIDTH = Dimensions.get("window").width;

/** Skeleton placeholder for loading messages */
function ChatSkeleton() {
  return (
    <View style={skeletonStyles.container}>
      {[0.6, 0.4, 0.8, 0.5].map((widthFraction, i) => (
        <View
          key={i}
          style={[
            skeletonStyles.bubble,
            i % 2 === 0 ? skeletonStyles.left : skeletonStyles.right,
            { width: Math.round((SCREEN_WIDTH - 32) * widthFraction * 0.8) },
          ]}
        />
      ))}
    </View>
  );
}

const skeletonStyles = StyleSheet.create({
  container: {
    flex: 1,
    padding: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  bubble: {
    height: 48,
    borderRadius: THEME.radius.lg,
    backgroundColor: THEME.colors.surface,
  },
  left: {
    alignSelf: "flex-start",
    width: "60%",
  },
  right: {
    alignSelf: "flex-end",
    width: "50%",
  },
});

export function ChatView() {
  const { theme } = useTheme();
  // -------------------------------------------------------------------------
  // State
  // -------------------------------------------------------------------------
  const [messages, setMessages] = useState<AdvisorMessage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [inputText, setInputText] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [showPaywall, setShowPaywall] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);


  const listRef = useRef<FlatList<AdvisorMessage>>(null);
  const retryCountRef = useRef(0);
  const retryTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Track the last message ID to only auto-scroll on appended messages */
  const lastMessageIdRef = useRef<string | null>(null);

  // -------------------------------------------------------------------------
  // Load initial messages
  // -------------------------------------------------------------------------
  const loadMessages = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetchMessages();
      // API returns newest first; we display oldest first, so reverse
      setMessages(response.messages.slice().reverse());
      setHasMore(response.has_more);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load messages";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMessages();
    return () => {
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
    };
  }, [loadMessages]);

  // -------------------------------------------------------------------------
  // Load older messages (pagination)
  // -------------------------------------------------------------------------
  const loadOlderMessages = useCallback(async () => {
    if (!hasMore || isLoadingMore || messages.length === 0) return;
    setIsLoadingMore(true);
    try {
      // The oldest message in our list is the cursor for older pages
      const oldestMessage = messages[0]!;
      const response = await fetchMessages(oldestMessage.id);
      const older = response.messages.slice().reverse();
      setMessages((prev) => [...older, ...prev]);
      setHasMore(response.has_more);
      retryCountRef.current = 0;
    } catch {
      retryCountRef.current += 1;
      if (retryCountRef.current < 3) {
        const delay = retryCountRef.current === 1 ? 2000 : 3000;
        setIsLoadingMore(false);
        retryTimeoutRef.current = setTimeout(() => {
          loadOlderMessages();
        }, delay);
        return;
      }
      // Reset so next user-initiated scroll starts a fresh retry round
      retryCountRef.current = 0;
    } finally {
      setIsLoadingMore(false);
    }
  }, [hasMore, isLoadingMore, messages]);

  // -------------------------------------------------------------------------
  // Send message
  // -------------------------------------------------------------------------
  const handleSend = useCallback(async () => {
    const trimmed = inputText.trim();
    if (!trimmed || isSending) return;

    setInputText("");
    setIsSending(true);

    // Optimistic: add user message immediately
    const optimisticUserMsg: AdvisorMessage = {
      id: `temp-${Date.now()}`,
      role: "user",
      content: trimmed,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUserMsg]);

    try {
      // Send and get Ada's response (backend returns the assistant reply)
      const adaResponse = await sendMessage(trimmed);

      // Replace optimistic user message with the real one from the response
      // and append Ada's reply
      setMessages((prev) => {
        const withoutOptimistic = prev.filter(
          (m) => m.id !== optimisticUserMsg.id,
        );
        // Add user message with correct ID (the backend may echo it) and Ada's reply
        return [
          ...withoutOptimistic,
          { ...optimisticUserMsg, id: `user-${Date.now()}` },
          adaResponse,
        ];
      });

      // Auto-scroll to bottom
      setTimeout(() => {
        listRef.current?.scrollToEnd({ animated: true });
      }, ADVISOR_CONFIG.AUTO_SCROLL_DELAY_MS);
    } catch (err) {
      if (isPremiumRequired(err)) {
        // Remove optimistic message and show paywall
        setMessages((prev) =>
          prev.filter((m) => m.id !== optimisticUserMsg.id),
        );
        setInputText(trimmed); // Restore input
        setShowPaywall(true);
      } else {
        // Mark optimistic message as failed (keep in list)
        setError("Failed to send. Tap retry.");
      }
    } finally {
      setIsSending(false);
    }
  }, [inputText, isSending]);

  // -------------------------------------------------------------------------
  // Auto-scroll only when a NEW message is appended (not on prepend/pagination)
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (messages.length === 0 || isLoading) return;

    const currentLastId = messages[messages.length - 1]?.id ?? null;
    const previousLastId = lastMessageIdRef.current;
    lastMessageIdRef.current = currentLastId;

    // Only scroll when the last message changed (new message appended)
    if (currentLastId && currentLastId !== previousLastId) {
      setTimeout(() => {
        listRef.current?.scrollToEnd({ animated: true });
      }, ADVISOR_CONFIG.AUTO_SCROLL_DELAY_MS);
    }
  }, [messages, isLoading]);

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  const keyExtractor = useCallback((item: AdvisorMessage) => item.id, []);

  const renderItem = useCallback(
    ({ item }: { item: AdvisorMessage }) => <MessageBubble message={item} />,
    [],
  );

  const renderHeader = useCallback(() => {
    if (isLoadingMore) {
      return (
        <View style={styles.loadingMore}>
          <ActivityIndicator size="small" color={theme.accent} />
        </View>
      );
    }
    return null;
  }, [isLoadingMore, theme.accent]);

  const canSend = inputText.trim().length > 0 && !isSending;

  if (isLoading) {
    return <ChatSkeleton />;
  }

  if (error && messages.length === 0) {
    return (
      <View style={styles.errorContainer}>
        <Ionicons name="alert-circle-outline" size={48} color={THEME.colors.textSecondary} />
        <Text style={styles.errorTitle}>Could not load messages</Text>
        <Text style={styles.errorSubtitle}>{error}</Text>
        <Pressable
          onPress={loadMessages}
          style={[styles.retryButton, { backgroundColor: theme.accent }]}
          accessibilityLabel="Retry loading messages"
          accessibilityRole="button"
        >
          <Ionicons name="refresh-outline" size={18} color={THEME.colors.bg} />
          <Text style={styles.retryText}>Try Again</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      keyboardVerticalOffset={Platform.OS === "ios" ? 90 : 0}
    >
      {/* Message list */}
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={keyExtractor}
        renderItem={renderItem}
        ListHeaderComponent={renderHeader}
        ListFooterComponent={isSending ? TypingIndicator : null}
        onStartReached={loadOlderMessages}
        onStartReachedThreshold={0.3}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={styles.listContent}
        maxToRenderPerBatch={ADVISOR_CONFIG.MAX_TO_RENDER_PER_BATCH}
        updateCellsBatchingPeriod={ADVISOR_CONFIG.UPDATE_CELLS_BATCHING_PERIOD_MS}
        windowSize={ADVISOR_CONFIG.WINDOW_SIZE}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Ionicons name="chatbubble-ellipses-outline" size={48} color={THEME.colors.textSecondary} />
            <Text style={styles.emptyTitle}>Chat with Ada</Text>
            <Text style={styles.emptySubtitle}>
              Ask about styling, grooming, or anything she can help with
            </Text>
          </View>
        }
      />

      {/* Send error banner */}
      {error && messages.length > 0 && (
        <View style={styles.errorBanner} accessibilityRole="alert">
          <Ionicons name="alert-circle" size={16} color={THEME.colors.destructive} />
          <Text style={styles.errorBannerText}>{error}</Text>
          <Pressable
            onPress={() => setError(null)}
            hitSlop={8}
            accessibilityLabel="Dismiss error"
          >
            <Ionicons name="close" size={16} color={THEME.colors.textSecondary} />
          </Pressable>
        </View>
      )}

      {/* Input bar */}
      <View style={styles.inputBar}>
        <TextInput
          style={styles.textInput}
          value={inputText}
          onChangeText={setInputText}
          placeholder="Message Ada..."
          placeholderTextColor={THEME.colors.textDisabled}
          multiline
          maxLength={ADVISOR_CONFIG.MESSAGE_MAX_LENGTH}
          returnKeyType="default"
          accessibilityLabel="Message input"
        />
        <Pressable
          onPress={handleSend}
          disabled={!canSend}
          style={({ pressed }) => [
            styles.sendButton,
            canSend && styles.sendButtonActive,
            pressed && canSend && styles.sendButtonPressed,
          ]}
          accessibilityLabel="Send message"
          accessibilityRole="button"
        >
          {isSending ? (
            <ActivityIndicator size="small" color={THEME.colors.bg} />
          ) : (
            <Ionicons
              name="send"
              size={20}
              color={canSend ? THEME.colors.bg : THEME.colors.textDisabled}
            />
          )}
        </Pressable>
      </View>

      {/* Paywall modal — shown on 402 */}
      <PaywallModal
        visible={showPaywall}
        onClose={() => setShowPaywall(false)}
      />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  listContent: {
    flexGrow: 1,
    paddingVertical: THEME.spacing.md,
  },
  loadingMore: {
    paddingVertical: THEME.spacing.md,
    alignItems: "center",
  },
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: THEME.spacing.xxxl,
    paddingTop: THEME.spacing.xxxl * 2.5,
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
    backgroundColor: THEME.colors.bg,
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
    minHeight: MIN_TOUCH_TARGET,
  },
  retryText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 14,
    color: THEME.colors.bg,
  },
  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    marginHorizontal: THEME.spacing.lg,
    marginBottom: THEME.spacing.xs,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.sm,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.sm,
  },
  errorBannerText: {
    flex: 1,
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.destructive,
  },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: THEME.colors.glassBorder,
    backgroundColor: THEME.colors.glass,
    gap: THEME.spacing.sm,
  },
  textInput: {
    flex: 1,
    fontFamily: FONTS.body,
    backgroundColor: THEME.colors.surfaceElevated,
    borderRadius: THEME.radius.xl,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md - 2,
    paddingBottom: THEME.spacing.md - 2,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
    maxHeight: 120,
    minHeight: MIN_TOUCH_TARGET,
  },
  sendButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: MIN_TOUCH_TARGET / 2,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: THEME.colors.border,
  },
  sendButtonActive: {
    backgroundColor: THEME.colors.textPrimary,
  },
  sendButtonPressed: {
    opacity: 0.85,
  },
});
