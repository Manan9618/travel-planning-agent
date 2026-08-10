import type { TravelPreferences } from '@/types/api'

// Mirrors PDFGenerator._destination_label (backend) — kept in sync by hand,
// same cross-language duplication this project already accepts elsewhere
// (e.g. DAY_COLORS/dayColors.ts).
export function destinationLabel(prefs: TravelPreferences): string {
  const destinations = [prefs.destination, ...prefs.additional_destinations]
  if (destinations.length === 1) return destinations[0]
  if (destinations.length === 2) return destinations.join(' & ')
  return `${destinations.slice(0, -1).join(', ')} & ${destinations[destinations.length - 1]}`
}
