import { useEffect } from "react";
import { Platform } from "react-native";
import { useFonts as useExpoFonts } from "expo-font";
import {
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
} from "@expo-google-fonts/inter";
import {
  InstrumentSerif_400Regular,
  InstrumentSerif_400Regular_Italic,
} from "@expo-google-fonts/instrument-serif";

/**
 * On web, inject Google Fonts link tag for proper rendering.
 * expo-font works on native but web needs CSS @font-face from Google.
 */
function useWebFonts() {
  useEffect(() => {
    if (Platform.OS !== "web") return;
    if (typeof document === "undefined") return;

    // Check if already injected
    if (document.getElementById("nxme-google-fonts")) return;

    const link = document.createElement("link");
    link.id = "nxme-google-fonts";
    link.rel = "stylesheet";
    link.href =
      "https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Inter:wght@400;500;600;700&display=swap";
    document.head.appendChild(link);
  }, []);
}

export function useAppFonts() {
  useWebFonts();

  const [fontsLoaded] = useExpoFonts({
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    InstrumentSerif_400Regular,
    InstrumentSerif_400Regular_Italic,
  });

  // On web, fonts load via CSS — always consider them loaded
  if (Platform.OS === "web") return true;
  return fontsLoaded;
}

export const FONTS = {
  body: "Inter_400Regular",
  bodyMedium: "Inter_500Medium",
  bodySemiBold: "Inter_600SemiBold",
  bodyBold: "Inter_700Bold",
  display: "InstrumentSerif_400Regular",
  displayItalic: "InstrumentSerif_400Regular_Italic",
} as const;

/**
 * Web CSS font-family fallbacks — use these in web-specific overrides.
 * On native, the FONTS constants above work directly.
 */
export const WEB_FONTS = {
  body: "'Inter', system-ui, sans-serif",
  display: "'Instrument Serif', Georgia, serif",
} as const;
