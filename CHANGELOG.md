# Changelog

## 0.5.1 - 2026-05-20
- Tightened dashboard profile cards to a compact dating-app style layout
- Limited card tag display to three visible tags with overflow shown as `+N`
- Added ranked tag priorities in Settings so card tags are chosen by priority order
- Added editable tag and status sort order fields in Settings

## 0.5.0 - 2026-05-20
- Added profile intake parser action that builds a draft bio from profile intake uploads
- Added stored generated bio output area on profile pages
- Added conversation parser action that combines message tracking uploads into one readable thread
- Added conversation search on profile pages
- Added automatic text import for uploaded `.txt` files
- Added in-place editing for reusable tags and status choices in Settings
- Added distance filtering on the dashboard
- Redirected bulk update actions back to the Manage screen

## 0.4.0 - 2026-05-20
- Added dashboard search and filters for app, name, location, age, status, and tags
- Added editable profile details layout with stronger mobile-friendly sections
- Added Initial Review Ready workflow with structured overview output
- Added better upload handling with image thumbnails and upload acknowledgment timeline entries
- Added saved initial options, follow-up options, drafts, and sent message history
- Added timeline editing and delete actions
- Added profile export to external exports storage
- Added bulk dashboard updates for status and tags
- Added duplicate profile detection on the dashboard
- Added reminder calendar groups from follow-up reminder notes
- Added ZIP bundle export with profile text and uploads
- Added real reminder dates for profiles
- Added duplicate merge action from the dashboard
- Added PDF export for profile summaries
- Removed timeline, review, suggested message, and sent message workflow from the UI
- Reworked uploads into profile intake, general photos, and message tracking lanes
- Added per-upload metadata fields for copied or extracted text to support future automation
- Moved bulk profile updates to a separate Manage screen
- Rebuilt the dashboard into a browse-first card layout with photo, name, age, location, distance, status, and tags
- Added distance as a profile field in create, edit, browse, and manage views
- Added Settings editing for tags and status choices, not just add/remove

## 0.1.0 - 2026-05-20
- Initial project setup
- Added Docker Compose self-hosted app skeleton
- Added login, dashboard, create profile, profile detail, uploads, notes, and timeline areas
- Added external data storage structure
- Added backup and restore scripts
- Added README, roadmap, env example, and demo data support
