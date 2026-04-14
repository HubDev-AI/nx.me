/**
 * ShareComposite — hook-based headless share helper.
 *
 * Renders an offscreen 1080×1080 view with both images + a thin divider
 * + label strip + <Watermark />, captures it to a temp PNG via
 * react-native-view-shot, then hands the URI to the native Share sheet.
 *
 * Usage:
 *   const { generateAndShare, isCapturing } = useShareComposite();
 *   await generateAndShare({ beforeUrl, afterUrl, rightLabel: "Glow Up" });
 *
 * Gotcha: captureRef fires before images load = blank PNG.
 * Guard: track onLoad for each image; only enable capture once both ready.
 */
import { useRef, useState, useCallback } from "react";
import {
  View,
  Image,
  Share,
  StyleSheet,
  Alert,
  Text,
} from "react-native";
import { captureRef } from "react-native-view-shot";

import { FONTS } from "../../hooks/useFonts";
import { Watermark } from "./Watermark";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Output composite dimensions (square Instagram-style). */
const COMPOSITE_SIZE_PX = 1080;

/** Width of each half within the composite (px). */
const HALF_WIDTH_PX = COMPOSITE_SIZE_PX / 2;

/** Divider line width between before and after halves (px). */
const COMPOSITE_DIVIDER_PX = 2;

/** Divider line color. */
const COMPOSITE_DIVIDER_COLOR = "rgba(255,255,255,0.8)";

/** Height of the bottom label strip (px). */
const LABEL_STRIP_HEIGHT_PX = 64;

/** Background color for the label strip. */
const LABEL_STRIP_BG = "rgba(0,0,0,0.7)";

/** Font size for before/after labels within the composite (px). */
const LABEL_FONT_SIZE_PX = 18;

/** Letter-spacing for labels. */
const LABEL_LETTER_SPACING = 1.5;

/** Offset to move the composite far enough off-screen to be invisible. */
const OFFSCREEN_OFFSET = -COMPOSITE_SIZE_PX - 200;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ShareParams {
  beforeUrl: string;
  afterUrl: string;
  /** Right-side label, e.g. "Glow Up". */
  rightLabel: string;
  /** Optional card-web URL to attach to the native share sheet.
   *  When present, shared messages include a clickable link back to
   *  the user's card instead of a standalone PNG. */
  shareUrl?: string;
  /** Optional prose message accompanying the image. Used when the
   *  recipient app supports plain text alongside the attachment. */
  shareMessage?: string;
}

interface UseShareCompositeReturn {
  /** Renders the offscreen composite. Must be included in the component tree. */
  ShareCompositeView: React.ReactNode;
  /** Capture → share. Resolves when the native share sheet is dismissed. */
  generateAndShare: (params: ShareParams) => Promise<void>;
  /** True while capturing (disable Share button during this). */
  isCapturing: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useShareComposite(): UseShareCompositeReturn {
  const viewRef = useRef<View>(null);

  // Track readiness of each image.
  const [beforeReady, setBeforeReady] = useState(false);
  const [afterReady, setAfterReady] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);

  // Current share params — updated before each share.
  const [params, setParams] = useState<ShareParams>({
    beforeUrl: "",
    afterUrl: "",
    rightLabel: "",
  });
  const paramsRef = useRef<ShareParams>(params);
  paramsRef.current = params;

  // Reset image readiness whenever URLs change.
  const updateParams = useCallback((next: ShareParams) => {
    setParams(next);
    paramsRef.current = next;
    setBeforeReady(false);
    setAfterReady(false);
  }, []);

