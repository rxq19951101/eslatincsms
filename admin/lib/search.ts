/**
 * Match API-backed values without assuming nullable fields are strings.
 * An empty query intentionally matches every record.
 */
export function matchesSearchQuery(
  query: string | null | undefined,
  values: readonly unknown[],
): boolean {
  const needle = String(query ?? '').trim().toLowerCase();
  if (!needle) return true;
  return values.some((value) => String(value ?? '').toLowerCase().includes(needle));
}
