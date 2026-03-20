# Napkin

## Corrections
| Date | Source | What Went Wrong | What To Do Instead |
|------|--------|----------------|-------------------|
| 2026-03-20 | Investigation | `tabBarItemStyle` with `justifyContent: 'center'` does NOT fix vertical centering -- it applies to the outer wrapper View, not the inner pressable where `justifyContent: 'flex-start'` is hardcoded | Use `tabBarIconStyle: { flex: 1 }` to expand the icon wrapper to fill the tab item height; the absolute-positioned icon children already center themselves |

## User Preferences

## Patterns That Work
- `tabBarIconStyle: { flex: 1 }` fixes vertical centering when `tabBarShowLabel: false` in React Navigation bottom tabs
- Tracing through node_modules source to find root cause of style issues rather than applying workarounds
- Custom animated tab bar via `tabBar` prop: render `<BottomTabBar {...props} />` inside an `Animated.View` -- preserves all existing styles including `position: absolute` pill
- `useAnimatedScrollHandler` context types must be explicitly typed via `ScrollHandlerProcessed<T>` in interfaces; reanimated v4 exports this type
- `Animated.createAnimatedComponent(FlatList<T>)` works for typed FlatLists; pass ref via `as any` cast since animated wrapper loses generic ref type

## Patterns That Don't Work
- `tabBarItemStyle: { justifyContent: 'center' }` -- only affects outer View, inner pressable has hardcoded flex-start
- CSS injection / style hacks for React Navigation layout issues
- Padding workarounds to compensate for misaligned flex layouts

## Domain Notes
- React Navigation BottomTabItem (uikit variant, vertical layout) uses `justifyContent: 'flex-start'` on the inner pressable because it expects icon + label stacked vertically
- When `showLabel: false`, the label renders null but the flex-start layout remains, pushing the icon to the top
- The icon is rendered inside TabBarIcon which has a fixed-size wrapper (31x28 for uikit); children are absolute-positioned with `height: '100%'` and `justifyContent: 'center'`
- `tabBarIconStyle` maps to TabBarIcon's wrapper `style` prop, applied after base styles
- Expo Router `<Tabs>` wraps `@react-navigation/bottom-tabs` directly
