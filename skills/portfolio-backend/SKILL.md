---
name: portfolio-backend
description: Add or maintain a Django backend, editable admin content, and PostgreSQL deployment for an existing React portfolio while preserving its frontend. Use for portfolio backend integration and its verification, not unrelated redesigns.
---

# Portfolio backend

Preserve the existing frontend's pages, styling, assets, animations, and public URLs. Inspect the repository and its instructions before editing. On an already integrated site, extend the existing backend rather than scaffold a second one.

## Architecture

- Prefer a supported Django LTS release for its maintained ORM, authentication, and admin. Verify its support status when choosing or upgrading versions.
- Keep React and its current styling system. Serve the production build, public read-only JSON API, and `/admin/` from one origin. Proxy backend requests during frontend development.
- Use PostgreSQL for production, SQLite for local development, and environment variables for secrets and hosting settings.
- Use typed models for profile/contact details, social links, projects, experience, education, and technologies. Support ordering and visibility where useful. Preserve current images; image URLs are sufficient unless uploads are requested.
- Import existing content once with migrations or a non-destructive seed command. Repeated deployments must preserve admin edits and deletions.
- Treat the database as authoritative after integration: empty collections must remain empty, and fetch failures must not silently republish deleted content from JavaScript defaults.

## Implementation and delivery

1. Establish the frontend build and inspect existing content sources and routes.
2. Add Django models, migrations, read-only API serialization, and authenticated admin editing. Keep internal user and session data out of public responses.
3. Connect the existing components through a shared content provider; handle loading and failures without replacing the visual design. Preserve direct navigation and refresh of public routes, while unknown API/static paths return real errors.
4. Provide a production image using Gunicorn and static serving, PostgreSQL persistence, and explicit migration and administrator-creation commands. Document HTTPS termination, trusted proxy settings, backups/restores, and secret configuration. Never ship a default administrator password.
5. Test initial content, migrations, API ordering/visibility, unauthenticated write rejection, admin permissions and CSRF, an admin edit appearing in the public UI, frontend error/empty states, and production static assets. Run checks against PostgreSQL when available and identify any untested deployment layer.
6. Deliver setup and hosting instructions with exact tested commands and remaining limitations. GitHub Pages cannot execute Django; distinguish static-only publication from full application hosting.

Implementation authorization does not imply permission to purchase hosting, publish externally, or overwrite an existing production database.
