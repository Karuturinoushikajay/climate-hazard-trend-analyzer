"""Featured cities and regions.

State and region boxes are approximate extents used to place sample points. They
are not legal boundaries. Boxes wider or taller than 15 degrees are rejected by
the analyzer, so very large territories are left to a custom box the user draws.
"""

from __future__ import annotations

City = dict
Region = dict


def _city(region_id: str, name: str, country: str, admin: str, latitude: float, longitude: float) -> City:
    return {
        "id": region_id,
        "name": name,
        "kind": "city",
        "country": country,
        "admin": admin,
        "latitude": latitude,
        "longitude": longitude,
        "bbox": None,
    }


def _region(
    region_id: str,
    name: str,
    country: str,
    west: float,
    south: float,
    east: float,
    north: float,
) -> Region:
    return {
        "id": region_id,
        "name": name,
        "kind": "region",
        "country": country,
        "admin": name,
        "latitude": round((south + north) / 2, 4),
        "longitude": round((west + east) / 2, 4),
        "bbox": {"west": west, "south": south, "east": east, "north": north},
    }


CITIES: list[City] = [
    _city("delhi", "Delhi", "India", "Delhi", 28.6139, 77.2090),
    _city("mumbai", "Mumbai", "India", "Maharashtra", 19.0760, 72.8777),
    _city("chennai", "Chennai", "India", "Tamil Nadu", 13.0827, 80.2707),
    _city("kolkata", "Kolkata", "India", "West Bengal", 22.5726, 88.3639),
    _city("bengaluru", "Bengaluru", "India", "Karnataka", 12.9716, 77.5946),
    _city("hyderabad", "Hyderabad", "India", "Telangana", 17.3850, 78.4867),
    _city("ahmedabad", "Ahmedabad", "India", "Gujarat", 23.0225, 72.5714),
    _city("jaipur", "Jaipur", "India", "Rajasthan", 26.9124, 75.7873),
    _city("lucknow", "Lucknow", "India", "Uttar Pradesh", 26.8467, 80.9462),
    _city("nagpur", "Nagpur", "India", "Maharashtra", 21.1458, 79.0882),
    _city("phoenix", "Phoenix", "United States", "Arizona", 33.4484, -112.0740),
    _city("houston", "Houston", "United States", "Texas", 29.7604, -95.3698),
    _city("los-angeles", "Los Angeles", "United States", "California", 34.0522, -118.2437),
    _city("new-york", "New York", "United States", "New York", 40.7128, -74.0060),
    _city("chicago", "Chicago", "United States", "Illinois", 41.8781, -87.6298),
    _city("london", "London", "United Kingdom", "England", 51.5072, -0.1276),
    _city("paris", "Paris", "France", "Île-de-France", 48.8566, 2.3522),
    _city("madrid", "Madrid", "Spain", "Community of Madrid", 40.4168, -3.7038),
    _city("athens", "Athens", "Greece", "Attica", 37.9838, 23.7275),
    _city("cairo", "Cairo", "Egypt", "Cairo", 30.0444, 31.2357),
    _city("dubai", "Dubai", "United Arab Emirates", "Dubai", 25.2048, 55.2708),
    _city("tokyo", "Tokyo", "Japan", "Tokyo", 35.6762, 139.6503),
    _city("beijing", "Beijing", "China", "Beijing", 39.9042, 116.4074),
    _city("singapore", "Singapore", "Singapore", "Singapore", 1.3521, 103.8198),
    _city("sydney", "Sydney", "Australia", "New South Wales", -33.8688, 151.2093),
    _city("cape-town", "Cape Town", "South Africa", "Western Cape", -33.9249, 18.4241),
    _city("lagos", "Lagos", "Nigeria", "Lagos", 6.5244, 3.3792),
    _city("sao-paulo", "São Paulo", "Brazil", "São Paulo", -23.5558, -46.6396),
]

REGIONS: list[Region] = [
    _region("nct-delhi", "National Capital Territory of Delhi", "India", 76.84, 28.40, 77.35, 28.88),
    _region("rajasthan", "Rajasthan", "India", 69.50, 23.06, 78.25, 30.12),
    _region("gujarat", "Gujarat", "India", 68.20, 20.12, 74.48, 24.70),
    _region("maharashtra", "Maharashtra", "India", 72.65, 15.60, 80.90, 22.03),
    _region("karnataka", "Karnataka", "India", 74.05, 11.55, 78.59, 18.45),
    _region("tamil-nadu", "Tamil Nadu", "India", 76.23, 8.08, 80.35, 13.55),
    _region("uttar-pradesh", "Uttar Pradesh", "India", 77.08, 23.87, 84.63, 30.40),
    _region("west-bengal", "West Bengal", "India", 85.82, 21.54, 89.88, 27.22),
    _region("telangana", "Telangana", "India", 77.25, 15.80, 81.30, 19.92),
    _region("punjab-in", "Punjab", "India", 73.88, 29.54, 76.94, 32.50),
    _region("kerala", "Kerala", "India", 74.86, 8.18, 77.41, 12.79),
    _region("arizona", "Arizona", "United States", -114.81, 31.33, -109.05, 37.00),
    _region("california", "California", "United States", -124.41, 32.53, -114.13, 42.01),
    _region("england", "England", "United Kingdom", -5.72, 49.96, 1.77, 55.81),
]

FEATURED_BY_ID: dict[str, dict] = {item["id"]: item for item in [*CITIES, *REGIONS]}


def sample_points(
    latitude: float,
    longitude: float,
    bbox: tuple[float, float, float, float] | None,
) -> list[tuple[float, float]]:
    """Snap a point to 0.01°, or place up to four interior points in a box."""

    def snap(lat: float, lon: float) -> tuple[float, float]:
        return (round(lat, 2), round(lon, 2))

    if bbox is None:
        return [snap(latitude, longitude)]
    west, south, east, north = bbox
    if west >= east or south >= north:
        raise ValueError("Bounding box is inverted. West must be left of east, and south below north.")
    if east - west > 15 or north - south > 15:
        raise ValueError("Bounding box is too large. Keep each side within 15 degrees so the sample stays regional.")
    if east - west <= 1 and north - south <= 1:
        return [snap((south + north) / 2, (west + east) / 2)]
    points: list[tuple[float, float]] = []
    for lat_fraction in (1 / 3, 2 / 3):
        for lon_fraction in (1 / 3, 2 / 3):
            point = snap(
                south + (north - south) * lat_fraction,
                west + (east - west) * lon_fraction,
            )
            if point not in points:
                points.append(point)
    if not points:
        raise ValueError("Could not place sample points in that box.")
    return points
