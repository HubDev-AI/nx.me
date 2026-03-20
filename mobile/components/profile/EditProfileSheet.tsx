import { useState, useCallback, useRef, useEffect } from "react";
import {
  View,
  Text,
  TextInput,
  Image,
  Pressable,
  Animated,
  Modal,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  AccessibilityInfo,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";

import { THEME } from "../../constants/theme";
import {
  IMAGE_PICKER as IMAGE_PICKER_CONFIG,
  MIN_TOUCH_TARGET,
  PROFILE_CONFIG,
} from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import type { UserProfile, UpdateProfilePayload } from "./types";

const AVATAR_SIZE = 88;
const SHEET_ENTER_DURATION_MS = 300;
const SHEET_EXIT_DURATION_MS = 200;

interface EditProfileSheetProps {
  visible: boolean;
  profile: UserProfile;
  isUpdating: boolean;
  updateError: string | null;
  onSave: (payload: UpdateProfilePayload) => Promise<boolean>;
  onClose: () => void;
}

/**
 * Slide-in sheet for editing display name and avatar.
 * Confirms on unsaved changes before dismissing.
 */
export function EditProfileSheet({
  visible,
  profile,
  isUpdating,
  updateError,
  onSave,
  onClose,
}: EditProfileSheetProps) {
  const { theme } = useTheme();
  const [displayName, setDisplayName] = useState(
    profile.display_name ?? "",
  );
  const [avatarUri, setAvatarUri] = useState(profile.avatar_url ?? "");
  const [hasChanges, setHasChanges] = useState(false);

  const slideAnim = useRef(new Animated.Value(0)).current;
  const scrimAnim = useRef(new Animated.Value(0)).current;
  const cancelButtonRef = useRef<React.ElementRef<typeof Pressable>>(null);

  // Reset form when profile changes or sheet opens
  useEffect(() => {
    if (visible) {
      setDisplayName(profile.display_name ?? "");
      setAvatarUri(profile.avatar_url ?? "");
      setHasChanges(false);

      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 1,
          duration: SHEET_ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 1,
          duration: SHEET_ENTER_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start();

      AccessibilityInfo.announceForAccessibility("Dialog opened");
      cancelButtonRef.current?.focus();
    }
  }, [visible, profile, slideAnim, scrimAnim]);

  const animateClose = useCallback(
    (callback: () => void) => {
      Animated.parallel([
        Animated.timing(slideAnim, {
          toValue: 0,
          duration: SHEET_EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(scrimAnim, {
          toValue: 0,
          duration: SHEET_EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start(callback);
    },
    [slideAnim, scrimAnim],
  );

  const handleClose = useCallback(() => {
    if (hasChanges) {
      Alert.alert(
        "Unsaved Changes",
        "You have unsaved changes. Are you sure you want to discard them?",
        [
          { text: "Keep Editing", style: "cancel" },
          {
            text: "Discard",
            style: "destructive",
            onPress: () => animateClose(onClose),
          },
        ],
      );
    } else {
      animateClose(onClose);
    }
  }, [hasChanges, animateClose, onClose]);

  const handleDisplayNameChange = useCallback(
    (text: string) => {
      setDisplayName(text);
      const original = profile.display_name ?? "";
      setHasChanges(text !== original);
    },
    [profile.display_name],
  );

  const handlePickAvatar = useCallback(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images"],
      allowsEditing: true,
      aspect: IMAGE_PICKER_CONFIG.ASPECT,
      quality: IMAGE_PICKER_CONFIG.QUALITY,
    });

    if (!result.canceled && result.assets[0]) {
      const newUri = result.assets[0].uri;
      setAvatarUri(newUri);
      setHasChanges(true);
    }
  }, []);

  const handleSave = useCallback(async () => {
    const payload: UpdateProfilePayload = {};

    const originalDisplayName = profile.display_name ?? "";
    if (displayName !== originalDisplayName) {
      payload.display_name = displayName.trim();
    }

    if (Object.keys(payload).length === 0) {
      animateClose(onClose);
      return;
    }

    const success = await onSave(payload);
    if (success) {
      animateClose(onClose);
    }
  }, [displayName, profile, onSave, animateClose, onClose]);

  const translateY = slideAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [400, 0],
  });

  const scrimOpacity = scrimAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 0.5],
  });

  const isDisplayNameValid =
    displayName.trim().length > 0 &&
    displayName.trim().length <= PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH;

  const charCount = displayName.length;
  const charCountNearLimit =
    charCount > PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH * 0.8;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleClose}
    >
      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : "height"}
        style={styles.modalContainer}
      >
        {/* Scrim */}
        <Animated.View
          style={[styles.scrim, { opacity: scrimOpacity }]}
        >
          <Pressable
            style={StyleSheet.absoluteFill}
            onPress={handleClose}
            accessibilityLabel="Close edit profile"
            accessibilityRole="button"
          />
        </Animated.View>

        {/* Sheet */}
        <Animated.View
          style={[
            styles.sheet,
            { transform: [{ translateY }] },
          ]}
        >
          {/* Glass top border */}
          <View style={styles.sheetTopBorder} />

          {/* Handle bar */}
          <View style={styles.handleBar} />

          {/* Header */}
          <View style={styles.header}>
            <Pressable
              ref={cancelButtonRef}
              onPress={handleClose}
              style={styles.headerButton}
              accessibilityLabel="Cancel"
              accessibilityRole="button"
            >
              <Text style={styles.cancelText}>Cancel</Text>
            </Pressable>

            <Text style={styles.headerTitle}>Edit Profile</Text>

            <Pressable
              onPress={handleSave}
              disabled={isUpdating || !isDisplayNameValid}
              style={[
                styles.saveButton,
                { backgroundColor: theme.accent },
                (!isDisplayNameValid || isUpdating) &&
                  styles.saveButtonDisabled,
              ]}
              accessibilityLabel="Save profile changes"
              accessibilityRole="button"
              accessibilityState={{ disabled: isUpdating || !isDisplayNameValid }}
            >
              <Text
                style={[
                  styles.saveButtonText,
                  (!isDisplayNameValid || isUpdating) &&
                    styles.saveButtonTextDisabled,
                ]}
              >
                {isUpdating ? "Saving..." : "Save"}
              </Text>
            </Pressable>
          </View>

          {/* Avatar picker */}
          <Pressable
            onPress={handlePickAvatar}
            style={styles.avatarPicker}
            accessibilityLabel="Change avatar photo"
            accessibilityRole="button"
          >
            <View
              style={[styles.avatarRing, { borderColor: theme.accent + "60" }]}
            >
              {avatarUri ? (
                <Image
                  source={{ uri: avatarUri }}
                  style={styles.avatar}
                  accessibilityLabel="Current avatar"
                />
              ) : (
                <View style={[styles.avatar, styles.avatarPlaceholder]}>
                  <Ionicons
                    name="person"
                    size={36}
                    color={THEME.colors.textSecondary}
                  />
                </View>
              )}
            </View>
            <View style={[styles.avatarBadge, { backgroundColor: theme.accent }]}>
              <Ionicons name="camera" size={14} color={THEME.colors.bg} />
            </View>
          </Pressable>
          <Text style={styles.avatarHint}>Tap to change photo</Text>

          {/* Display name input */}
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>DISPLAY NAME</Text>
            <TextInput
              value={displayName}
              onChangeText={handleDisplayNameChange}
              style={styles.input}
              placeholderTextColor={THEME.colors.textMuted}
              placeholder="Your display name"
              maxLength={PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH}
              autoCapitalize="words"
              returnKeyType="done"
              accessibilityLabel="Display name"
            />
            <Text
              style={[
                styles.charCount,
                charCountNearLimit && styles.charCountWarning,
              ]}
            >
              {charCount}/{PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH}
            </Text>
          </View>

          {/* Error message */}
          {updateError ? (
            <View style={styles.errorContainer}>
              <Ionicons
                name="alert-circle"
                size={16}
                color={THEME.colors.destructive}
              />
              <Text style={styles.errorText}>{updateError}</Text>
            </View>
          ) : null}
        </Animated.View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalContainer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  scrim: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "#000000",
  },
  sheet: {
    backgroundColor: THEME.colors.glass,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    paddingBottom: THEME.spacing.xxl,
    overflow: "hidden",
  },
  sheetTopBorder: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    height: StyleSheet.hairlineWidth,
    backgroundColor: "rgba(255, 255, 255, 0.1)",
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255, 255, 255, 0.25)",
    alignSelf: "center",
    marginTop: THEME.spacing.sm,
    marginBottom: THEME.spacing.sm,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
  },
  headerButton: {
    minWidth: 60,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  headerTitle: {
    fontFamily: FONTS.display,
    fontSize: 18,
    color: THEME.colors.textPrimary,
    letterSpacing: THEME.typography.heading.letterSpacing,
  },
  cancelText: {
    fontFamily: FONTS.body,
    fontSize: 16,
    color: THEME.colors.textSecondary,
  },
  saveButton: {
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.sm,
    minHeight: 36,
    alignItems: "center",
    justifyContent: "center",
  },
  saveButtonDisabled: {
    opacity: 0.4,
  },
  saveButtonText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 14,
    color: THEME.colors.bg,
  },
  saveButtonTextDisabled: {
    color: THEME.colors.bg,
  },
  avatarPicker: {
    alignSelf: "center",
    marginTop: THEME.spacing.xl,
    position: "relative",
  },
  avatarRing: {
    width: AVATAR_SIZE + 8,
    height: AVATAR_SIZE + 8,
    borderRadius: (AVATAR_SIZE + 8) / 2,
    borderWidth: 2,
    alignItems: "center",
    justifyContent: "center",
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarPlaceholder: {
    backgroundColor: THEME.colors.surface,
    borderWidth: 1,
    borderColor: THEME.colors.border,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarBadge: {
    position: "absolute",
    bottom: 2,
    right: 2,
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: THEME.colors.bg,
  },
  avatarHint: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: THEME.colors.textSecondary,
    textAlign: "center",
    marginTop: THEME.spacing.sm,
    marginBottom: THEME.spacing.xxl,
  },
  fieldContainer: {
    paddingHorizontal: THEME.spacing.lg,
    marginBottom: THEME.spacing.lg,
  },
  fieldLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 11,
    color: THEME.colors.textSecondary,
    marginBottom: THEME.spacing.sm,
    textTransform: "uppercase",
    letterSpacing: 1,
  },
  input: {
    fontFamily: FONTS.body,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.md,
    fontSize: 16,
    color: THEME.colors.textPrimary,
    minHeight: MIN_TOUCH_TARGET,
  },
  charCount: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
    textAlign: "right",
    marginTop: THEME.spacing.xs,
  },
  charCountWarning: {
    color: THEME.colors.destructive,
  },
  errorContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    paddingHorizontal: THEME.spacing.lg,
    marginTop: THEME.spacing.sm,
  },
  errorText: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: THEME.colors.destructive,
    flex: 1,
  },
});
