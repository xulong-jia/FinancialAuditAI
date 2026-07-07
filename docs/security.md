# Security

This project is a local demonstration and portfolio system. It includes practical safety controls, but it is not a production security program.

## RBAC

Default roles:

- `viewer`: read-only access.
- `analyst`: create/update tasks, upload documents, run processing, run rule audit, run Agent workflows.
- `reviewer`: field correction, exception confirm/dismiss, rule rerun.
- `manager`: report generation, evaluation result viewing, audit-log viewing.
- `admin`: all permissions, including Rule Center, RAG management, user/role management.

Protected APIs require `Authorization: Bearer <token>`.

## Upload Security

Uploads are checked for:

- allowed extension
- basic content type
- size limit
- file hash
- basic magic header/signature match

Files are saved under ignored `local_storage/uploads`.

## Logging And Audit

- `audit_logs` record important review, rule, user, and role changes.
- Sensitive keys such as password, token, secret, API key, and authorization are redacted.
- Large raw text fields such as OCR/source/chunk text are redacted in audit logs.

## Repository Safety

Do not commit:

- `.env` or `.env.*`
- `local_storage/`
- uploads
- generated reports
- vector index files
- API keys
- tokens
- cleartext passwords
- real customer documents

Run before commit:

```bash
python3 scripts/danger_check.py
```

`danger_check.py` scans tracked files, staged diff additions, common secret patterns, accidental `.env` files, runtime artifact paths such as `local_storage`, `uploads`, `reports`, `vector_index`, and provider readiness artifacts. It is a repository safety check, not enterprise DLP, managed secret scanning, KMS, or incident response.

## Production Configuration Safety

Before any production deployment review, run:

```bash
python3 scripts/production_safety_check.py
```

The script does not read `.env` files. It checks current environment variables plus tracked and staged Git paths. When `ENVIRONMENT=production`, it blocks:

- default or missing `AUTH_SECRET_KEY`
- empty or default database passwords in `DATABASE_URL`
- wildcard or localhost `CORS_ORIGINS`
- tracked or staged `.env` files
- tracked or staged `local_storage`, upload, report, or vector-index artifacts

Session/token production boundary:

- Bearer tokens are signed with `AUTH_SECRET_KEY`.
- `ACCESS_TOKEN_MINUTES` is configurable.
- Production deployments must set secrets through deployment secret storage, not committed files.
- Enterprise SSO, KMS-backed secret rotation, centralized monitoring, and incident response remain production hardening outside this local portfolio repository.

## Data Boundary

Use only synthetic, simulated, desensitized, or public data. The repository must not contain real contracts, confirmations, interview notes, audit workpapers, bank data, invoices, customer data, or screenshots containing such data.

## Not Implemented

- Enterprise SSO
- Third-party OAuth
- Multi-tenant billing
- Production KMS
- Complex organization hierarchy
- Production monitoring or incident response
