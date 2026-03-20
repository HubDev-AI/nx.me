/**
 * Post detail — full-screen before/after view with larger images.
 * Reuses ReactionButton and CommentsSheet components.
 */
import { useState, useCallback } from "react";
import { View, Text, Image, ScrollView, StyleSheet, Pressable } from "react-native";
import { useLocalSearchParams, Stack, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  BEFORE_OVERLAY,
  AFTER_OVERLAY_STRONG,
} from "../../constants/colors";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { ReactionButton } from "../../components/feed/ReactionButton";
import { CommentsSheet } from "../../components/comments/CommentsSheet";

export default function PostDetailScreen() {
  const {
    postId,
    beforeImage,
    afterImage,
    caption,
    displayName,
    reactionCount: initialReactionCount,
    commentCount: initialCommentCount,
    timeAgo,
    hasReacted: initialHasReacted,
  } = useLocalSearchParams<{
    postId: string;
    beforeImage: string;
    afterImage: string;
    caption?: string;
    displayName?: string;
    reactionCount?: string;
    commentCount?: string;
    timeAgo?: string;
    hasReacted?: string;
  }>();

  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { theme } = useTheme();

  const [reactionCount, setReactionCount] = useState(Number(initialReactionCount) || 0);
  const [commentCount, setCommentCount] = useState(Number(initialCommentCount) || 0);
  const [hasReacted, setHasReacted] = useState(initialHasReacted === "true");
  const [commentsVisible, setCommentsVisible] = useState(false);

  const handleReact = useCallback(() => {
    if (hasReacted) return;
    setHasReacted(true);
    setReactionCount((c) => c + 1);
    // TODO: API call to react — same as useFeed.reactToPost
  }, [hasReacted]);

  const handleCommentPosted = useCallback(() => {
    setCommentCount((c) => c + 1);
  }, []);

  return (
    <>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView
        style={styles.container}
        contentContainerStyle={{ paddingBottom: insets.bottom + 16 }}
      >
        {/* Before image — full width */}
        <View style={styles.imageSection}>
          <View style={styles.labelRow}>
            <View style={[styles.label, styles.beforeLabel]}>
              <Text style={styles.labelText}>BEFORE</Text>
            </View>
          </View>
          <Image
            source={{ uri: beforeImage }}
            style={styles.fullImage}
            resizeMode="cover"
          />
        </View>

        {/* After image — full width */}
        <View style={styles.imageSection}>
          <View style={styles.labelRow}>
            <View style={[styles.label, styles.afterLabel, { backgroundColor: theme.accent + "CC" }]}>
              <Text style={styles.labelText}>AFTER</Text>
            </View>
          </View>
          <Image
            source={{ uri: afterImage }}
            style={styles.fullImage}
            resizeMode="cover"
          />
        </View>

        {/* Caption */}
        {caption ? (
          <Text style={styles.caption}>{caption}</Text>
        ) : null}

        {/* Actions — reusing shared components */}
        <View style={styles.actionsRow}>
          <ReactionButton
            reactionCount={reactionCount}
            hasReacted={hasReacted}
            onReact={handleReact}
          />

          <Pressable
            onPress={() => setCommentsVisible(true)}
            style={styles.commentButton}
            accessibilityLabel={`${commentCount} comments, tap to view`}
            accessibilityRole="button"
          >
            <Ionicons name="chatbubble-outline" size={18} color={TEXT_SECONDARY} />
            <Text style={styles.commentCountText}>{commentCount}</Text>
          </Pressable>

          <Text style={styles.timeAgo}>{timeAgo || ""}</Text>
        </View>
      </ScrollView>

      {/* Floating back button — top-left circle */}
      <Pressable
        onPress={() => router.back()}
        style={[styles.floatingBack, { top: insets.top + 12 }]}
        accessibilityLabel="Go back"
        accessibilityRole="button"
      >
        <Ionicons name="close" size={22} color="#e8e8e8" />
      </Pressable>

      <CommentsSheet
        visible={commentsVisible}
        postId={postId ?? ""}
        onClose={() => setCommentsVisible(false)}
        onCommentPosted={handleCommentPosted}
      />
    </>
  );
}

const styles = StyleSheet.create({
  floatingBack: {
    position: "absolute",
    right: 32,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: "rgba(10, 10, 10, 0.55)",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 10,
  },
  container: {
    flex: 1,
    backgroundColor: BG_PAGE,
  },
  imageSection: {
    marginBottom: 2,
  },
  labelRow: {
    position: "absolute",
    top: 12,
    left: 16,
    zIndex: 1,
  },
  label: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
  },
  beforeLabel: {
    backgroundColor: BEFORE_OVERLAY,
  },
  afterLabel: {
    backgroundColor: AFTER_OVERLAY_STRONG,
  },
  labelText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 11,
    color: "#ffffff",
    letterSpacing: 1,
  },
  fullImage: {
    width: "100%",
    aspectRatio: 3 / 4,
  },
  caption: {
    fontFamily: FONTS.body,
    fontSize: 16,
    lineHeight: 24,
    color: TEXT_PRIMARY,
    paddingHorizontal: 20,
    paddingTop: 16,
  },
  actionsRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 20,
    paddingVertical: 14,
    gap: 12,
  },
  commentButton: {
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    minHeight: 44,
    paddingHorizontal: 4,
    paddingVertical: 6,
  },
  commentCountText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: TEXT_SECONDARY,
  },
  timeAgo: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: TEXT_SECONDARY,
    marginLeft: "auto",
  },
});
