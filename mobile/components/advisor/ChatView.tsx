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

import {
  BG_PAGE,
  BG_CARD,
  INPUT_FILL,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  CTA_PRIMARY,
  CTA_PRESSED,
  ERROR_DARK,
  BORDER_DEFAULT,
} from "../../constants/colors";
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
    padding: 16,
    gap: 12,
  },
  bubble: {
    height: 48,
    borderRadius: 16,
    backgroundColor: BG_CARD,
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
  const [paginationFailed, setPaginationFailed] = useState(false);

  const listRef = useRef<FlatList<AdvisorMessage>>(null);
  const retryCountRef = useRef(0);

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
      setPaginationFailed(false);
    } catch {
      retryCountRef.current += 1;
      if (retryCountRef.current < 3) {
        const delay = retryCountRef.current === 1 ? 2000 : 3000;
        setIsLoadingMore(false);
        setTimeout(() => {
          loadOlderMessages();
        }, delay);
        return;
      }
      setPaginationFailed(true);
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
  // Auto-scroll when new messages arrive
  // -------------------------------------------------------------------------
  useEffect(() => {
    if (messages.length > 0 && !isLoading) {
      setTimeout(() => {
        listRef.current?.scrollToEnd({ animated: true });
      }, ADVISOR_CONFIG.AUTO_SCROLL_DELAY_MS);
    }
  }, [messages.length, isLoading]);

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
          <ActivityIndicator size="small" color={TEXT_SECONDARY} />
        </View>
      );
    }
    return null;
  }, [isLoadingMore]);

  const canSend = inputText.trim().length > 0 && !isSending;

  if (isLoading) {
    return <ChatSkeleton />;
  }

  if (error && messages.length === 0) {
    return (
      <View style={styles.errorContainer}>
        <Ionicons name="alert-circle-outline" size={48} color={TEXT_SECONDARY} />
        <Text style={styles.errorTitle}>Could not load messages</Text>
        <Text style={styles.errorSubtitle}>{error}</Text>
        <Pressable
          onPress={loadMessages}
          style={styles.retryButton}
          accessibilityLabel="Retry loading messages"
          accessibilityRole="button"
        >
          <Ionicons name="refresh-outline" size={18} color="#FFFFFF" />
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
            <Ionicons name="chatbubble-ellipses-outline" size={48} color={TEXT_SECONDARY} />
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
          <Ionicons name="alert-circle" size={16} color={ERROR_DARK} />
          <Text style={styles.errorBannerText}>{error}</Text>
          <Pressable
            onPress={() => setError(null)}
            hitSlop={8}
            accessibilityLabel="Dismiss error"
          >
            <Ionicons name="close" size={16} color={TEXT_SECONDARY} />
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
          placeholderTextColor={TEXT_DISABLED}
          multiline
          maxLength={2000}
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
            <ActivityIndicator size="small" color="#FFFFFF" />
          ) : (
            <Ionicons
              name="send"
              size={20}
              color={canSend ? "#FFFFFF" : TEXT_DISABLED}
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
    backgroundColor: BG_PAGE,
  },
  listContent: {
    flexGrow: 1,
    paddingVertical: 12,
  },
  loadingMore: {
    paddingVertical: 12,
    alignItems: "center",
  },
  emptyContainer: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
    paddingTop: 80,
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
    backgroundColor: BG_PAGE,
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
  retryText: {
    fontSize: 14,
    fontWeight: "600",
    color: "#FFFFFF",
  },
  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginHorizontal: 16,
    marginBottom: 4,
    backgroundColor: "rgba(248,113,113,0.1)",
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  errorBannerText: {
    flex: 1,
    fontSize: 13,
    color: ERROR_DARK,
  },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: BORDER_DEFAULT,
    backgroundColor: BG_PAGE,
    gap: 8,
  },
  textInput: {
    flex: 1,
    backgroundColor: INPUT_FILL,
    borderRadius: 20,
    paddingHorizontal: 16,
    paddingTop: 10,
    paddingBottom: 10,
    fontSize: 15,
    color: TEXT_PRIMARY,
    maxHeight: 120,
    minHeight: MIN_TOUCH_TARGET,
  },
  sendButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    borderRadius: MIN_TOUCH_TARGET / 2,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: BORDER_DEFAULT,
  },
  sendButtonActive: {
    backgroundColor: CTA_PRIMARY,
  },
  sendButtonPressed: {
    backgroundColor: CTA_PRESSED,
  },
});
