# Napkin

## Corrections
| Date | Source | What Went Wrong | What To Do Instead |
|------|--------|----------------|-------------------|
| 2026-03-20 | Investigation | `tabBarItemStyle` with `justifyContent: 'center'` does NOT fix vertical centering -- it applies to the outer wrapper View, not the inner pressable where `justifyContent: 'flex-start'` is hardcoded | Use `tabBarIconStyle: { flex: 1 }` to expand the icon wrapper to fill the tab item height; the absolute-positioned icon children already center themselves |

## User Preferences
- ONE auth hook (`useAuth`) used everywhere -- no ad-hoc auth state management

## Patterns That Work
- Reanimated `FadeInDown`/`FadeOutUp` entering/exiting animations on conditionally rendered `Animated.View` -- much simpler and more reliable than `maxHeight` clipping for expandable sections (no content cutoff, no need to calculate expanded height)
- Move overlay buttons (3-dot menu etc.) to `position: absolute` in the parent screen rather than inside `ListHeaderComponent` -- prevents z-index conflicts and overlap with header content
- `tabBarIconStyle: { flex: 1 }` fixes vertical centering when `tabBarShowLabel: false` in React Navigation bottom tabs
- Tracing through node_modules source to find root cause of style issues rather than applying workarounds
- Custom animated tab bar via `tabBar` prop: render `<BottomTabBar {...props} />` inside an `Animated.View` -- preserves all existing styles including `position: absolute` pill
- `useAnimatedScrollHandler` context types must be explicitly typed via `ScrollHandlerProcessed<T>` in interfaces; reanimated v4 exports this type
- `Animated.createAnimatedComponent(FlatList<T>)` works for typed FlatLists; pass ref via `as any` cast since animated wrapper loses generic ref type

## Patterns That Don't Work
- `maxHeight` + `overflow: 'hidden'` for collapsible sections -- clips content, requires hardcoded expanded height constant that easily drifts out of sync with actual content, looks terrible when height is wrong
- Placing overlay buttons (3-dot menu) inside `ListHeaderComponent` with `position: absolute` -- causes overlap with other header elements because the absolute positioning is relative to the header wrapper, not the screen
- `tabBarItemStyle: { justifyContent: 'center' }` -- only affects outer View, inner pressable has hardcoded flex-start
- CSS injection / style hacks for React Navigation layout issues
- Padding workarounds to compensate for misaligned flex layouts

## Domain Notes
- Backend POST /v1/auth/email-login returns `{ user_id, access_token, refresh_token, expires_at }` -- NO username
- Backend POST /v1/auth/register returns `{ message, email }` -- username is known from the request, not the response
- No /v1/auth/me or /v1/users/me endpoint exists -- profile requires actual username in path
- Username resolution strategy: persist during registration, read from secure storage on login, fallback to email-prefix guess verified against profile API
- `nxme_username` key in secure storage is the canonical location for the current user's username
- auth-context.tsx manages username in state + secure storage; clears on logout
- React Navigation BottomTabItem (uikit variant, vertical layout) uses `justifyContent: 'flex-start'` on the inner pressable because it expects icon + label stacked vertically
- When `showLabel: false`, the label renders null but the flex-start layout remains, pushing the icon to the top
- The icon is rendered inside TabBarIcon which has a fixed-size wrapper (31x28 for uikit); children are absolute-positioned with `height: '100%'` and `justifyContent: 'center'`
- `tabBarIconStyle` maps to TabBarIcon's wrapper `style` prop, applied after base styles
- Expo Router `<Tabs>` wraps `@react-navigation/bottom-tabs` directly
