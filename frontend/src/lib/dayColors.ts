// Mirrors DAY_COLORS in travel_map_generator.py exactly, so the live map
// preview, the exported Folium map, and the PDF's day badges (Weeks 13/14)
// all agree on which color means "Day N".
export const DAY_COLORS = [
  '#3388ff', // blue (Leaflet's own default blue)
  '#2e8b2e', // green
  '#d33', // red
  '#800080', // purple
  '#ff8c00', // orange
  '#8b0000', // darkred
  '#5f9ea0', // cadetblue
  '#006400', // darkgreen
  '#ff69b4', // pink
  '#808080', // gray
]

export function dayColor(dayNumber: number): string {
  return DAY_COLORS[(dayNumber - 1) % DAY_COLORS.length]
}
