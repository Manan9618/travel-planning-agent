// Mirrors src/travel_agent/api/schemas.py and models/core.py's JSON wire
// format exactly (field names/shapes must match what FastAPI actually
// serializes) — kept as one hand-written file rather than codegen since the
// backend has no OpenAPI-schema-to-TS pipeline yet.

export const PLANNING_STEPS = [
  'parse_preferences',
  'search_flights',
  'search_hotels',
  'find_attractions',
  'find_restaurants',
  'check_weather',
  'build_itinerary',
  'check_conflicts',
  'optimize_budget',
  'generate_map',
  'generate_pdf',
] as const

export type PlanningStep = (typeof PLANNING_STEPS)[number]

export const STEP_LABELS: Record<PlanningStep, string> = {
  parse_preferences: 'Understanding your request',
  search_flights: 'Searching flights',
  search_hotels: 'Searching hotels',
  find_attractions: 'Finding attractions',
  find_restaurants: 'Finding restaurants',
  check_weather: 'Checking weather',
  build_itinerary: 'Building your itinerary',
  check_conflicts: 'Checking for conflicts',
  optimize_budget: 'Optimizing your budget',
  generate_map: 'Generating map',
  generate_pdf: 'Generating PDF',
}

export interface TravelPreferences {
  origin: string | null
  destination: string
  start_date: string | null
  end_date: string | null
  duration_days: number | null
  travelers: number
  budget_total: number | null
  budget_currency: string
  budget_tier: string | null
  trip_style: string | null
  pace: string
  interests: string[]
  must_see: string[]
  dietary_restrictions: string[]
  accessibility_needs: string[]
  priority_weights: Record<string, number>
  raw_text: string
}

export interface HotelOption {
  name: string
  address: string
  lat: number
  lng: number
  rating: number | null
  price_per_night: number
  currency: string
  amenities: string[]
  booking_link: string | null
  is_mock_data: boolean
}

export interface FlightOption {
  airline: string
  flight_number: string | null
  origin: string
  destination: string
  departure_time: string
  arrival_time: string
  duration_minutes: number
  stops: number
  price: number
  currency: string
  booking_link: string | null
  has_exact_time: boolean
  is_mock_data: boolean
}

export interface WeatherForecast {
  day: string
  condition: string
  temp_high_c: number
  temp_low_c: number
  rain_probability: number
  wind_speed_kph: number
  comfort_score: number
}

export interface ItineraryItem {
  time_slot: string
  start_time: string
  end_time: string
  activity_type: string
  title: string
  category: string | null
  location: string | null
  lat: number | null
  lng: number | null
  cost: number | null
  notes: string | null
}

export interface DayPlan {
  day_number: number
  date: string
  items: ItineraryItem[]
  weather: WeatherForecast | null
  warnings: string[]
}

export interface Itinerary {
  preferences: TravelPreferences
  days: DayPlan[]
  flights: FlightOption[]
  hotel: HotelOption | null
  budget_summary: unknown | null
}

export interface CategoryEvaluation {
  category: string
  allocated: number
  actual: number
  difference: number
  status: 'under' | 'on_target' | 'over'
}

export interface BudgetEvaluation {
  allocation: { flights: number; hotel: number; food: number; activities: number }
  categories: CategoryEvaluation[]
  total_allocated: number
  total_actual: number
  adherence_score: number | null
  suggestions: string[]
}

export interface Conflict {
  day_number: number
  conflict_type: string
  description: string
  auto_resolvable: boolean
}

// --- HTTP request/response bodies -------------------------------------------

export interface PlanRequest {
  raw_text: string
}

export interface PlanResponse {
  session_id: string
  status: string
}

export interface ResumeRequest {
  approved: boolean
}

export interface RefineRequest {
  session_id: string
  raw_text: string
}

export type SessionStatus = 'running' | 'awaiting_review' | 'completed' | 'failed'

export interface SessionStateResponse {
  session_id: string
  status: SessionStatus
  completed_steps: string[]
  errors: string[]
  preferences: TravelPreferences | null
  itinerary: Itinerary | null
  unresolved_conflicts: Conflict[]
  budget_evaluation: BudgetEvaluation | null
  pdf_path: string | null
  map_html_available: boolean
}

// --- WebSocket events --------------------------------------------------------

export interface StepCompletedEvent {
  type: 'step_completed'
  step: string
  errors: string[]
}

export interface NarrationTokenEvent {
  type: 'narration_token'
  token: string
}

export interface AwaitingReviewEvent {
  type: 'awaiting_review'
  next: string[]
}

export interface DoneEvent {
  type: 'done'
}

export interface ErrorEvent {
  type: 'error'
  message: string
}

export type WsEvent =
  | StepCompletedEvent
  | NarrationTokenEvent
  | AwaitingReviewEvent
  | DoneEvent
  | ErrorEvent
