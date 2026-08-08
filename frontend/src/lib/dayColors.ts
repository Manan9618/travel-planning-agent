// A sequential blue -> amber ramp (HSL hue 214 -> 36, s=58%, l=46%), so day
// color reads as a natural progression through the trip. Mirrors
// DAY_COLORS in travel_map_generator.py exactly (kept in sync by hand), so
// the live map preview, the exported Folium map, and the PDF's day badges
// all agree on which color means "Day N".
export const DAY_COLORS = [
  '#316cb9',
  '#3199b9',
  '#31b9ad',
  '#31b980',
  '#31b953',
  '#3cb931',
  '#69b931',
  '#96b931',
  '#b9b031',
  '#b98331',
]

export function dayColor(dayNumber: number): string {
  return DAY_COLORS[(dayNumber - 1) % DAY_COLORS.length]
}
