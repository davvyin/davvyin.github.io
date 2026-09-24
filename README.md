# Dawei Yin's portfolio

The original React/Tailwind frontend is served by Django 5.2 LTS. Content is stored in a database and edited in Django admin. Use SQLite locally and PostgreSQL for hosting. Django, the API, the admin, and the production React build share one origin.

## Local development

Requirements: Python 3.10+ (3.13 recommended) and Node.js 22 LTS with npm.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
python backend/manage.py migrate
python backend/manage.py createsuperuser
python backend/manage.py runserver 127.0.0.1:8000
```

In a second terminal:

```sh
npm ci
npm start
```

Open http://localhost:3000. The footer's **Admin** link opens http://localhost:3000/admin/; you can also use http://127.0.0.1:8000/admin/. Log in with the superuser you created. React's development proxy forwards API, admin, and backend image requests to Django.

To serve everything from Django locally:

```sh
npm run build
python backend/manage.py collectstatic --noinput
python backend/manage.py runserver 127.0.0.1:8000
```

Open http://127.0.0.1:8000. Existing routes (`/about`, `/projects`, `/technologies`, `/contact`) work on direct visits and refreshes.

## Editing content

At `/admin/` you can manage:

- **Site profile:** name, biography, tagline, profile image, logo, contact text, coding challenges link, and footer.
- **Site text and labels:** all visible page headings, home greeting, navigation labels, technology page introduction, project card labels, and footer admin label.
- **Projects:** descriptions, images, keywords, preview links, source links, ordering, and visibility.
- **Experiences:** work and education entries, ordering, and visibility.
- **Technologies:** technology/tool groups, icons, ordering, and visibility.
- **Social links:** URLs and visibility; the current header displays LinkedIn and GitHub, as in the original frontend.
- **Users and groups:** delegated staff access with Django's model permissions.

The original content is imported once by migration `0002_initial_content`. Subsequent migrations do not overwrite edits or restore deleted items. `src/Details.js` remains only as a historical reference; edit live content in the admin. Reload the public page after saving changes. Empty lists stay empty, and unavailable API responses show a retry action.

Images accept an HTTPS URL or a site-relative path, such as `/static/portfolio/profile.jpg`. Existing assets are retained in `src/assets/`. New local assets require rebuilding/redeploying; remote image URL changes do not. File uploads are not included.

No default admin account or password is shipped. To reset your account's password, run `python backend/manage.py changepassword USERNAME` (use `docker compose exec web` before the command when hosted).

## Hosting with Docker and PostgreSQL

For a low-memory Raspberry Pi, see the [native deployment instructions](deploy/raspberrypi/README.md) using systemd, Gunicorn, Nginx, and PostgreSQL.

**GitHub Pages cannot run Django.** Host the full application on a VPS or a platform that runs containers and provides PostgreSQL. The former GitHub Pages deployment scripts have been removed because the frontend now requires the API.

The supplied Compose setup uses PostgreSQL 17 with a persistent volume and a non-root Gunicorn web container. Its web port binds only to the host's loopback interface; terminate HTTPS through a reverse proxy on the host. `Caddyfile.example` shows the proxy configuration. Point your domain's DNS to your server and configure Caddy with that hostname to obtain HTTPS certificates.

On the server:

```sh
cp .env.production.example .env
python3 -c 'import secrets; print(secrets.token_hex(32))'
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Put the two independently generated values in `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD`, and replace the example domain in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. Use hexadecimal database passwords with this Compose URL configuration. Keep `.env` private and out of Git. Keep the same secret and database password across deployments.

```sh
docker compose build
docker compose up -d db
docker compose run --rm web python backend/manage.py migrate --noinput
docker compose run --rm web python backend/manage.py createsuperuser
docker compose up -d web
docker compose exec web python backend/manage.py check --deploy --fail-level WARNING
```

Configure the host's HTTPS reverse proxy, then visit `https://YOUR_DOMAIN/` and `https://YOUR_DOMAIN/admin/`. `GET /healthz/` checks database connectivity; `GET /api/content/` returns public content. The public API accepts only GET and HEAD.

Production defaults require a secret, explicit hosts, and a PostgreSQL URL, and enable HTTPS redirects, secure cookies, HSTS, and CSRF protection. `DJANGO_TRUST_PROXY=true` is appropriate only when the trusted proxy overwrites incoming `X-Forwarded-Proto` headers and clients cannot bypass it. HSTS includes subdomains: all subdomains must support HTTPS before using these defaults.

For a managed container host, build the same Dockerfile, provide its PostgreSQL connection URL as `DATABASE_URL` (including the provider's required TLS options), set the Django environment variables from `.env.production.example`, and configure the service's internal port as 8000. Run migrations as a release job and create the administrator via the host's shell. Configure proxy trust to match that host. The image already contains the frontend and collected static assets.

### Updating and backing up

Back up PostgreSQL before applying schema changes:

```sh
docker compose exec -T db pg_dump -U portfolio -d portfolio -Fc > portfolio-backup.dump
```

Keep backups off the server as well. To verify a backup without replacing the live database:

```sh
docker compose exec db createdb -U portfolio portfolio_restore
docker compose exec -T db pg_restore -U portfolio -d portfolio_restore --no-owner < portfolio-backup.dump
```

Inspect the restored database before using it for recovery. The named volume survives `docker compose down`; `docker compose down -v` deletes it. Changing the `.env` password alone does not rotate an existing database user's password.

For an update, build the image, run migrations once, then recreate the web container:

```sh
docker compose build
docker compose run --rm web python backend/manage.py migrate --noinput
docker compose up -d web
```

Use a maintenance window for incompatible schema changes. Install supported security updates regularly; Python dependencies are constrained to compatible release families.

## Verification

With the local `.env` created and the virtual environment active:

```sh
CI=true npm test -- --watchAll=false --runInBand
CI=true GENERATE_SOURCEMAP=false npm run build
python backend/manage.py collectstatic --noinput
python backend/manage.py makemigrations --check --dry-run
python backend/manage.py test portfolio
```

The backend tests include initial data, ordering/visibility, empty lists, URL validation, read-only API behavior, staff permissions, CSRF-protected admin edits, migration preservation, deep links, database health, and production static assets. Build and collect static files before running them. The frontend tests cover loading, failure/retry, invalid responses, cancellation, empty projects, and page navigation using API content.

Set `DATABASE_URL` to a disposable PostgreSQL database to run the same backend tests on PostgreSQL. Django creates and drops a separate test database; the test role needs database-creation permission. `.github/workflows/test.yml` runs these checks with PostgreSQL 17, Python 3.13, and Node 22.

The retained Create React App dependency tree has existing npm audit advisories and outdated browser metadata. Migrating the frontend build tool is a separate maintenance task; Node/npm build tools are excluded from the production image.

## Reusable skill

`skills/portfolio-backend/SKILL.md` captures this implementation and verification workflow. A personal copy is installed as `$portfolio-backend`. The repository copy can be reused by copying its folder into your Codex skills directory.
