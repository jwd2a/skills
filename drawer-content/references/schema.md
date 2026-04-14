# Drawer Database Schema

## Brand Account
- User ID: `24b55cde-afcf-4e8b-8e8b-7b75d49c7801`
- Username: `drawer`
- All content drawers are created under this account

## Tables

### drawers
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| user_id | uuid | FK → profiles.id |
| name | text | 1-100 chars |
| description | text | nullable |
| emoji | text | nullable |
| slug | text | auto-generated, unique per user |
| is_public | boolean | default true |
| gradient_index | integer | nullable |

### places
| Column | Type | Notes |
|--------|------|-------|
| id | uuid | PK |
| drawer_id | uuid | FK → drawers.id |
| user_id | uuid | FK → profiles.id |
| google_place_id | text | required, unique per drawer |
| name | text | required |
| address | text | nullable |
| latitude | double | nullable |
| longitude | double | nullable |
| place_types | text[] | nullable |
| status | text | 'recommended' or 'want_to_try' |
| is_public | boolean | default true |
| notes | text | nullable |
| who_recommended | text | nullable |
| what_to_get | text | nullable |
| source_url | text | nullable |

## URL Structure
- Public drawer page: `https://ilovedrawer.com/d/{username}/{slug}`
- Slug is derived from drawer name: lowercase, non-alphanumeric → hyphens
- Username comes from the profile that owns the drawer
- Brand account username: `drawer`
- Example: `https://ilovedrawer.com/d/drawer/best-coffee-in-tampa`

## Existing Drawers (as of creation)
- Best Coffee in Tampa (☕) → `/d/drawer/best-coffee-in-tampa`
- Date Night - Tampa Bay (🌹) → `/d/drawer/date-night-tampa-bay`
- Best Tacos in Tampa (🌮) → `/d/drawer/best-tacos-in-tampa`
- Kid-Friendly Eats (👨‍👩‍👧‍👦) → `/d/drawer/kid-friendly-eats`
- My Places → `/d/drawer/my-places`
