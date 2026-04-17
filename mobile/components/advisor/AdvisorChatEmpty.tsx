/**
 * AdvisorChatEmpty — scoped seed state for the advisor Chat tab.
 *
 * Replaces the generic AdvisorEmptyOverlay's "Start a conversation" /
 * "Ask Ada for style advice" copy. Renders inside the same listArea slot
 * (NOT StyleSheet.absoluteFill) so the chips don't z-stack with the
 * composer below — the chips are interactive and need clean hit
 * targeting.
 *
 * Hardcoded scope must stay in sync with `app/advisor/SOUL.md`. If the
 * persona's lanes change, update both the body copy and the chip list
 * in `mobile/constants/config.ts`.
 */
import { ScrollView, StyleSheet, View } from "react-native";

import {
  ADVISOR_CHAT_EMPTY_BODY,
  ADVISOR_CHAT_EMPTY_TITLE,
  ADVISOR_CHAT_STARTER_CHIPS,
} from "../../constants/config";
import { THEME } from "../../constants/theme";
import { Button } from "../ui/Button";
import { Body, Heading } from "../ui/Text";

export interface AdvisorChatEmptyProps {
  /**
   * Invoked with the chip text when a chip is tapped. The caller is
   * responsible for actually sending the message — this component only
   * renders the copy + chips.
   */
  onChipPress: (chipText: string) => void;
  /**
   * Disable the chips while a send is in flight so a double-tap can't
   * fire two LLM calls in parallel.
   */
  isSending?: boolean;
}

export function AdvisorChatEmpty({
  onChipPress,
  isSending = false,
}: AdvisorChatEmptyProps) {
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
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipsRow}
      >
        {ADVISOR_CHAT_STARTER_CHIPS.map((chip) => (
          <Button
            key={chip}
            title={chip}
            onPress={() => onChipPress(chip)}
            variant="outline"
            size="sm"
            disabled={isSending}
            haptic="light"
          />
        ))}
      </ScrollView>
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
    gap: THEME.spacing.md,
  },
  /* Title + body get their own horizontal padding; the ScrollView
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
  chipsRow: {
    paddingTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.xxl,
    gap: THEME.spacing.sm,
  },
});
