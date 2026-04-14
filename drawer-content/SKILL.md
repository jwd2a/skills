---
name: drawer-content
description: Create, retrieve, and manage Drawer app content (drawers and places) via the Supabase API. Use when creating drawers for social media posts, verifying drawer URLs exist before posting, adding places to drawers, or listing existing drawer content. Always use this skill before referencing any drawer URL in a post — create the drawer first, verify it, then post.
---

# Drawer Content Management

Manage drawers and places in the Drawer app's production Supabase database using the `drawer` brand account. All operations use the service role key from workspace `.env`.

## Critical Rule

**NEVER reference a drawer URL (`ilovedrawer.com/d/{username}/{slug}`) without first verifying it exists.** The screenshot of a 404 page is why this skill exists.

## Workflow: Creating Content for a Post

1. **Check existing drawers** — maybe one already fits
2. **Create the drawer** if needed (name, emoji, description)
3. **Look up places** on Google Places API to get `google_place_id`, coords, address
4. **Add places** to the drawer
5. **Verify the URL** loads before using it anywhere
6. **Then create the post/content** referencing the verified URL

## Scripts

All scripts are in `scripts/` relative to this skill directory. Run with bash.

### drawer-api.sh — Main API interface

```bash
# List all drawers under the brand account
bash scripts/drawer-api.sh list-drawers

# Get a specific drawer by slug or UUID
bash scripts/drawer-api.sh get-drawer best-coffee-in-tampa

# Get places in a drawer
bash scripts/drawer-api.sh get-places <drawer-id>

# Create a new drawer
bash scripts/drawer-api.sh create-drawer "Sushi in Tampa Bay" "🍣" "The best sushi spots across Tampa Bay"

# Add a place (drawer_id, google_place_id, name, address, lat, lng, notes, what_to_get, who_recommended, place_types)
bash scripts/drawer-api.sh add-place <drawer-id> <google_place_id> "Place Name" "123 Main St" 27.95 -82.45 "Great omakase" "Chef's special" "" "restaurant,food"

# Verify a URL will resolve (checks DB for slug, default username=drawer)
bash scripts/drawer-api.sh verify-url sushi-in-tampa-bay
# Or verify for a specific user
bash scripts/drawer-api.sh verify-url tampa justin

# Search drawers by name
bash scripts/drawer-api.sh search-drawers "coffee"

# Delete a place
bash scripts/drawer-api.sh delete-place <place-id>
```

### google-places-lookup.sh — Get Google Place IDs

```bash
# Look up a place to get google_place_id, coords, address
bash scripts/google-places-lookup.sh "Locale Market, St Petersburg FL"
```

Returns: `google_place_id`, `name`, `address`, `latitude`, `longitude`, `types`

**Important:** Every place needs a `google_place_id`. Use this script before `add-place`.

## Schema Reference

See `references/schema.md` for full table schemas, the brand account ID, and URL structure.

## Known Issues

- URLs are username-namespaced: `/d/{username}/{slug}` — the brand account username is `drawer`, so URLs are like `ilovedrawer.com/d/drawer/best-coffee-in-tampa`

## Tips

- Slugs are auto-generated from the name (lowercase, hyphens). Predict the slug before creating to avoid surprises.
- `google_place_id` + `drawer_id` must be unique — can't add the same place twice to one drawer.
- All drawers/places are created as `is_public: true` by default.
- Places need `status: "recommended"` to appear in the feed.
