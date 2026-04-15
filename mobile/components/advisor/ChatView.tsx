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
  Pressable,
  Text,
  Keyboard,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  StyleSheet,
  Dimensions,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { ADVISOR_CONFIG, PAGINATION_CONFIG } from "../../constants/config";
import { useCapabilities } from "../../lib/capabilities";
import { TAB_BAR_HEIGHT } from "../../app/(tabs)/_layout";
import {
  fetchMessages,
  sendMessage,
  isPremiumRequired,
} from "../../lib/advisor";
import type { AdvisorMessage } from "../../lib/advisor";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { AdvisorComposer } from "./AdvisorComposer";
import { PaywallModal } from "../paywall/PaywallModal";
import { EmptyState } from "../ui/EmptyState";

/** The floating tab bar renders whenever at least two tabs are visible. */
const MIN_TABS_FOR_FLOATING_BAR = 2;

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
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
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
  const insets = useSafeAreaInsets();
  const caps = useCapabilities();
  // The floating tab bar renders on advisor + create (or more). When it's
  // visible we must lift the input above it, otherwise paddingBottom only
  // covers the home-indicator inset and the bar clips the TextInput.
  const visibleTabCount =
    1 /* create */ +
    (caps.canSeeFeed ? 2 : 0) +
    (caps.canUseAdvisor ? 1 : 0);
  const floatingTabBarVisible = visibleTabCount >= MIN_TABS_FOR_FLOATING_BAR;
  // Track keyboard so we drop the TAB_BAR_HEIGHT offset while it's open — the
  // floating tab bar hides itself on keyboard show, so keeping the offset
  // would leave a visible gap between the input and the keyboard (BUG 3).
  const [isKeyboardVisible, setIsKeyboardVisible] = useState(false);
  useEffect(() => {
    const showSub = Keyboard.addListener(
      Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow",
      () => setIsKeyboardVisible(true),
    );
    const hideSub = Keyboard.addListener(
      Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide",
      () => setIsKeyboardVisible(false),
    );
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);
  const effectiveTabBarOffset =
    floatingTabBarVisible && !isKeyboardVisible ? TAB_BAR_HEIGHT : 0;
  const inputBottomPadding =
    Math.max(insets.bottom, THEME.spacing.sm) + effectiveTabBarOffset;
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
  /** Preserves the user's message across paywall dismissals */
  const savedMessageRef = useRef<string | null>(null);
  /** Cursor for loading older message pages */
  const nextCursorRef = useRef<string | null>(null);
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
      nextCursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "We couldn't load your messages.";
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
    if (!hasMore || isLoadingMore || !nextCursorRef.current) return;
    setIsLoadingMore(true);
    try {
      const response = await fetchMessages(nextCursorRef.current);
      const older = response.messages.slice().reverse();
      setMessages((prev) => [...older, ...prev]);
      nextCursorRef.current = response.next_cursor;
      setHasMore(response.has_more);
      retryCountRef.current = 0;
    } catch {
      retryCountRef.current += 1;
      if (retryCountRef.current < PAGINATION_CONFIG.MAX_RETRIES) {
        const attemptIndex = Math.min(
          retryCountRef.current - 1,
          PAGINATION_CONFIG.RETRY_DELAYS_MS.length - 1,
        );
        const delay = PAGINATION_CONFIG.RETRY_DELAYS_MS[attemptIndex]!;
        setIsLoadingMore(false);
        // Clear any previously scheduled retry so rapid scrolls don't stack timers.
        if (retryTimeoutRef.current) {
          clearTimeout(retryTimeoutRef.current);
        }
        retryTimeoutRef.current = setTimeout(() => {
          retryTimeoutRef.current = null;
          loadOlderMessages();
        }, delay);
        return;
      }
      // Reset so next user-initiated scroll starts a fresh retry round
      retryCountRef.current = 0;
    } finally {
      setIsLoadingMore(false);
    }
  }, [hasMore, isLoadingMore]);

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
        savedMessageRef.current = trimmed;
        setInputText(trimmed); // Restore input immediately
        setShowPaywall(true);
      } else {
        // Mark optimistic message as failed (keep in list)
        setError("Couldn't send that. Tap retry.");
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

  if (isLoading) {
    return <ChatSkeleton />;
  }

  if (error && messages.length === 0) {
    return (
      <EmptyState
        icon="alert-circle-outline"
        title="Could not load messages"
        description={error}
        action={{
          label: "Try Again",
          onPress: loadMessages,
          accessibilityLabel: "Retry loading messages",
        }}
      />
    );
  }

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === "ios" ? "padding" : Platform.OS === "web" ? undefined : "height"}
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
          <EmptyState
            icon="sparkles-outline"
            title="Start a conversation"
            description="Ask Ada for style advice"
          />
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
      <AdvisorComposer
        value={inputText}
        onChangeText={setInputText}
        onSubmit={handleSend}
        placeholder="Message Ada..."
        disabled={isSending}
        submitIcon="send"
        maxLength={ADVISOR_CONFIG.MESSAGE_MAX_LENGTH}
        accessibilityLabel="Message input"
        submitAccessibilityLabel="Send message"
        bottomPadding={inputBottomPadding}
        separator
      />

      {/* Paywall modal — shown on 402 */}
      <PaywallModal
        visible={showPaywall}
        onClose={() => {
          setShowPaywall(false);
          // Restore the user's message if paywall was dismissed without purchase
          if (savedMessageRef.current) {
            setInputText(savedMessageRef.current);
            savedMessageRef.current = null;
          }
        }}
      />
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
    paddingVertical: THEME.spacing.md,
  },
  loadingMore: {
    paddingVertical: THEME.spacing.md,
    alignItems: "center",
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
});
