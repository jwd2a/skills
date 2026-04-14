#!/bin/bash
# Drawer API helper — manages drawers and places via Supabase REST API
# Uses service role key (bypasses RLS) for the "drawer" brand account
#
# Usage:
#   drawer-api.sh list-drawers
#   drawer-api.sh get-drawer <slug-or-id>
#   drawer-api.sh get-places <drawer-id>
#   drawer-api.sh create-drawer <name> <emoji> [description]
#   drawer-api.sh add-place <drawer-id> <google_place_id> <name> <address> <lat> <lng> [notes] [what_to_get] [who_recommended] [place_types]
#   drawer-api.sh verify-url <slug>
#   drawer-api.sh search-drawers <query>
#   drawer-api.sh delete-place <place-id>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKSPACE_DIR="${SCRIPT_DIR}/../../.."

# Load env
if [ -f "$WORKSPACE_DIR/.env" ]; then
  export $(grep -E '^(SUPABASE_URL|SUPABASE_SERVICE_ROLE_KEY)=' "$WORKSPACE_DIR/.env" | xargs)
fi

: "${SUPABASE_URL:?Set SUPABASE_URL in .env}"
: "${SUPABASE_SERVICE_ROLE_KEY:?Set SUPABASE_SERVICE_ROLE_KEY in .env}"

DRAWER_USER_ID="24b55cde-afcf-4e8b-8e8b-7b75d49c7801"
API="${SUPABASE_URL}/rest/v1"
AUTH=(-H "apikey: ${SUPABASE_SERVICE_ROLE_KEY}" -H "Authorization: Bearer ${SUPABASE_SERVICE_ROLE_KEY}")

cmd="${1:?Usage: drawer-api.sh <command> [args]}"
shift

case "$cmd" in
  list-drawers)
    curl -s "${API}/drawers?user_id=eq.${DRAWER_USER_ID}&select=id,name,slug,emoji,is_public,description&order=created_at.desc" \
      "${AUTH[@]}" -H "Content-Type: application/json"
    ;;

  get-drawer)
    val="${1:?Provide slug or UUID}"
    # Try slug first, then id
    if [[ "$val" =~ ^[0-9a-f-]{36}$ ]]; then
      curl -s "${API}/drawers?id=eq.${val}&select=*" "${AUTH[@]}" -H "Content-Type: application/json"
    else
      curl -s "${API}/drawers?user_id=eq.${DRAWER_USER_ID}&slug=eq.${val}&select=*" "${AUTH[@]}" -H "Content-Type: application/json"
    fi
    ;;

  get-places)
    drawer_id="${1:?Provide drawer_id}"
    curl -s "${API}/places?drawer_id=eq.${drawer_id}&select=id,name,address,latitude,longitude,notes,what_to_get,who_recommended,google_place_id,place_types,status&order=created_at.desc" \
      "${AUTH[@]}" -H "Content-Type: application/json"
    ;;

  create-drawer)
    name="${1:?Provide name}"
    emoji="${2:?Provide emoji}"
    desc="${3:-}"
    # Generate slug from name
    slug=$(echo "$name" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g' | sed 's/-\+/-/g' | sed 's/^-\|-$//g')
    
    payload=$(jq -n \
      --arg uid "$DRAWER_USER_ID" \
      --arg name "$name" \
      --arg emoji "$emoji" \
      --arg slug "$slug" \
      --arg desc "$desc" \
      '{user_id: $uid, name: $name, emoji: $emoji, slug: $slug, is_public: true, description: (if $desc == "" then null else $desc end)}')
    
    curl -s "${API}/drawers" "${AUTH[@]}" \
      -H "Content-Type: application/json" \
      -H "Prefer: return=representation" \
      -d "$payload"
    ;;

  add-place)
    drawer_id="${1:?Provide drawer_id}"
    google_place_id="${2:?Provide google_place_id}"
    name="${3:?Provide name}"
    address="${4:-}"
    lat="${5:-0}"
    lng="${6:-0}"
    notes="${7:-}"
    what_to_get="${8:-}"
    who_recommended="${9:-}"
    place_types="${10:-}"

    payload=$(jq -n \
      --arg did "$drawer_id" \
      --arg uid "$DRAWER_USER_ID" \
      --arg gpid "$google_place_id" \
      --arg name "$name" \
      --arg addr "$address" \
      --argjson lat "$lat" \
      --argjson lng "$lng" \
      --arg notes "$notes" \
      --arg wtg "$what_to_get" \
      --arg wr "$who_recommended" \
      --arg pt "$place_types" \
      '{
        drawer_id: $did, user_id: $uid, google_place_id: $gpid, name: $name,
        address: (if $addr == "" then null else $addr end),
        latitude: $lat, longitude: $lng,
        status: "recommended", is_public: true,
        notes: (if $notes == "" then null else $notes end),
        what_to_get: (if $wtg == "" then null else $wtg end),
        who_recommended: (if $wr == "" then null else $wr end),
        place_types: (if $pt == "" then null else ($pt | split(",")) end)
      }')

    curl -s "${API}/places" "${AUTH[@]}" \
      -H "Content-Type: application/json" \
      -H "Prefer: return=representation" \
      -d "$payload"
    ;;

  verify-url)
    slug="${1:?Provide slug}"
    username="${2:-drawer}"
    url="https://ilovedrawer.com/d/${username}/${slug}"
    # Check if drawer exists in DB with this slug under the specified user
    if [ "$username" = "drawer" ]; then
      result=$(curl -s "${API}/drawers?user_id=eq.${DRAWER_USER_ID}&slug=eq.${slug}&select=id,name,slug" \
        "${AUTH[@]}" -H "Content-Type: application/json")
    else
      result=$(curl -s "${API}/drawers?slug=eq.${slug}&select=id,name,slug,profiles!inner(username)&profiles.username=eq.${username}" \
        "${AUTH[@]}" -H "Content-Type: application/json")
    fi
    count=$(echo "$result" | jq 'length')
    if [ "$count" -gt 0 ]; then
      echo "{\"exists\": true, \"url\": \"${url}\", \"drawer\": $(echo "$result" | jq '.[0]')}"
    else
      echo "{\"exists\": false, \"url\": \"${url}\", \"message\": \"No drawer found with slug '${slug}' for user '${username}'\"}"
    fi
    ;;

  search-drawers)
    query="${1:?Provide search query}"
    curl -s "${API}/drawers?user_id=eq.${DRAWER_USER_ID}&name=ilike.*${query}*&select=id,name,slug,emoji,description" \
      "${AUTH[@]}" -H "Content-Type: application/json"
    ;;

  delete-place)
    place_id="${1:?Provide place_id}"
    curl -s -X DELETE "${API}/places?id=eq.${place_id}" "${AUTH[@]}" \
      -H "Content-Type: application/json"
    echo '{"deleted": true}'
    ;;

  *)
    echo "Unknown command: $cmd" >&2
    echo "Commands: list-drawers, get-drawer, get-places, create-drawer, add-place, verify-url, search-drawers, delete-place" >&2
    exit 1
    ;;
esac
