// Condenses OpenWeatherMap's `condition` string (Week 3's WeatherCheckerTool)
// into a terse METAR-style code for the day-card header — real data, just
// abbreviated, not invented.
const CONDITION_CODES: Record<string, string> = {
  Clear: 'CLR',
  Clouds: 'OVC',
  Rain: 'RAIN',
  Drizzle: 'DRZL',
  Thunderstorm: 'TSRA',
  Snow: 'SNOW',
  Mist: 'FG',
  Fog: 'FG',
  Haze: 'HZ',
}

export function weatherCode(condition: string): string {
  return CONDITION_CODES[condition] ?? condition.slice(0, 4).toUpperCase()
}
