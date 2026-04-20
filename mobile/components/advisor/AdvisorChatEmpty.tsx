/**
 * AdvisorChatEmpty — scoped seed state for the advisor Chat tab.
 *
 * Replaces the generic AdvisorEmptyOverlay's "Start a conversation" /
 * "Ask Ada for style advice" copy. Renders inside the same listArea slot
 * (NOT StyleSheet.absoluteFill) so the chips don't z-stack with the
 * composer below — the chips are interactive and need clean hit
 * targeting.
 *
 * Vertical stack:
 *   1. Static title + body copy ("Hi, I'm Ada…").
 *   2. `ChatSeedChips` — up to 3 server-generated seeds. A chip tap
 *      bubbles `seed.text` up to the parent (ChatView), which prefills
 *      the composer. The user still taps send — nothing auto-submits.
 *
 * Hardcoded copy must stay in sync with `app/advisor/SOUL.md`. The
 * seeds themselves are server-driven (Unit 5 endpoint), so no hardcoded
 * chip list lives in this file.
 */
import { StyleSheet, View } from "react-native";

import {
  ADVISOR_CHAT_EMPTY_BODY,
  ADVISOR_CHAT_EMPTY_TITLE,
} from "../../constants/config";
import { THEME } from "../../constants/theme";
import { EMPTY_STATE_OPTICAL_LIFT } from "../ui/EmptyState";
import { Body, Heading } from "../ui/Text";
import { ChatSeedChips } from "./ChatSeedChips";

export interface AdvisorChatEmptyProps {
  /**
   * Invoked with the seed's full prompt text when a chip is tapped. The
   * parent (ChatView) prefills the composer — this component only
   * renders the copy + chip row; nothing auto-submits.
   */
  onChipPress: (seedText: string) => void;
}

export function AdvisorChatEmpty({ onChipPress }: AdvisorChatEmptyProps) {
  return (
    <View style={styles.container}>
      <View style={styles.textBlock}>
        <Heading
          size="md"
          display={false}
          color="primary"
          style={styles.title}
        >
          {ADVISOR_CHAT_EMPTY_TITLE}
        </Heading>
        <Body color="secondary" style={styles.body}>
          {ADVISOR_CHAT_EMPTY_BODY}
        </Body>
      </View>
      <ChatSeedChips onChipPress={onChipPress} />
    </View>
  );
}

const styles = StyleSheet.create({
  /* flex:1 + center so the hero sits mid-viewport of the listArea
     instead of pinned to the top. Horizontal padding stays off the
     container so the chip ScrollView can extend edge-to-edge — the
     last chip was being clipped by container padding when it spilled
     past the viewport. */
  container: {
    flex: 1,
    justifyContent: "center",
    paddingBottom: EMPTY_STATE_OPTICAL_LIFT,
    gap: THEME.spacing.md,
  },
  /* Title + body get their own horizontal padding; the ChatSeedChips
     sibling below keeps full width for overflow scrolling. */
  textBlock: {
    paddingHorizontal: THEME.spacing.xxl,
    gap: THEME.spacing.md,
  },
  title: {
    textAlign: "center",
  },
  body: {
    textAlign: "center",
  },
});
