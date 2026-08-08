const EARTH_RADIUS_KM = 6371

/** Great-circle distance in km — an honest "as the crow flies" estimate,
 * not real routing (the backend's DistanceMatrixTool does real driving/
 * transit routing server-side; this is just for a quick in-UI hint). */
export function haversineKm(a: [number, number], b: [number, number]): number {
  const [lat1, lng1] = a
  const [lat2, lng2] = b
  const dLat = ((lat2 - lat1) * Math.PI) / 180
  const dLng = ((lng2 - lng1) * Math.PI) / 180
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) * Math.cos((lat2 * Math.PI) / 180) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.sqrt(h))
}

const WALK_KM_PER_HOUR = 5

export function estimatedWalkMinutes(km: number): number {
  return Math.round((km / WALK_KM_PER_HOUR) * 60)
}
