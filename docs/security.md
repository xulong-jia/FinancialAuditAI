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

## Data Boundary

Use only synthetic, simulated, desensitized, or public data. The repository must not contain real contracts, confirmations, interview notes, audit workpapers, bank data, invoices, customer data, or screenshots containing such data.

## Not Implemented

- Enterprise SSO
- Third-party OAuth
- Multi-tenant billing
- Production KMS
- Complex organization hierarchy
- Production monitoring or incident response
