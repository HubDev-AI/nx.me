---
alwaysApply: false
globs: ["*.tsx", "*.jsx", "*.ts", "*.css"]
---

# LimeChain Design System

This project uses the LimeChain Design System (shadcn/ui v4 + Tailwind).

Before creating UI components, read `docs/design-system.md` Sections 8-10 for the component catalog and Figma-to-Code mapping.

- **Use shadcn components** — never hand-code what exists in the catalog (`npx shadcn add <name>`)
- **Use design tokens** — never hardcode colors, spacing, or typography values; use CSS variables and Tailwind classes
- **Follow Section 9 patterns** for custom components not covered by shadcn
- **Check Section 11** for organism recipes before composing page layouts
- **All four themes must work** — wireframe-light, wireframe-dark, brand-light, brand-dark
