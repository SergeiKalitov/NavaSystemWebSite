# Forma on Render

This version adds a private sign-in page and a shared SQLite diary. It is prepared for deployment and is not yet live.

## Deployment

Create a dedicated Render Python web service from this folder in a GitHub repository. Use `pip install -r requirements.txt` to build and `gunicorn app:app --workers 1 --threads 4 --bind 0.0.0.0:$PORT --access-logfile -` to start. Use the smallest paid compute plan and attach a 1 GB disk at `/var/data`. The health check path is `/healthz`.

Set `FORMA_LOGIN`, `FORMA_PASSWORD_HASH` and a long random `SESSION_SECRET` in Render's environment settings. Keep credentials out of GitHub. Generate a password hash with Werkzeug's `generate_password_hash`. Only the hash belongs in Render; the password is for the user.

The database is `/var/data/forma.sqlite3`. It persists through restarts and deployments. There is no public signup. Sessions use secure, HTTP-only cookies; changes require CSRF tokens. Writes check a revision number to avoid overwriting another device's changes.

The safest simple deployment serves the whole app from Render, with its login and API on the same origin. The existing `nava-system.com/forma/` page can redirect to its Render URL once deployed. Keeping that exact URL in the address bar needs a reverse proxy; GitHub Pages cannot proxy requests.

## Existing records

Download records from the current diary before switching. After signing in to the new version, use **Load data** to import the exported JSON. Nothing is uploaded automatically from a browser.

## Backups

Use **Download data** for a portable backup. Before restoring or moving the SQLite database, make a consistent database backup with SQLite's backup API. Render disk snapshots are not a substitute for database backups.
