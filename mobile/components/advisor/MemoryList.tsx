/**
 * MemoryList — user memories with add and swipe-to-delete.
 *
 * Mirrors ChatView's layout: list fills the tab, composer sits at the
 * bottom of the screen, KeyboardAvoidingView lifts the composer with
 * the keyboard, and the floating tab-bar is cleared via bottomPadding.
 * The Goals / Notes subtabs sit at the top as a list filter — each tab
 * has its own draft, error, and isAdding state so submitting on one
 * never locks the other. The actual input is the shared AdvisorComposer
 * at the bottom, bound to the active tab's draft.
 *
 * Memories are things Ada remembers about the user: goals, notes,
 * accepted suggestions, etc. The Goals / Notes tabs only show
 * user-authored rows; system-authored insights / accepted /
 * dismissed suggestions are hidden via a server-side type filter.
 * Swipe left on a row to reveal delete.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  FlatList,
  Text,
  Pressable,
  Alert,
  Animated,
  ActivityIndicator,
  Platform,
  StyleSheet,
  PanResponder,
} from "react-native";
import { KeyboardAvoidingView } from "react-native-keyboard-controller";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { showToast } from "../../lib/toast";
import { hapticLight } from "../../lib/haptics";
import { ADVISOR_CONFIG, MIN_TOUCH_TARGET } from "../../constants/config";
import { useAdvisorComposerLayout } from "../../hooks/useAdvisorComposerLayout";
import { fetchMemories, addMemory, deleteMemory } from "../../lib/advisor";
import type { UserMemory } from "../../lib/advisor";
import { AdvisorComposer } from "./AdvisorComposer";
import { AdvisorEmptyOverlay } from "./AdvisorEmptyOverlay";
import { MemoryDetailSheet } from "./MemoryDetailSheet";
import { memoryContentText, memoryTypeIcon } from "./memory-helpers";
import { PressableScale } from "../ui/PressableScale";
import { Caption } from "../ui/Text";

const DELETE_BUTTON_WIDTH = 80;
// Position past which a release commits to the open state. iOS Mail
// uses ~50% of the action width as the snap point, with velocity able
// to override.
const SWIPE_OPEN_POSITION_THRESHOLD = -DELETE_BUTTON_WIDTH / 2;
// |vx| past which a flick commits open/closed regardless of position.
// Picked to match iOS Mail-style flicks: a slow drag uses position,
// a quick wrist flick wins on velocity. Units are points-per-ms from
// PanResponder.
const SWIPE_VELOCITY_THRESHOLD = 0.3;
// Visual position at which we fire the open/close edge haptic. Set
// to 70% of fully-open so the tick lands when the user can SEE the
// trash button is mostly revealed — matches Mail's perceived "click".
const SWIPE_HAPTIC_THRESHOLD = -DELETE_BUTTON_WIDTH * 0.7;
// Min |dx| before claiming the responder. Lowered slightly from the
// previous 10pt so the gesture feels more responsive without
// stealing vertical scrolls.
const SWIPE_RESPONDER_THRESHOLD = 8;
// Spring config for snap and reset animations. Tension 100 + friction
// 14 hits a quick, slightly underdamped settle that reads as
// responsive without overshoot. Velocity from gestureState.vx is
// passed in so a release-flick continues into the snap smoothly.
const SWIPE_SPRING_TENSION = 100;
const SWIPE_SPRING_FRICTION = 14;
// Exit animation when the user confirms delete in the Alert. Slides
// the row off-screen left while fading, then the parent removes it
// from the list.
const DELETE_EXIT_DURATION_MS = 220;
const DELETE_EXIT_TRANSLATE_X = -400;

// ---------------------------------------------------------------------------
// SwipeableMemoryRow
// ---------------------------------------------------------------------------

interface SwipeableRowProps {
  memory: UserMemory;
  /**
   * Trash-button intent. The row stays in its currently-open swipe
   * position (does NOT animate away yet) — the parent shows the
   * confirmation Alert and only commits removal after the user picks
   * "Delete". The exit animation is then driven by ``isPendingDelete``.
   */
  onDelete: (id: string) => void;
  /**
   * Whether THIS row is the currently-open one (trash button revealed).
   * MemoryList tracks the single open id; flipping this to false
   * triggers the row to spring back to the resting position so taps on
   * other rows / chrome / a sibling row's swipe close the open row
   * automatically.
   */
  isOpen: boolean;
  /** Notify parent that this row opened (id) or closed (null). */
  onOpenChange: (id: string | null) => void;
  /**
   * Parent has confirmed deletion via the Alert. The row plays its
   * exit animation (slide off left + fade), then fires
   * ``onExitAnimationComplete`` — at which point the parent removes
   * the row from ``memories``. Decoupling animation from removal lets
   * us keep the row visible during the Alert (so the user is not
   * staring at empty space while they confirm) and gives the removal
   * the polish of a Mail-style sweep instead of a hard pop.
   */
  isPendingDelete: boolean;
  onExitAnimationComplete: (id: string) => void;
  /**
   * Tap on a closed row opens the detail modal (full content, no
   * truncation). Tap on an open row closes the swipe instead of
   * opening detail — prevents a stray tap on the revealed trash
   * button's card region from stacking modal + open row.
   */
  onOpenDetail: (memory: UserMemory) => void;
}

