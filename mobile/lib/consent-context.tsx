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
  /**
   * Hydrate consent state from the server. Pass `true` after POST
   * /users/me/face-mod-consent succeeds, or when GET /users/me
   * returns a non-null `face_mod_consent_at`. Pass `false` to reset
   * (sign-out, account switch, user deletion via the settings flow).
   */
  markConsentGranted: (granted?: boolean) => void;
  /**
   * Resolves if user has (or grants) consent.
   * Rejects with ConsentDismissedError if user dismisses the modal,
   * or with the underlying error if the grant API call fails.
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

  const markConsentGranted = useCallback((granted: boolean = true) => {
    setHasConsent(granted);
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
    } catch (err) {
      // Consent API failed — DO NOT flip hasConsent to true. The old
      // behavior was to pretend success, which then 428'd the analyze
      // call and left the Analyze button looking broken. Reject the
      // pending promise so the caller (upload.tsx) can surface a real
      // error and the user can retry.
      pendingRejectRef.current?.(
        err instanceof Error
          ? err
          : new Error("Failed to save consent. Try again."),
      );
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
