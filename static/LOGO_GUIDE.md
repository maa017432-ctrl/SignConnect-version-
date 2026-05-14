# SignConnect Logo Design

## Concept
The SignConnect logo visually represents "connection" through a minimal, geometric design inspired by modern SaaS branding (Stripe, Linear, Vercel).

### Design Philosophy
- **Minimal**: Clean, no unnecessary details or decorative elements
- **Geometric**: Two circles connected by a bridge line — representing nodes establishing a connection
- **Meaningful**: The connection metaphor is central to the meaning (sign language connecting people)
- **Professional**: Flat design, no gradients or glow effects, works in light and dark themes

---

## Logo Components

### Icon (Connection Symbol)
- **Left Node**: Solid circle (radius 5.5)
- **Right Node**: Solid circle (radius 5.5)
- **Bridge**: Horizontal line connecting the two nodes (represents the link/bridge)
- **Signal Arc**: Curved line above the bridge (represents data/signal flow through the connection)

### Typography
- **Font**: System default sans-serif (SF Pro Display on Apple, Segoe UI on Windows)
- **Weight**: 600 (semi-bold)
- **Size**: Responsive (24px in header)
- **Letter Spacing**: Tight (-0.5px) for modern, premium feel

---

## Files

### Full Logo (Icon + Text)
**Location**: `/static/logo.svg`
- **Use**: Header branding, website logo
- **Dimensions**: 240×60px (16:4 aspect ratio)
- **Color**: Inherits from `currentColor` (dark in light theme, light in dark theme)

### Icon Only (Mark)
**Location**: `/static/logo-icon.svg`
- **Use**: Favicon, app icon, tab icon
- **Dimensions**: 64×64px (square)
- **Color**: Inherits from `currentColor`

---

## Design Details

### Spacing & Proportions
- Left node positioned at X=12
- Right node positioned at X=28
- Center Y at 30 (vertical center)
- Bridge spans from X=17.5 to X=22.5 (4 units, centered)
- Signal arc curves from X=15 to X=25
- Text starts at X=42 (clear gap from icon)

### Visual Hierarchy
1. **Nodes** (circles) — Primary visual elements
2. **Bridge line** — Connection emphasis (thicker stroke)
3. **Signal arc** — Secondary accent (lighter opacity)
4. **Text** — Brand name

### Color & Theme Support
- Uses `currentColor` to automatically adapt to light/dark themes
- Opacity variations create depth without using colors:
  - Nodes: 90-95% opacity (strong)
  - Bridge: 100% opacity (emphasis)
  - Signal arc: 40-65% opacity (subtle accent)

---

## Technical Implementation

### HTML Integration
```html
<a href="/" class="logo-link">
  <svg class="logo-svg" ...>
    <!-- Logo content -->
  </svg>
</a>
```

### CSS Styling
```css
.logo-link {
  display: inline-flex;
  align-items: center;
  transition: opacity 150ms;
}

.logo-svg {
  width: 140px;
  height: 35px;
  color: var(--text);
  flex-shrink: 0;
}

.logo-link:hover {
  opacity: 0.8;  /* Subtle hover effect */
}
```

---

## Accessibility
- Logo is linked to homepage for easy navigation
- Screen reader text hidden (sr-only class)
- High contrast in both light and dark themes
- Touch-friendly target size (140×35px minimum)

---

## Design Inspiration
- **Stripe**: Minimal icon + typography
- **Linear**: Clean geometric shapes
- **Vercel**: Professional, flat design
- **Apple**: System font usage, elegant simplicity

---

## Favicon & App Icon
The icon-only version (`logo-icon.svg`) is used as:
- Browser tab icon
- Bookmarks
- PWA app icon
- OS shortcuts

This maintains brand consistency across all touchpoints while being recognizable at small sizes (16px+).

---

## Future Extensions
The design system allows for:
- Icon animation (nodes could pulse on connection events)
- Gradient overlays for special contexts
- Icon variants (connected, disconnected, error states)
- Monochrome/inverse versions for different backgrounds
