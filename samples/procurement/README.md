# Procurement MVP Demo Samples

This folder contains hand-written mock procurement walkthrough data for MVP demos.

- The data is synthetic.
- It does not contain real customer, supplier, invoice, bank, tax, or payment information.
- It is intended only for local demo seeding and tests.
- Generated upload files and xlsx reports must stay under `local_storage/` and must not be committed.

Use:

```bash
cd backend
source .venv/bin/activate
python ../scripts/seed_demo_data.py
```

The script creates a procurement task, mock document records, page text, extracted fields, document relations, audit results, and an xlsx report record in the configured local database. Generated report files are written under ignored `local_storage/reports`.
