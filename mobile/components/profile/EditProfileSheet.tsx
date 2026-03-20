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

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  ERROR_DARK,
  COLORS,
} from "../../constants/colors";
import {
  IMAGE_PICKER as IMAGE_PICKER_CONFIG,
  MIN_TOUCH_TARGET,
  PROFILE_CONFIG,
} from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import type { UserProfile, UpdateProfilePayload } from "./types";

const AVATAR_SIZE = 80;
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
                styles.headerButton,
                (!isDisplayNameValid || isUpdating) &&
                  styles.headerButtonDisabled,
              ]}
              accessibilityLabel="Save profile changes"
              accessibilityRole="button"
              accessibilityState={{ disabled: isUpdating || !isDisplayNameValid }}
            >
              <Text
                style={[
                  styles.saveText,
                  { color: theme.accent },
                  (!isDisplayNameValid || isUpdating) &&
                    styles.saveTextDisabled,
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
                  color="#888888"
                />
              </View>
            )}
            <View style={[styles.avatarBadge, { backgroundColor: theme.accent }]}>
              <Ionicons name="camera" size={14} color="#0a0a0a" />
            </View>
          </Pressable>
          <Text style={styles.avatarHint}>Tap to change photo</Text>

          {/* Display name input */}
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>Display Name</Text>
            <TextInput
              value={displayName}
              onChangeText={handleDisplayNameChange}
              style={styles.input}
              placeholderTextColor="#555555"
              placeholder="Your display name"
              maxLength={PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH}
              autoCapitalize="words"
              returnKeyType="done"
              accessibilityLabel="Display name"
            />
            <Text style={styles.charCount}>
              {displayName.length}/{PROFILE_CONFIG.DISPLAY_NAME_MAX_LENGTH}
            </Text>
          </View>

          {/* Error message */}
          {updateError ? (
            <View style={styles.errorContainer}>
              <Ionicons
                name="alert-circle"
                size={16}
                color={ERROR_DARK}
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
    backgroundColor: "#0a0a0a",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingBottom: 16,
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: "rgba(255,255,255,0.12)",
    alignSelf: "center",
    marginTop: 8,
    marginBottom: 8,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 8,
    minHeight: MIN_TOUCH_TARGET,
  },
  headerButton: {
    minWidth: 60,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  headerButtonDisabled: {
    opacity: 0.4,
  },
  headerTitle: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 17,
    color: "#e8e8e8",
  },
  cancelText: {
    fontFamily: FONTS.body,
    fontSize: 16,
    color: "#888888",
  },
  saveText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 16,
    textAlign: "right",
  },
  saveTextDisabled: {
    color: "#555555",
  },
  avatarPicker: {
    alignSelf: "center",
    marginTop: 16,
    position: "relative",
  },
  avatar: {
    width: AVATAR_SIZE,
    height: AVATAR_SIZE,
    borderRadius: AVATAR_SIZE / 2,
  },
  avatarPlaceholder: {
    backgroundColor: "#111111",
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarBadge: {
    position: "absolute",
    bottom: 0,
    right: 0,
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 2,
    borderColor: "#0a0a0a",
  },
  avatarHint: {
    fontFamily: FONTS.body,
    fontSize: 13,
    color: "#888888",
    textAlign: "center",
    marginTop: 8,
    marginBottom: 24,
  },
  fieldContainer: {
    paddingHorizontal: 16,
    marginBottom: 16,
  },
  fieldLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 13,
    color: "#888888",
    marginBottom: 6,
    textTransform: "uppercase",
    letterSpacing: 0.5,
  },
  input: {
    fontFamily: FONTS.body,
    backgroundColor: "rgba(255,255,255,0.05)",
    borderRadius: 12,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.06)",
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: "#e8e8e8",
    minHeight: MIN_TOUCH_TARGET,
  },
  charCount: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: "#555555",
    textAlign: "right",
    marginTop: 4,
  },
  errorContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 16,
    marginTop: 8,
  },
  errorText: {
    fontFamily: FONTS.body,
    fontSize: 14,
    color: ERROR_DARK,
    flex: 1,
  },
});