/**
 * Single memory row with swipe-to-delete. The left icon container is
 * the only visual cue for the row's type — the textual label was
 * dropped because each tab's content is uniform, so the label was
 * redundant chrome.
 *
 * Open state is lifted to ``MemoryList`` so only one row can be open
 * at a time and taps anywhere else (sibling row, subtabs, list
 * background) close it.
 */
function SwipeableMemoryRow({
  memory,
  onDelete,
  isOpen,
  onOpenChange,
  isPendingDelete,
  onExitAnimationComplete,
  onOpenDetail,
}: SwipeableRowProps) {
  const { theme } = useTheme();
  const translateX = useRef(new Animated.Value(0)).current;
  const opacity = useRef(new Animated.Value(1)).current;

  // Mirror the controlled ``isOpen`` prop in a ref so the
  // PanResponder closures (created once on mount) always see the
  // current state when computing the gesture's starting offset and
  // the haptic edge crossing. A ref is appropriate here because the
  // PanResponder must NOT be recreated on every prop change — that
  // would cancel an in-flight gesture mid-swipe.
  const isOpenRef = useRef(isOpen);
  // The current visual translateX (after offset + delta), tracked in
  // a ref so the release handler can decide open/close based on the
  // last on-screen position rather than reading from the Animated
  // node (which is on the native side when useNativeDriver is true).
  const lastValueRef = useRef(0);
  // Edge-detect for the haptic tick — true while the row is past the
  // SWIPE_HAPTIC_THRESHOLD position. Flipping this drives one tick
  // per crossing (open and re-close both feel a tick).
  const crossedThresholdRef = useRef(false);

  // When the parent flips isOpen to false (another row opened, or a
  // tap-outside fired), spring the trash button back behind the card.
  // Skipping the initial mount keeps the animation from firing on the
  // very first render of every row.
  const didMountRef = useRef(false);
  useEffect(() => {
    if (!didMountRef.current) {
      didMountRef.current = true;
      isOpenRef.current = isOpen;
      crossedThresholdRef.current = isOpen;
      return;
    }
    // Only animate a close — open is driven by the gesture itself,
    // and the parent setting isOpen=true mid-gesture would fight the
    // user's finger.
    if (!isOpen && isOpenRef.current) {
      isOpenRef.current = false;
      crossedThresholdRef.current = false;
      lastValueRef.current = 0;
      Animated.spring(translateX, {
        toValue: 0,
        useNativeDriver: true,
        tension: SWIPE_SPRING_TENSION,
        friction: SWIPE_SPRING_FRICTION,
      }).start();
    }
  }, [isOpen, translateX]);

  // Refs mirror props that are read from inside PanResponder
  // closures (created once on mount — the closures would otherwise
  // see stale values on re-render). `memoryRef` is defensive; in
  // practice FlatList's keyExtractor keeps identity per row, but
  // reading through a ref makes the contract explicit.
  const onExitDoneRef = useRef(onExitAnimationComplete);
  onExitDoneRef.current = onExitAnimationComplete;
  // Mirror memory + onOpenChange for the PanResponder closure. The
  // snap path reads `memory.id` and calls `onOpenChange(...)` after a
  // swipe settles; without refs the once-created closure would fire
  // against stale props after any parent re-render.
  const memoryRef = useRef(memory);
  memoryRef.current = memory;
  const onOpenChangeRef = useRef(onOpenChange);
  onOpenChangeRef.current = onOpenChange;

  // Confirmed-delete exit animation — slides the card off-screen
  // left while fading out. On completion the parent removes the
  // memory from the list. Kept as Animated.parallel so both
  // properties land at the same instant for a clean sweep.
  useEffect(() => {
    if (!isPendingDelete) return;
    Animated.parallel([
      Animated.timing(translateX, {
        toValue: DELETE_EXIT_TRANSLATE_X,
        duration: DELETE_EXIT_DURATION_MS,
        useNativeDriver: true,
      }),
      Animated.timing(opacity, {
        toValue: 0,
        duration: DELETE_EXIT_DURATION_MS,
        useNativeDriver: true,
      }),
    ]).start(({ finished }) => {
      if (finished) onExitDoneRef.current(memory.id);
    });
  }, [isPendingDelete, memory.id, opacity, translateX]);

  // PanResponder is created once on mount. All mutable state it needs
  // is held in refs (isOpenRef, lastValueRef, crossedThresholdRef) so
  // the closures see live values without forcing a recreate that
  // would cancel an in-flight gesture.
  //
  // Coexistence with a tap Pressable wrapping the card:
  //   - Tap (no movement) stays with the Pressable — PanResponder
  //     never claims. `handleTap` opens the detail modal.
  //   - Horizontal swipe — PanResponder steals the responder from
  //     Pressable via the capture-phase move check. Pressable sees
  //     its press cancelled, onPress doesn't fire, swipe proceeds.
  //     This is the documented RN idiom for combining the two and
  //     avoids the #144/#145 regression where Pressable winning at
  //     touch-start killed the swipe (with capture-phase we win
  //     back once movement is clearly horizontal).
  //   - Vertical scroll — neither capture nor non-capture move
  //     claims; FlatList scrolls normally.
  //
  // Issue #6 (vertical drift mid-swipe would terminate): handled by
  // `onPanResponderTerminationRequest: () => false` and
  // `onShouldBlockNativeResponder: () => true`. Both only take
  // effect once PanResponder has already won via a horizontal move,
  // so vertical scroll before claim stays unaffected.
  const horizontalMoveClaim = (
    _: unknown,
    gesture: { dx: number; dy: number },
  ) => {
    // Defensive: a NaN dx slipping past the comparison would
    // cascade into translateX.setValue(NaN) below and surface
    // as a CoreGraphics "invalid numeric value" warning on iOS.
    if (!Number.isFinite(gesture.dx) || !Number.isFinite(gesture.dy)) {
      return false;
    }
    // Bias slightly toward horizontal so the FlatList still wins
    // diagonal-ish drags.
    return (
      Math.abs(gesture.dx) > SWIPE_RESPONDER_THRESHOLD &&
      Math.abs(gesture.dx) > Math.abs(gesture.dy) * 1.2
    );
  };
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onStartShouldSetPanResponderCapture: () => false,
      // Capture-phase move claim — lets PanResponder steal the
      // responder from a child Pressable on clear horizontal drags.
      onMoveShouldSetPanResponderCapture: horizontalMoveClaim,
      onMoveShouldSetPanResponder: horizontalMoveClaim,
      // Once we hold the responder, don't give it back. Previously
      // a mid-swipe vertical drift let FlatList's native scroll
      // reclaim, firing onPanResponderTerminate → row auto-closed.
      onPanResponderTerminationRequest: () => false,
      onShouldBlockNativeResponder: () => true,
      onPanResponderGrant: () => {
        // Anchor future deltas to the row's current on-screen
        // position. With setOffset, dx during the move is interpreted
        // relative to the start, so an already-open row swiped
        // further left rubber-bands cleanly without snapping to
        // wherever dx happens to land first.
        const startX = isOpenRef.current ? -DELETE_BUTTON_WIDTH : 0;
        translateX.setOffset(startX);
        translateX.setValue(0);
        lastValueRef.current = startX;
        crossedThresholdRef.current = isOpenRef.current;
      },
      onPanResponderMove: (_, gesture) => {
        if (!Number.isFinite(gesture.dx)) return;
        const startX = isOpenRef.current ? -DELETE_BUTTON_WIDTH : 0;
        // Hard clamp to [-DELETE_BUTTON_WIDTH, 0]. Rubber-band past
        // the open position would reveal background between the card's
        // right edge and the trash button's left edge — the user
        // reads that as the card "disconnecting" from the button.
        // Clamping keeps the two glued throughout the gesture.
        const absoluteX = Math.min(
          0,
          Math.max(-DELETE_BUTTON_WIDTH, startX + gesture.dx),
        );
        const delta = absoluteX - startX;

        translateX.setValue(delta);
        const newAbs = absoluteX;
        lastValueRef.current = newAbs;

        // One haptic tick per threshold crossing in either direction.
        const nowCrossed = newAbs < SWIPE_HAPTIC_THRESHOLD;
        if (nowCrossed !== crossedThresholdRef.current) {
          crossedThresholdRef.current = nowCrossed;
          void hapticLight();
        }
      },
      onPanResponderRelease: (_, gesture) => {
        translateX.flattenOffset();
        // PanResponder reports vx in points/ms; SWIPE_VELOCITY_THRESHOLD
        // is in the same unit. Animated.spring's `velocity` option,
        // however, is in points/SECOND, so we scale by 1000 when
        // handing it to the spring to keep the release flick visually
        // continuous instead of being dominated by the spring's own
        // initial impulse.
        const vxPerMs = Number.isFinite(gesture.vx) ? gesture.vx : 0;
        const finalX = lastValueRef.current;

        // Velocity wins: a quick flick commits the direction even
        // when finger position hasn't crossed the position
        // threshold yet (matches iOS Mail). Otherwise fall back to
        // position-based snap.
        let willOpen: boolean;
        if (vxPerMs < -SWIPE_VELOCITY_THRESHOLD) {
          willOpen = true;
        } else if (vxPerMs > SWIPE_VELOCITY_THRESHOLD) {
          willOpen = false;
        } else {
          willOpen = finalX < SWIPE_OPEN_POSITION_THRESHOLD;
        }

        Animated.spring(translateX, {
          toValue: willOpen ? -DELETE_BUTTON_WIDTH : 0,
          velocity: vxPerMs * 1000,
          useNativeDriver: true,
          tension: SWIPE_SPRING_TENSION,
          friction: SWIPE_SPRING_FRICTION,
        }).start();
        isOpenRef.current = willOpen;
        lastValueRef.current = willOpen ? -DELETE_BUTTON_WIDTH : 0;
        // Sync local edge-detect to the committed position so the
        // next gesture starts from the right haptic state.
        crossedThresholdRef.current = willOpen;
        onOpenChangeRef.current(willOpen ? memoryRef.current.id : null);
      },
      onPanResponderTerminate: () => {
        // Another responder (e.g. the parent FlatList scroll) won
        // mid-gesture. Settle the offset back into the value and
        // snap to the prior committed state without firing the open
        // change, so we don't leave the row half-swiped.
        translateX.flattenOffset();
        const target = isOpenRef.current ? -DELETE_BUTTON_WIDTH : 0;
        Animated.spring(translateX, {
          toValue: target,
          useNativeDriver: true,
          tension: SWIPE_SPRING_TENSION,
          friction: SWIPE_SPRING_FRICTION,
        }).start();
        lastValueRef.current = target;
        crossedThresholdRef.current = isOpenRef.current;
      },
    }),
  ).current;

  // Trash-button tap. We DO NOT animate the row away here — that
  // would slide the card off-screen before the user has confirmed
  // and leave them staring at empty space (or worse, at a dangling
  // trash button) while the confirmation Alert is up. Instead just
  // notify the parent of the intent; the row holds its open
  // position. The parent shows the Alert and, on confirm, flips
  // ``isPendingDelete`` to drive the exit animation.
  const handleDelete = useCallback(() => {
    onDelete(memory.id);
  }, [memory.id, onDelete]);

  // Tap handler — used by the Pressable wrapping the card. A tap on
  // an open row closes the swipe (rather than opening detail), so
  // users don't stack the detail modal over a revealed trash button.
  // A tap on a closed row opens the detail sheet.
  const handleTap = useCallback(() => {
    if (isOpenRef.current) {
      isOpenRef.current = false;
      crossedThresholdRef.current = false;
      lastValueRef.current = 0;
      Animated.spring(translateX, {
        toValue: 0,
        useNativeDriver: true,
        tension: SWIPE_SPRING_TENSION,
        friction: SWIPE_SPRING_FRICTION,
      }).start();
      onOpenChange(null);
      return;
    }
    onOpenDetail(memory);
  }, [memory, onOpenChange, onOpenDetail, translateX]);

  const dateStr = new Date(memory.created_at).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });

  // Wrapping the inner card in a Pressable is safe now that
  // PanResponder uses `onMoveShouldSetPanResponderCapture`: the
  // Pressable wins at touch-start (so taps fire onPress), but as
  // soon as the user drags horizontally past SWIPE_RESPONDER_THRESHOLD
  // PanResponder captures the responder back and the swipe proceeds.
  // Vertical drags never trigger the capture claim, so FlatList's
  // native pan keeps scrolling the list.
  //
  // Exit-animation wrapper stays an Animated.View so the trash
  // button AND card fade together. Tap-outside-close (open row closed
  // by a tap elsewhere in the list) is still handled in MemoryList.
  const previewText = memoryContentText(memory.content);
  return (
    <Animated.View style={[rowStyles.wrapper, { opacity }]}>
      <View style={rowStyles.deleteContainer}>
        <Pressable
          onPress={handleDelete}
          style={rowStyles.deleteButton}
          accessibilityLabel={`Delete memory: ${previewText}`}
          accessibilityRole="button"
        >
          <Ionicons name="trash-outline" size={22} color={THEME.colors.white} />
        </Pressable>
      </View>

      <Animated.View
        style={[rowStyles.card, { transform: [{ translateX }] }]}
        {...panResponder.panHandlers}
      >
        <Pressable
          onPress={handleTap}
          style={rowStyles.cardPressable}
          accessibilityLabel={`Open memory: ${previewText}`}
          accessibilityRole="button"
          accessibilityHint="Shows the full content of this memory"
        >
          <View style={[rowStyles.iconContainer, { backgroundColor: theme.accentMuted }]}>
            <Ionicons
              name={memoryTypeIcon(memory.type)}
              size={20}
              color={theme.accent}
            />
          </View>
          <View style={rowStyles.content}>
            <Text style={rowStyles.body} numberOfLines={3}>
              {previewText}
            </Text>
            <Text style={rowStyles.date}>{dateStr}</Text>
          </View>
        </Pressable>
      </Animated.View>
    </Animated.View>
  );
}

