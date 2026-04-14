#!/bin/bash
# Look up a place on Google Places API to get google_place_id, coords, address
# NOTE: The Drawer Google API key is iOS-restricted and won't work from CLI.
# Use this script with a separate unrestricted API key, or look up places manually:
#   1. Search on Google Maps
#   2. The place_id is in the URL or can be found via the Place ID Finder
#   3. Or use web_search to find the Google Place ID
#
# Usage: GOOGLE_PLACES_API_KEY=<key> google-places-lookup.sh "place name, city"
#
# FALLBACK: If no API key available, manually construct place data:
#   - google_place_id: Use "manual_<slugified_name>" as a placeholder
#   - Get lat/lng from Google Maps URL
#   - Get address from Google Maps
set -euo pipefail

GOOGLE_API_KEY="${GOOGLE_PLACES_API_KEY:-}"

if [ -z "$GOOGLE_API_KEY" ]; then
  echo '{"error": "No GOOGLE_PLACES_API_KEY set. The Drawer API key is iOS-restricted. Use manual lookup — search Google Maps, extract place_id/coords/address."}' 
  exit 0
fi

query="${1:?Provide place name to search}"

response=$(curl -s "https://maps.googleapis.com/maps/api/place/textsearch/json?query=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$query'))")&key=${GOOGLE_API_KEY}")

echo "$response" | jq '{
  google_place_id: .results[0].place_id,
  name: .results[0].name,
  address: .results[0].formatted_address,
  latitude: .results[0].geometry.location.lat,
  longitude: .results[0].geometry.location.lng,
  types: .results[0].types
}'
