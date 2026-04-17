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
  ActivityIndicator,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as ImagePicker from "expo-image-picker";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import {
  AUTH_VALIDATION,
  IMAGE_PICKER as IMAGE_PICKER_CONFIG,
  MIN_TOUCH_TARGET,
  PROFILE_CONFIG,
} from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import { apiFetch } from "../../lib/api";
import type { UserProfile, UpdateProfilePayload } from "./types";

const AVATAR_SIZE = 88;
const SHEET_ENTER_DURATION_MS = 300;
const SHEET_EXIT_DURATION_MS = 200;
const AVAILABILITY_CHECK_DEBOUNCE_MS = 300;
/** Green checkmark for available username — not in THEME, defined here */
const COLOR_SUCCESS = "#22c55e";

interface EditProfileSheetProps {
  visible: boolean;
  profile: UserProfile;
  isUpdating: boolean;
  updateError: string | null;
  onSave: (payload: UpdateProfilePayload) => Promise<boolean>;
  /**
   * Upload a freshly-picked avatar (ImagePicker URI) to the backend. Fires
   * before onSave so the PATCH in onSave doesn't need to know about the
   * storage-key round-trip.
   */
  onUploadAvatar: (uri: string) => Promise<boolean>;
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
  onUploadAvatar,
  onClose,
}: EditProfileSheetProps) {
  const { theme } = useTheme();
  const insets = useSafeAreaInsets();
  const [displayName, setDisplayName] = useState(
    profile.display_name ?? "",
  );
  const [avatarUri, setAvatarUri] = useState(profile.avatar_url ?? "");
  /**
   * Local file URI from expo-image-picker when the user picks a new avatar.
   * Null until the picker fires for this sheet session. Distinct from
   * `avatarUri` (which also shows the remote signed URL) because only local
   * picks should be uploaded — tapping Save without picking must not POST.
   */
  const [avatarPickedUri, setAvatarPickedUri] = useState<string | null>(null);
  const [newUsername, setNewUsername] = useState(profile.username ?? "");
  const [usernameAvailable, setUsernameAvailable] = useState<boolean | null>(null);
  const [usernameChecking, setUsernameChecking] = useState(false);
  const [usernameError, setUsernameError] = useState<string | null>(null);

  const slideAnim = useRef(new Animated.Value(0)).current;
  const scrimAnim = useRef(new Animated.Value(0)).current;
  const cancelButtonRef = useRef<React.ElementRef<typeof Pressable>>(null);

  // Reset form when profile changes or sheet opens
  useEffect(() => {
    if (visible) {
      setDisplayName(profile.display_name ?? "");
      setAvatarUri(profile.avatar_url ?? "");
      setAvatarPickedUri(null);
      setNewUsername(profile.username ?? "");
      setUsernameAvailable(null);
      setUsernameError(null);

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

  // Debounced username validation + availability check.
  //
  // Validation is deferred — the old flow marked the field invalid
  // synchronously on every keystroke, so backspacing an existing name
  // to 2 chars flashed red before the user could finish editing. Now:
  //   1. Any change → enter "checking" state, clear error + availability.
  //      Spinner in `usernameStatus` shows while the user types.
  //   2. After AVAILABILITY_CHECK_DEBOUNCE_MS of quiet, run the local
  //      format/length check. If it fails, surface the error.
  //   3. Only if the format check passes do we hit the server.
  //
  // Alignment with the backend:
  //   - Backend stores usernames case-sensitively but enforces
  //     uniqueness via `ILIKE` (case-insensitive). The public
  //     `/users/check-username` endpoint has no auth, so it does NOT
  //     exclude the caller's own row — a case variant of the user's
  //     existing name would come back as "taken". We compare
  //     case-insensitively before hitting the server so typing
  //     "VladTrifonov" when the stored value is "vladtrifonov" is
  //     treated as a no-op (the PATCH endpoint DOES exclude self and
  //     will apply the case change on save).
  //   - Partial values never reach the server because we only fire
  //     /check-username after format + length pass locally (backend
  //     Query min_length=3 would 422 otherwise).
  useEffect(() => {
    const currentUsername = profile.username ?? "";
    if (newUsername.toLowerCase() === currentUsername.toLowerCase()) {
      setUsernameAvailable(null);
      setUsernameError(null);
      setUsernameChecking(false);
      return;
    }

    setUsernameChecking(true);
    setUsernameAvailable(null);
    setUsernameError(null);

    // Abort controller so a rapid-keystroke sequence cannot let an
    // in-flight stale response overwrite state that has since moved on
    // to the newer input. Aborting the fetch ALSO skips the setters via
    // the AbortError branch below.
    const controller = new AbortController();
    const timeout = setTimeout(async () => {
      if (controller.signal.aborted) return;
      if (
        newUsername.length < AUTH_VALIDATION.USERNAME_MIN_LENGTH ||
        newUsername.length > AUTH_VALIDATION.USERNAME_MAX_LENGTH ||
        !AUTH_VALIDATION.USERNAME_PATTERN.test(newUsername)
      ) {
        setUsernameAvailable(false);
        setUsernameError(
          `${AUTH_VALIDATION.USERNAME_MIN_LENGTH}-${AUTH_VALIDATION.USERNAME_MAX_LENGTH} chars, starts with letter, letters/numbers/underscores only`,
        );
        setUsernameChecking(false);
        return;
      }

      try {
        const resp = await apiFetch<{ available: boolean; reason?: string }>(
          `/v1/users/check-username?username=${encodeURIComponent(newUsername)}`,
          { signal: controller.signal },
        );
        if (controller.signal.aborted) return;
        setUsernameAvailable(resp.available);
        setUsernameError(
          resp.available
            ? null
            : resp.reason === "reserved"
              ? "Username is reserved"
              : "Username is taken",
        );
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof Error && err.name === "AbortError") return;
        setUsernameError(null);
        setUsernameAvailable(null);
      } finally {
        if (!controller.signal.aborted) setUsernameChecking(false);
      }
    }, AVAILABILITY_CHECK_DEBOUNCE_MS);

    return () => {
      clearTimeout(timeout);
      controller.abort();
    };
  }, [newUsername, profile.username]);

  // Computed change tracking — `hasUsernameChange` stays a strict
  // comparison so a case-only change ("vlad" → "Vlad") still submits
  // the PATCH; only the uniqueness branches below normalize case.
  const currentUsername = profile.username ?? "";
  const hasUsernameChange = newUsername !== currentUsername;
  const hasDisplayNameChange = displayName !== (profile.display_name ?? "");
  const hasAvatarChange = avatarPickedUri !== null;
  const hasChanges =
    hasUsernameChange || hasDisplayNameChange || hasAvatarChange;

  // Username validation
  //
  // A changed username is only "valid" when the server has confirmed it's
  // available (`usernameAvailable === true`). The old check used
  // `usernameAvailable !== false`, which treated `null` (not yet checked)
  // as valid — so Save lit up during the 300 ms debounce window and the
  // user could race-tap it into a 409 on a taken name. Require an explicit
  // `true` for the changed-name branch.
  //
  // Case handling: the same-name short-circuit is case-insensitive so a
  // user editing only the letter case of their own username keeps Save
  // enabled (the backend PATCH handler does exclude self when checking
  // availability). The /check-username endpoint cannot do that exclusion
  // — it's unauthenticated — which is why we match locally instead of
  // relying on a round-trip.
  const isUsernameValid =
    newUsername.toLowerCase() === currentUsername.toLowerCase() ||
    (newUsername.length >= AUTH_VALIDATION.USERNAME_MIN_LENGTH &&
      newUsername.length <= AUTH_VALIDATION.USERNAME_MAX_LENGTH &&
      AUTH_VALIDATION.USERNAME_PATTERN.test(newUsername) &&
      usernameAvailable === true);

  const isCooldownActive =
    (profile.username_change_cooldown_remaining_seconds ?? 0) > 0;

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

  const handleDisplayNameChange = useCallback((text: string) => {
    setDisplayName(text);
  }, []);

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
      setAvatarPickedUri(newUri);
    }
  }, []);

  const doSave = useCallback(
    async (
      payload: UpdateProfilePayload,
      uploadUri: string | null,
    ) => {
      // Upload the picked avatar FIRST so a later PATCH failure doesn't leave
      // the photo unsaved. The avatar endpoint already returns the refreshed
      // UpdateProfileResponse, so the hook merges it into profile state
      // regardless of whether we then PATCH other fields.
      if (uploadUri) {
        const uploaded = await onUploadAvatar(uploadUri);
        if (!uploaded) return;
      }
      if (Object.keys(payload).length > 0) {
        const saved = await onSave(payload);
        if (!saved) return;
      }
      animateClose(onClose);
    },
    [onSave, onUploadAvatar, animateClose, onClose],
  );

  const handleSave = useCallback(async () => {
    const payload: UpdateProfilePayload = {};

    if (hasDisplayNameChange) {
      payload.display_name = displayName.trim();
    }
    if (hasUsernameChange) {
      payload.new_username = newUsername.trim();
    }

    const uploadUri = hasAvatarChange ? avatarPickedUri : null;

    if (Object.keys(payload).length === 0 && uploadUri === null) {
      animateClose(onClose);
      return;
    }

    // Warn about broken links if username changes
    if (hasUsernameChange) {
      Alert.alert(
        "Change username?",
        "Changing your username will break any links you've shared with your current username.",
        [
          { text: "Cancel", style: "cancel" },
          { text: "Change", onPress: () => doSave(payload, uploadUri) },
        ],
      );
      return;
    }

    await doSave(payload, uploadUri);
  }, [
    displayName,
    newUsername,
    hasDisplayNameChange,
    hasUsernameChange,
    hasAvatarChange,
    avatarPickedUri,
    doSave,
    animateClose,
    onClose,
  ]);

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
            {
              transform: [{ translateY }],
              paddingBottom: Math.max(insets.bottom, THEME.spacing.xxl),
            },
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
              disabled={isUpdating || !isDisplayNameValid || !isUsernameValid}
              style={[
                styles.saveButton,
                { backgroundColor: theme.accent },
                (!isDisplayNameValid || !isUsernameValid || isUpdating) &&
                  styles.saveButtonDisabled,
              ]}
              accessibilityLabel="Save profile changes"
              accessibilityRole="button"
              accessibilityState={{
                disabled: isUpdating || !isDisplayNameValid || !isUsernameValid,
              }}
            >
              <Text
                style={[
                  styles.saveButtonText,
                  (!isDisplayNameValid || !isUsernameValid || isUpdating) &&
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

          {/* Username input */}
          <View style={styles.fieldContainer}>
            <Text style={styles.fieldLabel}>USERNAME</Text>
            <View style={styles.usernameInputRow}>
              <Text style={styles.usernamePrefix}>@</Text>
              <TextInput
                value={newUsername}
                onChangeText={setNewUsername}
                style={[styles.input, styles.usernameInput]}
                placeholderTextColor={THEME.colors.textMuted}
                placeholder="username"
                maxLength={AUTH_VALIDATION.USERNAME_MAX_LENGTH}
                autoCapitalize="none"
                autoCorrect={false}
                returnKeyType="next"
                editable={!isCooldownActive}
                accessibilityLabel="Username"
              />
              {/* Availability indicator — hidden when the value only
                  differs by case, since the effect short-circuits that
                  branch (no server call, no verdict to show). */}
              {newUsername.toLowerCase() !== currentUsername.toLowerCase() && (
                <View style={styles.usernameStatus}>
                  {usernameChecking ? (
                    <ActivityIndicator
                      size="small"
                      color={THEME.colors.textMuted}
                    />
                  ) : usernameAvailable === true ? (
                    <Ionicons
                      name="checkmark-circle"
                      size={20}
                      color={COLOR_SUCCESS}
                    />
                  ) : usernameAvailable === false ? (
                    <Ionicons
                      name="close-circle"
                      size={20}
                      color={THEME.colors.destructive}
                    />
                  ) : null}
                </View>
              )}
            </View>
            {usernameError ? (
              <Text style={styles.usernameErrorText}>{usernameError}</Text>
            ) : isCooldownActive ? (
              <Text style={styles.cooldownHint}>
                You can change your username again later
              </Text>
            ) : null}
          </View>

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
    minHeight: MIN_TOUCH_TARGET,
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
  usernameInputRow: {
    flexDirection: "row",
    alignItems: "center",
  },
  usernamePrefix: {
    fontFamily: FONTS.body,
    fontSize: 16,
    color: THEME.colors.textSecondary,
    marginRight: THEME.spacing.xs,
  },
  usernameInput: {
    flex: 1,
  },
  usernameStatus: {
    marginLeft: THEME.spacing.sm,
    width: 24,
    alignItems: "center",
  },
  usernameErrorText: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.destructive,
    marginTop: THEME.spacing.xs,
  },
  cooldownHint: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
    marginTop: THEME.spacing.xs,
  },
});
