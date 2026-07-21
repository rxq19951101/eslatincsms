const CONNECTOR_LABELS: Record<string, string> = {
  TYPE_1: 'Type 1',
  TYPE_2: 'Type 2',
  Type2: 'Type 2',
  CCS_1: 'CCS1',
  CCS_2: 'CCS2',
  CHADEMO: 'CHAdeMO',
  NACS: 'NACS',
  GB_T_AC: 'GB/T AC',
  GB_T_DC: 'GB/T DC',
  SCHUKO: 'Schuko',
};

export const connectorStandardLabel = (standard: string): string => {
  if (CONNECTOR_LABELS[standard]) return CONNECTOR_LABELS[standard];
  if (!standard || standard === 'UNKNOWN') return '';
  return standard.replace(/_/g, ' ');
};