const rowStyles = StyleSheet.create({
  wrapper: {
    // overflow:hidden + borderRadius:lg clips the card+button composite
    // to a single rounded shape. The card's right corners and the
    // trash button's left corners are intentionally SQUARE (see styles
    // below) so the seam between them at the swiped position is a
    // clean vertical line — the card and the button read as one
    // continuous control split in two, not as two separate pills.
    position: "relative",
    overflow: "hidden",
    borderRadius: THEME.radius.lg,
  },
  deleteContainer: {
    // Anchor to the right edge with a fixed width and stretch the
    // child via flex instead of `height: "100%"`. Percentage heights
    // resolve to NaN on iOS during the first layout pass when the
    // parent's measured height is briefly undefined, surfacing as
    // CoreGraphics "invalid numeric value" warnings.
    position: "absolute",
    top: 0,
    bottom: 0,
    right: 0,
    width: DELETE_BUTTON_WIDTH,
    alignItems: "stretch",
    justifyContent: "center",
  },
  deleteButton: {
    // Square left corners so the button merges flush with the card's
    // square right corners. The wrapper's overflow:hidden clips the
    // outer right edge to match the wrapper's borderRadius.
    flex: 1,
    backgroundColor: THEME.colors.destructive,
    alignItems: "center",
    justifyContent: "center",
  },
  // The Pressable inside the card holds the tap handler. It has to
  // stretch to the card's full interior so taps on icon/body/date
  // all register, and it reproduces the card's flex layout because
  // the Animated.View outside now only provides the translate
  // transform + PanResponder handlers.
  cardPressable: {
    flex: 1,
    flexDirection: "row",
    gap: THEME.spacing.md,
  },
  card: {
    // Square right corners for the same merge. The outer left corners
    // get rounded by the wrapper's clip.
    flexDirection: "row",
    backgroundColor: THEME.colors.glass,
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
// SubTabs — Goals / Notes switcher. Filters the list and binds the
// composer to the active tab's draft. Styled as a chip pair to match
// the rest of the advisor surface; semantically a tablist for VoiceOver.
// ---------------------------------------------------------------------------

/** Tab values double as the server-side type filter (`?type=goal|user_note`). */
type Tab = "goal" | "user_note";

const SUB_TABS: { value: Tab; label: string }[] = [
  { value: "goal", label: "Goals" },
  { value: "user_note", label: "Notes" },
];

interface SubTabsProps {
  activeTab: Tab;
  onChange: (tab: Tab) => void;
}

function SubTabs({ activeTab, onChange }: SubTabsProps) {
  const { theme } = useTheme();
  return (
    <View style={chipStyles.row} accessibilityRole="tablist">
      {SUB_TABS.map((t) => {
        const isActive = activeTab === t.value;
        return (
          <PressableScale
            key={t.value}
            scale={0.94}
            haptic={false}
            onPress={() => onChange(t.value)}
            style={[
              chipStyles.chip,
              isActive && {
                backgroundColor: theme.accent + "1A",
                borderColor: theme.accent,
                ...THEME.shadow.glow(theme.accent),
              },
            ]}
            accessibilityLabel={t.label}
            accessibilityRole="tab"
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

// ---------------------------------------------------------------------------
// Per-tab copy — kept in one place so SubTabs, composer, and empty
// overlay all read from the same source of truth.
// ---------------------------------------------------------------------------

interface TabCopy {
  placeholder: string;
  composerA11yLabel: string;
  emptyTitle: string;
  emptyDescription: string;
}

const TAB_COPY: Record<Tab, TabCopy> = {
  goal: {
    // Kept pithy — the old copy wrapped to two lines inside the
    // composer input on the standard iPhone width, which reads as
    // a broken multi-line field.
    placeholder: "e.g. Grow my hair out",
    composerA11yLabel: "Goal content",
    emptyTitle: "No goals yet",
    emptyDescription: "Tell Ada what you're working toward.",
  },
  user_note: {
    placeholder: "e.g. I prefer minimal jewelry",
    composerA11yLabel: "Note content",
    emptyTitle: "No notes yet",
    emptyDescription: "Jot anything Ada should know about you.",
  },
};

/** First tab shown on mount. Persists within session via `activeTab` state. */
const DEFAULT_TAB: Tab = "goal";

interface TabState {
  draft: string;
  error: string | null;
  isAdding: boolean;
}

const INITIAL_TAB_STATE: TabState = { draft: "", error: null, isAdding: false };

export function MemoryList() {
  const {
    keyboardVerticalOffset,
    inputBottomPadding,
    screenAnchorRef,
    onScreenAnchorLayout,
  } = useAdvisorComposerLayout();

  // -------------------------------------------------------------------------
  // State — see plan §High-Level Technical Design
  // -------------------------------------------------------------------------
  const [activeTab, setActiveTab] = useState<Tab>(DEFAULT_TAB);
  const [memories, setMemories] = useState<UserMemory[]>([]);
  const [byTab, setByTab] = useState<Record<Tab, TabState>>({
    goal: INITIAL_TAB_STATE,
    user_note: INITIAL_TAB_STATE,
  });
  const [initialLoading, setInitialLoading] = useState(true);
  const [refetching, setRefetching] = useState(false);
  // Single open swipe row at a time. Lifted from SwipeableMemoryRow so
  // tapping any other row, the subtabs chips, the empty list area, or
  // swiping a different row closes the previously-open one.
  const [openMemoryId, setOpenMemoryId] = useState<string | null>(null);
  // Row whose Delete the user just confirmed in the Alert. Drives the
  // exit animation in SwipeableMemoryRow; when the animation ends the
  // row calls back via onExitAnimationComplete and we mutate `memories`
  // (with restore-on-failure for the API call). Splitting the state
  // from `openMemoryId` keeps "trash button revealed" and "row is
  // sweeping out" independent — a Cancel from the Alert returns to the
  // open state without touching the exit machinery.
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  // Currently-open detail modal, or null when no row is being read.
  // Tap on a closed row (detected inside SwipeableMemoryRow's
  // PanResponder) drives this; the Modal in MemoryDetailSheet shows
  // the full content without truncation.
  const [detailMemory, setDetailMemory] = useState<UserMemory | null>(null);

  // Monotonic request counter + activeTab ref. A fetch that resolves
  // after a later fetch, or after the tab was switched, is discarded
  // — prevents a stale Goals response from overwriting Notes' data.
  // `activeTabRef` also gates `handleAdd`'s prepend so a row submitted
  // on Goals doesn't land in the Notes list if the user switches tabs
  // before the POST resolves.
  const requestIdRef = useRef(0);
  const activeTabRef = useRef<Tab>(DEFAULT_TAB);
  activeTabRef.current = activeTab;

  // Abort controller for the current in-flight list fetch. A rapid
  // tab tap cancels the prior request instead of firing a second
  // network round-trip, and the effect cleanup aborts the initial
  // load (relevant under React StrictMode's double-invoke in dev).
  const abortRef = useRef<AbortController | null>(null);

  const updateTab = useCallback(
    (tab: Tab, patch: Partial<TabState>) =>
      setByTab((prev) => ({ ...prev, [tab]: { ...prev[tab], ...patch } })),
    [],
  );

  // -------------------------------------------------------------------------
  // Unified load path — used by initial mount, tab switch, and retry.
  // Stale responses (user switched tabs mid-fetch) are dropped via the
  // request-id guard; only the most recent call for the currently-active
  // tab is allowed to mutate `memories`.
  // -------------------------------------------------------------------------
  const loadTab = useCallback(
    async (tab: Tab, { showRefetchIndicator = true } = {}) => {
      // Cancel any prior in-flight fetch so fast tab tapping does
      // not fire N parallel round-trips.
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const reqId = ++requestIdRef.current;
      if (showRefetchIndicator) setRefetching(true);
      updateTab(tab, { error: null });
      try {
        const response = await fetchMemories({
          type: tab,
          signal: controller.signal,
        });
        if (reqId !== requestIdRef.current || activeTabRef.current !== tab) return;
        setMemories(response.memories);
      } catch (err) {
        // Aborted fetches are expected when the user switches tabs
        // mid-request or the effect cleans up — swallow silently.
        if (err instanceof Error && err.name === "AbortError") return;
        if (reqId !== requestIdRef.current || activeTabRef.current !== tab) return;
        const message =
          err instanceof Error ? err.message : "We couldn't load your memories.";
        updateTab(tab, { error: message });
        setMemories([]);
      } finally {
        if (reqId === requestIdRef.current) setRefetching(false);
      }
    },
    [updateTab],
  );

  // -------------------------------------------------------------------------
  // Initial load — first mount only. Cleanup aborts the in-flight
  // fetch so React StrictMode's dev-only double-invoke doesn't fire
  // two identical network calls.
  // -------------------------------------------------------------------------
  useEffect(() => {
    (async () => {
      await loadTab(DEFAULT_TAB, { showRefetchIndicator: false });
      setInitialLoading(false);
    })();
    return () => abortRef.current?.abort();
  }, [loadTab]);

  // -------------------------------------------------------------------------
  // Tab switching — refetch the new tab's rows via loadTab. We keep the
  // previous list visible and show a subtle indicator (see plan) instead
  // of the full-screen skeleton on every tap. Drafts are intentionally
  // not cleared on switch — that's the whole point of per-tab state.
  // -------------------------------------------------------------------------
  const handleTabChange = useCallback(
    (tab: Tab) => {
      // Always close any open swipe row on a chip tap — even when the
      // tap is on the already-active chip — so the chip row works as
      // an extra dismiss surface for the open trash button.
      setOpenMemoryId(null);
      if (tab === activeTab) return;
      setActiveTab(tab);
      activeTabRef.current = tab;
      void loadTab(tab);
    },
    [activeTab, loadTab],
  );

  // -------------------------------------------------------------------------
  // Add memory — scoped to the active tab. Clears ONLY the active
  // tab's draft on success so the other tab's in-progress text stays
  // put. Errors surface via toast and leave the draft intact for retry.
  // -------------------------------------------------------------------------
  const activeState = byTab[activeTab];

  const handleAdd = useCallback(async () => {
    const trimmed = activeState.draft.trim();
    if (!trimmed || activeState.isAdding) return;
    const tab = activeTab;
    updateTab(tab, { isAdding: true });
    try {
      const newMemory = await addMemory(tab, { text: trimmed });
      // The draft belongs to `tab`; clearing it is always safe. But
      // `memories` reflects whichever tab is currently visible — only
      // prepend if the user is still on the tab they submitted from.
      // Otherwise the row would land in the wrong list visually until
      // the next refetch of `tab`.
      updateTab(tab, { draft: "", error: null });
      if (activeTabRef.current === tab) {
        setMemories((prev) => [newMemory, ...prev]);
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Couldn't save that memory.";
      updateTab(tab, { error: message });
      showToast({ kind: "error", message });
    } finally {
      updateTab(tab, { isAdding: false });
    }
  }, [activeState.draft, activeState.isAdding, activeTab, updateTab]);

  const handleDraftChange = useCallback(
    (text: string) => updateTab(activeTab, { draft: text }),
    [activeTab, updateTab],
  );

  // -------------------------------------------------------------------------
  // Delete memory — two-phase to avoid the visual glitch where the row
  // animated away BEFORE the user had confirmed. Now:
  //
  //   1. Trash tap (in row) → row notifies parent via `onDelete(id)` →
  //      this opens the Alert. The row stays in its swiped-open
  //      position, trash button still visible. Cancel from the Alert
  //      simply closes the row (existing tap-outside affordances).
  //
  //   2. Delete from the Alert → setPendingDeleteId(id). The matching
  //      row sees `isPendingDelete` flip to true and plays its exit
  //      animation (slide off left + fade).
  //
  //   3. Row's exit animation completes → row calls
  //      `handleExitAnimationComplete(id)` → we mutate `memories` and
  //      fire the DELETE network call. Restore-on-failure pops the
  //      row back into the list (no animation — the failure path is
  //      rare enough that polish there is not worth the complexity).
  // -------------------------------------------------------------------------
  const memoriesRef = useRef(memories);
  memoriesRef.current = memories;

  const handleDelete = useCallback((memoryId: string) => {
    Alert.alert(
      "Delete Memory",
      "Are you sure you want to delete this memory? Ada will no longer remember this.",
      [
        // Cancel: close the swipe row but leave the memory in place.
        // The row springs back to its rest position via the existing
        // controlled-isOpen effect.
        { text: "Cancel", style: "cancel", onPress: () => setOpenMemoryId(null) },
        {
          text: "Delete",
          style: "destructive",
          onPress: () => {
            // Hand off to the row's exit animation. Removal +
            // network call happen in handleExitAnimationComplete
            // once the sweep finishes. Note we leave openMemoryId
            // untouched on purpose — flipping it to null mid-exit
            // would race with the row's pendingDelete effect and
            // make the row spring back to closed before fading out.
            setPendingDeleteId(memoryId);
          },
        },
      ],
    );
  }, []);

  const handleExitAnimationComplete = useCallback(async (memoryId: string) => {
    // Reset the swipe + exit state in one batch so the row's mount
    // state is consistent for any future row reusing this slot.
    setPendingDeleteId(null);
    setOpenMemoryId((prev) => (prev === memoryId ? null : prev));
    const deletedItem = memoriesRef.current.find((m) => m.id === memoryId);
    setMemories((prev) => prev.filter((m) => m.id !== memoryId));
    try {
      await deleteMemory(memoryId);
    } catch {
      if (deletedItem) {
        setMemories((prev) =>
          [...prev, deletedItem].sort(
            (a, b) =>
              new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
          ),
        );
      }
      showToast({ kind: "error", message: "Couldn't delete that memory. Try again." });
    }
  }, []);

  // -------------------------------------------------------------------------
  // Render helpers
  // -------------------------------------------------------------------------
  const keyExtractor = useCallback((item: UserMemory) => item.id, []);

  const renderItem = useCallback(
    ({ item }: { item: UserMemory }) => (
      <SwipeableMemoryRow
        memory={item}
        onDelete={handleDelete}
        isOpen={openMemoryId === item.id}
        onOpenChange={setOpenMemoryId}
        isPendingDelete={pendingDeleteId === item.id}
        onExitAnimationComplete={handleExitAnimationComplete}
        onOpenDetail={setDetailMemory}
      />
    ),
    [handleDelete, handleExitAnimationComplete, openMemoryId, pendingDeleteId],
  );

  const handleCloseDetail = useCallback(() => setDetailMemory(null), []);

  const copy = TAB_COPY[activeTab];

  // `key={activeTab}` forces AdvisorComposer to remount on tab switch
  // so its focus state resets and the keyboard dismisses cleanly —
  // otherwise the previous tab's focused input stays live under the
  // new tab's draft value.
  const composer = (
    <AdvisorComposer
      key={activeTab}
      value={activeState.draft}
      onChangeText={handleDraftChange}
      onSubmit={handleAdd}
      placeholder={copy.placeholder}
      disabled={activeState.isAdding}
      submitIcon="add"
      maxLength={ADVISOR_CONFIG.MEMORY_MAX_LENGTH}
      accessibilityLabel={copy.composerA11yLabel}
      submitAccessibilityLabel="Add memory"
      bottomPadding={inputBottomPadding}
    />
  );

  const subTabs = <SubTabs activeTab={activeTab} onChange={handleTabChange} />;

  if (initialLoading) {
    return (
      <View
        ref={screenAnchorRef}
        onLayout={onScreenAnchorLayout}
        style={styles.container}
        collapsable={false}
      >
        <KeyboardAvoidingView
          style={styles.container}
          behavior="padding"
          keyboardVerticalOffset={keyboardVerticalOffset}
          enabled={Platform.OS !== "web"}
        >
          {subTabs}
          <MemorySkeleton />
          {composer}
        </KeyboardAvoidingView>
      </View>
    );
  }

  return (
    <View
      ref={screenAnchorRef}
      onLayout={onScreenAnchorLayout}
      style={styles.container}
      collapsable={false}
    >
    <KeyboardAvoidingView
      style={styles.container}
      behavior="padding"
      keyboardVerticalOffset={keyboardVerticalOffset}
      enabled={Platform.OS !== "web"}
    >
      {subTabs}

      {/* rowsArea is THE empty region of the Memories tab — the gap
          between the SubTabs chips above and the composer below. The
          empty/error overlays absoluteFill rowsArea, NOT a wider
          container that includes the subtabs. Centering inside rowsArea
          gives the hero equal space above (chip row → icon) and below
          (description → composer), matching how the Chat and Nudges
          empty heroes look. Including the subtabs in the centering
          region would bias the hero up against the chips because the
          subtabs eat the top of the centering box.

          accessibilityLiveRegion is Android-only; iOS VoiceOver
          ignores it. A future polish pass could call
          AccessibilityInfo.announceForAccessibility on tab change. */}
      <View style={styles.rowsArea} accessibilityLiveRegion="polite">
        <FlatList
          data={memories}
          keyExtractor={keyExtractor}
          renderItem={renderItem}
          showsVerticalScrollIndicator={false}
          contentContainerStyle={styles.listContent}
          ItemSeparatorComponent={MemorySeparator}
          ListFooterComponent={
            openMemoryId !== null ? (
              <Pressable
                style={styles.dismissFooter}
                onPress={() => setOpenMemoryId(null)}
                accessibilityElementsHidden
                importantForAccessibility="no"
              />
            ) : null
          }
          onScrollBeginDrag={() => {
            if (openMemoryId !== null) setOpenMemoryId(null);
          }}
        />

        {/* Tab-switch spinner — overlay; list stays rendered underneath. */}
        {refetching && (
          <View style={styles.refetchIndicator} pointerEvents="none">
            <ActivityIndicator size="small" color={THEME.colors.textSecondary} />
          </View>
        )}

        {/* Error overlay — scoped to the active tab; subtabs above stay
            interactive (overlays use pointerEvents="box-none"). Retry
            reuses loadTab so the stale-response guard applies. */}
        {activeState.error && memories.length === 0 && (
          <AdvisorEmptyOverlay
            icon="alert-circle-outline"
            title="Could not load memories"
            description={activeState.error}
            action={{
              label: "Try Again",
              onPress: () => void loadTab(activeTab),
              accessibilityLabel: "Retry loading memories",
            }}
            opticalLift={0}
          />
        )}

        {/* Empty overlay — per-tab copy. opticalLift=0 because the
            Memories rowsArea has chrome on BOTH ends (subtabs above,
            composer below) — the default 96pt lift overshoots and
            biases the hero up against the chips. With lift=0 the
            hero sits at the true geometric center of the gap. */}
        {!activeState.error && !refetching && memories.length === 0 && (
          <AdvisorEmptyOverlay
            icon={memoryTypeIcon(activeTab)}
            title={copy.emptyTitle}
            description={copy.emptyDescription}
            opticalLift={0}
          />
        )}
      </View>

      {composer}
    </KeyboardAvoidingView>

      {/* Detail modal — full content of a tapped row. Mounted outside
          the KeyboardAvoidingView so the sheet measures against the
          device viewport rather than the lifted chat region. */}
      <MemoryDetailSheet memory={detailMemory} onClose={handleCloseDetail} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "transparent",
  },
  /**
   * The actual empty region of the Memories tab — sits BELOW the
   * SubTabs chip row and ABOVE the composer. The FlatList fills it
   * when there are rows; when the list is empty the AdvisorEmptyOverlay
   * absoluteFills THIS box so the centering math gives the hero equal
   * space above the icon and below the description.
   */
  rowsArea: {
    flex: 1,
  },
  listContent: {
    flexGrow: 1,
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md,
    paddingBottom: THEME.spacing.lg,
  },
  /**
   * Tappable footer rendered only when a swipe row is open. flex:1
   * stretches it to fill the empty space below the last row, so a tap
   * anywhere in the list-but-not-on-a-row closes the open row. Min
   * height keeps it tappable when the rows already fill the viewport.
   */
  dismissFooter: {
    flex: 1,
    minHeight: 80,
  },
  separator: {
    height: THEME.spacing.md - 2,
  },
  refetchIndicator: {
    position: "absolute",
    top: THEME.spacing.md,
    left: 0,
    right: 0,
    alignItems: "center",
  },
});
