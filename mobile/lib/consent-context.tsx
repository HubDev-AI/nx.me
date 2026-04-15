/**
 * ConsentContext — manages face-modification consent state.
 *
 * Tracks whether the current user has granted face-mod consent
 * (users.face_mod_consent_at). Exposes `requestConsentIfNeeded` which
 * upstream callers (upload screen Analyze tap) invoke before proceeding.
 * If consent is already granted, the call resolves immediately.
 * If consent is missing, it shows the FaceModConsent modal and resolves
 * after the user accepts (or rejects — in which case it rejects the promise).
 *
 * Mount: <ConsentProvider> wraps the app inside _layout.tsx.
 * Render: <ConsentGate /> renders the modal at root (avoids z-index fights).
 */
import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { FaceModConsent } from "../components/consent/FaceModConsent";

import { grantFaceModConsent } from "./analysis";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConsentContextValue {
  /** Whether the current user has consented. Null = unknown (not yet loaded). */
  hasConsent: boolean | null;
  /** Mark consent as granted (called after POST /users/me/face-mod-consent). */
  markConsentGranted: () => void;
  /**
   * Resolves if user has (or grants) consent.
   * Rejects with ConsentDismissedError if user dismisses the modal.
   */
  requestConsentIfNeeded: () => Promise<void>;
}

export class ConsentDismissedError extends Error {
  constructor() {
    super("Face-mod consent modal dismissed");
    this.name = "ConsentDismissedError";
  }
}

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------

const ConsentContext = createContext<ConsentContextValue>({
  hasConsent: null,
  markConsentGranted: () => {},
  requestConsentIfNeeded: () => Promise.resolve(),
});

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function ConsentProvider({ children }: { children: ReactNode }) {
  const [hasConsent, setHasConsent] = useState<boolean | null>(null);
  const [modalVisible, setModalVisible] = useState(false);

  // Pending promise resolvers — set when modal is shown, cleared on settle.
  const pendingResolveRef = useRef<(() => void) | null>(null);
  const pendingRejectRef = useRef<((reason: ConsentDismissedError) => void) | null>(null);

  const markConsentGranted = useCallback(() => {
    setHasConsent(true);
  }, []);

  const requestConsentIfNeeded = useCallback((): Promise<void> => {
    // Already consented — no-op.
    if (hasConsent === true) return Promise.resolve();

    // Show modal and return a promise that settles when the user acts.
    return new Promise<void>((resolve, reject) => {
      pendingResolveRef.current = resolve;
      pendingRejectRef.current = reject;
      setModalVisible(true);
    });
  }, [hasConsent]);

  const handleAccept = useCallback(async () => {
    setModalVisible(false);
    try {
      await grantFaceModConsent();
      setHasConsent(true);
      pendingResolveRef.current?.();
    } catch {
      // Consent API failed — still resolve so the user can proceed; the
      // backend will 428 on the analyze call if consent isn't persisted.
      setHasConsent(true);
      pendingResolveRef.current?.();
    } finally {
      pendingResolveRef.current = null;
      pendingRejectRef.current = null;
    }
  }, []);

  const handleDismiss = useCallback(() => {
    setModalVisible(false);
    pendingRejectRef.current?.(new ConsentDismissedError());
    pendingResolveRef.current = null;
    pendingRejectRef.current = null;
  }, []);

  return (
    <ConsentContext.Provider
      value={{ hasConsent, markConsentGranted, requestConsentIfNeeded }}
    >
      {children}
      {/* Lazy import to avoid circular dep — rendered here so it's above all screens. */}
      <ConsentModalSlot
        visible={modalVisible}
        onAccept={handleAccept}
        onDismiss={handleDismiss}
      />
    </ConsentContext.Provider>
  );
}

function ConsentModalSlot({
  visible,
  onAccept,
  onDismiss,
}: {
  visible: boolean;
  onAccept: () => void;
  onDismiss: () => void;
}) {
  return (
    <FaceModConsent visible={visible} onAccept={onAccept} onDismiss={onDismiss} />
  );
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useConsent(): ConsentContextValue {
  return useContext(ConsentContext);
}
