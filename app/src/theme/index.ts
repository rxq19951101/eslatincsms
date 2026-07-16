/** Presentation-only design tokens. Business config must not live here. */
export const palette = {
  ink: '#17211B', muted: '#68736C', subtle: '#919A94', canvas: '#F7F8F6',
  surface: '#FFFFFF', border: '#E3E7E3', brand: '#087F5B',
  brandStrong: '#066B4D', brandSoft: '#E8F5EF', info: '#4263EB',
  warning: '#B86500', danger: '#C92A2A',
} as const;

export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 } as const;
export const radius = { sm: 8, md: 12, lg: 16, xl: 20, full: 999 } as const;
export const typography = {
  caption: 12, body: 14, label: 16, title: 24, display: 28,
  regular: '400' as const, medium: '500' as const,
  semibold: '600' as const, bold: '700' as const,
} as const;
export const shadow = {
  raised: {
    shadowColor: '#000000', shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07, shadowRadius: 6, elevation: 2,
  },
} as const;
export const theme = { palette, spacing, radius, typography, shadow } as const;

