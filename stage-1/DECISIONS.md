# Decisions where the requirements leave room

Foreman decisions D1–D5 from the ledger are built as stated. The builder's own choices:

- **B1. Check order.** Token (401) → body parses as a JSON object (400) → operator (403,
  settlements only) → `Idempotency-Key` present (400) and at most 255 characters (422) →
  claimed key resolved (200 replay / 409 reuse) → field types (400) and rules (422) →
  resources (404, then 403, then 409 status) → funds (409).
- **B2. Idempotency scope.** A key is stored per (user, method, path, key) with the
  canonical body. Numbers compare by value (`1000`, `1000.0`, `1e3` are one value);
  `true` and `1` differ. Only 2xx outcomes are stored, so a key that met a 4xx stays free.
- **B3. Pay body.** An empty body on `POST /requests/{id}/pay` counts as `{}`. Decline and
  cancel take no body; a non-empty body that does not parse is still 400.
- **B4. Settlement entries.** A missing or non-string `from_handle`/`to_handle`, or an
  entry that is not an object, is batch shape: 422 `validation_failed`. Within one entry
  the order is shape → amount → note → visibility → unknown handle (404) → self (422).
- **B5. Emails.** `local@domain` means one `@`, non-empty parts, no whitespace. Emails are
  compared case-insensitively for `email_taken` and login.
- **B6. Handles in bodies.** A string that names no user, including one outside
  `^[a-z0-9_]{1,20}$`, is 404 `not_found`.
- **B7. Fixture records.** Seeded payments and requests may carry `created_at`; when
  absent, the reset time is used. Seeded `note` defaults to `""`, `visibility` to
  `public`, request `status` to `pending`. Any invalid fixture is 422 and changes nothing.
- **B8. Timestamps.** UTC with microseconds and `+00:00`, strictly increasing, so creation
  order and `created_at` order agree. Settlement members share `committed_at`.
- **B9. Unknown routes** are 404 `not_found`; a known path with another method is 405
  `method_not_allowed`.
- **B10. Zero shares.** A split request for 0 can be paid and produces a 0-amount payment.
- **B11. Oversized integers.** A JSON integer longer than 4000 digits still parses; no
  field rule accepts it as a number (so an amount is 422, not 400) and replays compare its
  digits.
- **B12. Password cost and reset size.** scrypt with N=2^12, r=8, p=1 and a random salt for
  every user, seeded users included (foreman F1). A reset hashes the seeded passwords in
  parallel; a 1000-user fixture resets in about 3 s within the 2 vCPU cap (audit R3;
  foreman D7 sets 5 s). Hashes imported with other scrypt parameters still verify, since
  the parameters are stored in the hash.
- **B13. Body size (foreman D8, amended).** API routes cap bodies at 1 MiB; `/_test/reset`
  and `/_test/import` at 64 MiB. A larger body gets 413 `payload_too_large` in the error
  envelope; bodies up to 64 MiB are drained first so the client reads it. Ordinary bodies
  parse and fingerprint at C speed (the slow paths for 4000+-digit integers and `\u`
  surrogate escapes run only when the raw bytes contain them), and the fingerprint is
  taken outside the lock: 50 concurrent 1 MiB bodies answer in about 2 s, peak about
  250 MiB, under 2 vCPU / 2 GiB.
