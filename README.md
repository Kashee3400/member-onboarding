# Member Onboarding

Multi-organization platform for enrolling members: form capture, approval
workflow, member code generation and PDF generation.

| Part | Stack | Status |
| --- | --- | --- |
| `backend/` | Python 3.14, Django 6.1, DRF, PostgreSQL, Redis, Celery | Workflow, PDFs, reports |
| `admin/` | Next.js 16, React 19, Tailwind CSS | Staff portal |
| `mobile/` | Flutter 3.47 package | Facilitator form. See `mobile/README.md` |

## Waiting on decisions

- **Entra login:** staff use email, password and MFA until the Azure tenant details arrive.
- **Member code series and the `01` segment:** both are settings with assumed defaults
  (10 and 01), and a new series restarting serials at 0001 is also an assumption.

## Backend setup

Requires [uv](https://docs.astral.sh/uv/), PostgreSQL 16+ and Redis.

1. Install dependencies:

   ```
   cd backend
   uv sync
   ```

2. Create the database and roles, as a PostgreSQL superuser:

   ```
   psql -U postgres -f scripts/bootstrap_db.sql -v owner_password=... -v app_password=...
   ```

3. Copy `.env.example` to `.env` and fill it in. The file explains how to generate each key.

4. Migrate, create the first organization, and run:

   ```
   uv run python manage.py migrate
   uv run python manage.py create_organization --name "Kashee Milk" --slug kashee --admin-email you@example.com
   uv run python manage.py runserver
   ```

API docs: <http://127.0.0.1:8000/api/docs/> when `EXPOSE_API_DOCS=true`.

## Importing existing members

Do this once before go-live, and again whenever ERP has added members outside this
system. Otherwise serials restart at 0001 and existing members can apply again. Repeating
it is safe: rows are updated in place and counters only move upward.

1. In `erp_master` (read-only against ERP):

   ```
   python manage.py export_members_for_onboarding /secure/path/members.csv
   ```

2. Here:

   ```
   uv run python manage.py import_legacy_members /secure/path/members.csv --organization kashee
   ```

3. Read the printed counts, then delete the CSV. It holds Aadhaar numbers in plain text.
   Only their keyed index is stored here.

Set the form prefix under Member code settings first: only application numbers with that
prefix move the form number counter. Rows with `invalid_aadhaar` or `without_aadhaar`
cannot be caught by the duplicate check.

## Admin portal setup

```
cd admin
npm install
copy .env.example .env.local
npm run dev
```

The browser only talks to this app. It keeps tokens in `httpOnly` cookies and forwards
API calls to the backend, so `BACKEND_URL` is a server-side setting.

The portal's design rules are in `admin/DESIGN.md`. Set `NEXT_PUBLIC_DEFAULT_ORGANIZATION` so the
login page wears that organization's branding, which an admin sets under Administration > Branding.

## Connecting a host application

A host app such as `erp_master` signs in its own users through a token exchange:

1. Generate an RSA key pair of at least 2048 bits. The private key stays with the host.
2. Register the public key from the API at `POST /api/v1/auth/trusted-issuers/`, with
   `default_role_code` set to `facilitator` and `syncs_mpp_assignments` set to `true`.
3. The host signs a short-lived assertion, and the app swaps it at `POST /api/v1/auth/exchange/`.

`erp_master` issues assertions at `POST /management/api/auth/member-onboarding/token/` and
reads `MEMBER_ONBOARDING_JWT_PRIVATE_KEY` from its environment.

## Tests

Tests must run as a role that is neither superuser nor BYPASSRLS, otherwise row
level security would not be exercised. The role needs `CREATEDB`.

```
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

After changing the API, regenerate the contract. A test fails if it is stale:

```
uv run python manage.py spectacular --file openapi.yaml --validate
```

## Rules for new code

- **Organization data:** inherit `OrganizationOwnedModel` and add `enable_rls("<table>")` to
  the migration. A test fails if a table is missing it.
- **Background tasks:** wrap organization work in `organization_context(organization_id)`.
  Outside it, those tables return no rows.
- **Runtime role:** the app must connect as `onboarding_app`. `/health/ready/` reports
  `unsafe_role` if the role can bypass row level security.
- **Permissions:** add new ones to `apps/rbac/catalog.py`, guard the API with
  `require_permission("...")`, and run `manage.py sync_system_roles` after deploying.
  Never check a role name in code.
- **Sidebar:** add entries to `apps/rbac/navigation.py`. The menu only hides things, so
  the API must still check its permission.
- **MPP access:** query MPP-owned data through `accessible_mpps()`, so a transfer moves
  access at once. MPP assignment rows are closed, never rewritten.
- **Files:** go through `apps/documents/storage.py`. Files live under `MEDIA_ROOT`, outside
  the code, are encrypted, and are only ever served by the API after a permission check.
  Back up `MEDIA_ROOT` and the encryption keys together: one is useless without the other.
  With more than one server, `MEDIA_ROOT` must be shared storage.
- **Printed forms:** the terms in `apps/applications/templates/applications/pdf/form.html`
  are Kashee's legal text, so another organization needs its own version. The server needs
  Pango for WeasyPrint. The Hindi font ships in the repository.
- **Audit:** call `record_event()` for every state change. Never put secrets or personal
  identifiers in its metadata.
- **Configuration:** only secrets and deployment values go in `.env`. Third-party
  connections belong in `IntegrationConfig`.
- **Encryption keys:** to rotate, put the new key first in `FIELD_ENCRYPTION_KEYS` and keep
  the old one until all its values are re-encrypted. Losing a key loses its data.
