"""Shared geographic distance calculations for bot replies and map details."""
import math


def distance_km(start, end):
    lat1, lon1, lat2, lon2 = map(math.radians, (*start, *end))
    value = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(max(0.0, min(1.0, value))))
