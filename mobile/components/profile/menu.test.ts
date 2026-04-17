import { buildProfileMenu, type ProfileMenuHandlers } from "./menu";
import type { Capabilities } from "../../lib/capabilities";

const HANDLERS: ProfileMenuHandlers = {
  onEditProfile: jest.fn(),
  onOpenSubscription: jest.fn(),
  onOpenSettings: jest.fn(),
  onLogout: jest.fn(),
  onSignIn: jest.fn(),
};

const BASE: Capabilities = {
  canViewOwnProfile: true,
  canEditProfile: false,
  canViewAccountDetails: false,
  canDeleteAccount: false,
  canSignOut: false,
  canSignIn: false,
  canSeeFeed: false,
  canUseAdvisor: false,
  canShareGlowup: false,
  canShareProfile: false,
  canSeeOnboarding: false,
  canSubscribe: true,
  canReact: false,
  canViewBlockedUsers: false,
  requiresAuth: false,
};

function caps(overrides: Partial<Capabilities> = {}): Capabilities {
  return { ...BASE, ...overrides };
}

describe("buildProfileMenu", () => {
  it("real-user menu = [Edit, Subscription, Settings, Log Out]", () => {
    const items = buildProfileMenu(
      caps({ canEditProfile: true, canSignOut: true, canSubscribe: true }),
      HANDLERS,
    );
    expect(items.map((i) => i.label)).toEqual([
      "Edit Profile",
      "Subscription",
      "Settings",
      "Log Out",
    ]);
  });

  it("guest menu = [Subscription, Settings, Sign In] — no Log Out, no Edit", () => {
    const items = buildProfileMenu(
      caps({ canEditProfile: false, canSignOut: false, canSignIn: true }),
      HANDLERS,
    );
    expect(items.map((i) => i.label)).toEqual([
      "Subscription",
      "Settings",
      "Sign In",
    ]);
  });

  it("anon menu = [Subscription, Settings, Sign In]", () => {
    const items = buildProfileMenu(
      caps({ canSignIn: true }),
      HANDLERS,
    );
    expect(items.map((i) => i.label)).toEqual([
      "Subscription",
      "Settings",
      "Sign In",
    ]);
  });

  it("Settings always present (no capability gate today)", () => {
    const items = buildProfileMenu(caps(), HANDLERS);
    expect(items.some((i) => i.label === "Settings")).toBe(true);
  });

  it("Log Out is marked destructive", () => {
    const items = buildProfileMenu(
      caps({ canEditProfile: true, canSignOut: true }),
      HANDLERS,
    );
    const logout = items.find((i) => i.label === "Log Out");
    expect(logout).toBeDefined();
    expect(logout?.destructive).toBe(true);
  });

  it("Subscription suppressed when canSubscribe=false (future-proofing)", () => {
    const items = buildProfileMenu(
      caps({ canSubscribe: false, canSignIn: true }),
      HANDLERS,
    );
    expect(items.some((i) => i.label === "Subscription")).toBe(false);
  });
});
