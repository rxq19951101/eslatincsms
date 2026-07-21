/** Presentation-only design tokens. Business config must not live here. */
export const palette = {
  ink: '#102A43', muted: '#5B7083', subtle: '#8799A8', canvas: '#F5FAFD',
  surface: '#FFFFFF', border: '#D8E7F0', brand: '#0876BE',
  brandStrong: '#07598F', brandSoft: '#E7F7FC', info: '#22AFC4',
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