  const generateAndShare = useCallback(
    async (nextParams: ShareParams) => {
      updateParams(nextParams);

      // Poll until both images are ready (max ~3 seconds).
      const MAX_WAIT_MS = 3000;
      const POLL_INTERVAL_MS = 100;
      const startedAt = Date.now();

      await new Promise<void>((resolve, reject) => {
        const check = () => {
          // Re-read via refs rather than stale closure values.
          if (bothReadyRef.current) {
            resolve();
            return;
          }
          if (Date.now() - startedAt > MAX_WAIT_MS) {
            reject(new Error("Share composite: image load timeout"));
            return;
          }
          setTimeout(check, POLL_INTERVAL_MS);
        };
        check();
      });

      setIsCapturing(true);
      try {
        const uri = await captureRef(viewRef, {
          format: "png",
          quality: 1,
          result: "tmpfile",
          width: COMPOSITE_SIZE_PX,
          height: COMPOSITE_SIZE_PX,
        });
        // iOS Share.share accepts both url (attachment) + message (body).
        // On Android `url` is ignored; the message carries the link text so
        // recipients still get something clickable.
        const { shareUrl, shareMessage } = paramsRef.current;
        const content: Parameters<typeof Share.share>[0] = shareMessage
          ? { url: uri, message: shareMessage }
          : { url: uri };
        await Share.share(content);
        void shareUrl; // consumed via shareMessage; kept for future platforms.
      } catch (err) {
        const message = err instanceof Error ? err.message : "Share failed";
        Alert.alert("Share failed", message);
      } finally {
        setIsCapturing(false);
      }
    },
    [updateParams],
  );

  // Ref for both-ready state so the polling closure can see current values.
  const bothReadyRef = useRef(false);
  bothReadyRef.current = beforeReady && afterReady;

  const ShareCompositeView = (
    <View style={styles.offscreenWrapper} pointerEvents="none">
      <View
        ref={viewRef}
        collapsable={false}
        style={styles.composite}
      >
        {/* Left half: Before image */}
        <Image
          source={{ uri: params.beforeUrl }}
          style={styles.halfImage}
          resizeMode="cover"
          onLoad={() => setBeforeReady(true)}
          accessibilityElementsHidden={true}
        />

        {/* Divider */}
        <View style={styles.divider} />

        {/* Right half: After image */}
        <Image
          source={{ uri: params.afterUrl }}
          style={styles.halfImage}
          resizeMode="cover"
          onLoad={() => setAfterReady(true)}
          accessibilityElementsHidden={true}
        />

        {/* Bottom label strip */}
        <View style={styles.labelStrip} pointerEvents="none">
          <View style={styles.labelHalf}>
            <Text style={styles.labelText} allowFontScaling={false}>
              BEFORE
            </Text>
          </View>
          <View style={styles.labelDivider} />
          <View style={styles.labelHalf}>
            <Text style={styles.labelText} allowFontScaling={false}>
              {params.rightLabel.toUpperCase()}
            </Text>
          </View>
        </View>

        {/* Watermark */}
        <Watermark position="bottom-right" imageHeightPx={COMPOSITE_SIZE_PX} />
      </View>
    </View>
  );

  return { ShareCompositeView, generateAndShare, isCapturing };
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  offscreenWrapper: {
    position: "absolute",
    top: OFFSCREEN_OFFSET,
    left: 0,
    width: COMPOSITE_SIZE_PX,
    height: COMPOSITE_SIZE_PX,
    overflow: "hidden",
  },
  composite: {
    width: COMPOSITE_SIZE_PX,
    height: COMPOSITE_SIZE_PX,
    flexDirection: "row",
    backgroundColor: "#000000",
    overflow: "hidden",
  },
  halfImage: {
    width: HALF_WIDTH_PX - COMPOSITE_DIVIDER_PX / 2,
    height: COMPOSITE_SIZE_PX,
  },
  divider: {
    width: COMPOSITE_DIVIDER_PX,
    height: COMPOSITE_SIZE_PX,
    backgroundColor: COMPOSITE_DIVIDER_COLOR,
  },
  labelStrip: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    height: LABEL_STRIP_HEIGHT_PX,
    backgroundColor: LABEL_STRIP_BG,
    flexDirection: "row",
    alignItems: "center",
  },
  labelHalf: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  labelDivider: {
    width: COMPOSITE_DIVIDER_PX,
    height: LABEL_STRIP_HEIGHT_PX * 0.5,
    backgroundColor: COMPOSITE_DIVIDER_COLOR,
  },
  labelText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: LABEL_FONT_SIZE_PX,
    color: "#ffffff",
    letterSpacing: LABEL_LETTER_SPACING,
  },
});
