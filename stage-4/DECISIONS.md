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

## Stage 2

Foreman decisions S2-D1 to S2-D6 are built as stated. The builder's own choices:

- **B14. Holds.** `held` is kept per user as the sum of the remaining amounts of that user's
  open authorisations (`pocketful/holds.py`). Every money path goes through one guard in
  `State.commit_payments`: after the batch, each wallet's total must still cover what it
  holds. A capture passes the hold it gives up in the same step, so it may spend exactly
  the money reserved for it.
- **B15. Expiry.** Every operation first expires, by the UTC wall clock, each open
  authorisation whose `expires_at` is at or before now (a deadline heap, so no request is
  needed at the deadline). An authorisation expired this way remembers it
  (`clock_expired_authorization_ids` in the export): capturing it is 409
  `authorization_expired`. One seeded as `expired`, or captured or voided, is 409
  `authorization_not_open` (S2-D3). Void of any expired one is `authorization_not_open`.
- **B16. Capture checks, in order.** `final` of the wrong type 400; `amount` not an integer
  of at least 1 is 422 `validation_failed`; unknown 404; not the receiver 403; not open 409;
  `amount` above the remainder 422 `capture_exceeds_authorization` (including amounts above
  1000000000, since the remainder is the stated limit). `final` defaults to true.
- **B17. Seeded authorisations.** `note`, `visibility` and `created_at` are optional as for
  seeded payments. `captured_amount` defaults to the amount for `captured` and 0 otherwise;
  `remaining_amount` and `payment_ids` may be given (an export always gives them). The
  per-user sum of unexpired open holds is checked against the balance after loading.
- **B18. Replay fingerprints.** A stored idempotent request keeps a SHA-256 digest of its
  canonical body, not the body. A stage-1 export stores canonical bodies; import digests them,
  so its replays still match.
- **B19. Content negotiation.** `GET /requests` and `GET /authorizations` serve the app when
  the `Accept` header contains `text/html`, JSON otherwise. `/`, `/split`, `/signup` and
  `/login` always serve the app; static files live under `/assets/`.
- **B20. The browser app.** One HTML shell for every screen; ES modules render the screen
  named by the path (no build step, no third-party code). The session token lives in
  `localStorage`, so a browser stays signed in across an export/import that keeps tokens.
  Signed-out visits to `/`, `/requests`, `/split` and `/authorizations` go to `/login`.
- **B21. Where the forms live.** Pay, request and the authorise ("Hold for someone") form
  are on `/`; the authorise form is also on `/authorizations` beside the list. The wallet
  card (with `wallet-refresh`) is on `/`, `/requests` and `/authorizations`.
- **B22. Retries from forms.** A form keeps one Idempotency-Key until any field changes;
  resubmitting unchanged (after success, refusal or an uncertain outcome) resends the same
  key and body. Paying a request uses one key per request; a capture one key per
  authorisation and amount. A 4xx is a refusal; no answer, a 5xx or an unreadable body is
  uncertain, never shown as a refusal.
- **B23. Latest refresh wins.** Each screen's reads (`/me` with its list) are one refresh;
  a refresh applies only if no later one has been started since, whatever order the
  responses arrive in. A failed refresh keeps the last data and marks it not up to date.
- **B24. Amount input.** Digits with an optional point and up to `minor_units` decimals
  (`15`, `15.5`, `15.00`); anything else (`15.005`, `1e3`, `-5`, `15.`, `.5`, `1,5`, `0`)
  is refused in the form without sending. The capture amount is pre-filled with the
  remaining amount in the same decimal form.
- **B25. Dates** are shown in English (`en-GB`) whatever the browser locale;
  `authorization-expires-{id}` shows the exact RFC 3339 `expires_at` beside a
  human "Expires in …" label.

## Stage 3

Foreman decisions S3-D1 to S3-D7 are built as stated. The builder's own choices:

- **B26. Revisions and views.** Every payment keeps its revisions (`pocketful/history.py`);
  revision 1 is the payment as made. A view at (as_of T, known_at K) selects, per payment,
  the latest revision recorded at or before K and counts it if its effective_at is at or
  before T (a statement window counts effective_at in [from, to)). Omitted K means every
  revision; omitted T means the instant the read begins (never before the last recorded
  event).
- **B27. Opening balances** are derived, not stored: current balance minus the net of every
  payment's latest revision. A correction moves both by the same amount, so opening balances
  never change, and exports from stages 1 and 2 need nothing extra.
- **B28. Historical overdraft.** A correction is checked for both parties over every
  effective and hold-event boundary under the latest revisions with the correction applied,
  summing everything at one instant before checking total >= 0 and total - held >= 0.
- **B29. Holds in history.** A hold counts from created_at; captures reduce it at their
  payment's created_at; a void, final capture or clock expiry releases the rest at closed_at
  (clock expiry at expires_at, known once creation is known; the others known at closed_at).
  In a view that does not yet know a close, an open hold expires at its deadline. A closed
  authorisation that arrives by seed or import gets closed_at per S3-D8 (latest capture
  payment, expires_at, or the recorded void time, else the reset or import time). Seeded
  closed ones, and imported ones whose close time the export did not keep (stage-2 voids),
  hold nothing in any historical view; the set is exported as
  `authorizations_without_history`.
- **B30. Statements.** `from` later than `to` is 422 `validation_failed` (the window
  arithmetic would not close). Ties on effective_at are ordered by payment id as a string.
  A first read stores its whole result under a random snapshot token; the token is exported
  with the state (S3-D5) and cleared by reset.
- **B31. Instants in queries** must be RFC 3339 with seconds and Z or a numeric offset. A '+'
  that arrives unencoded in a query string (and so decodes as a space) is read as '+'.
- **B32. Correction fields.** `expected_revision` must be a JSON number (other types 400);
  `amount` follows the stage-1 amount rule but allows 0; effective_at must not be later than
  the wall-clock now at validation; `reason` counts code points.

## Stage 4

Foreman decisions S4-D1 to S4-D6 are built as stated. The builder's own choices:

- **B33. One correction engine** (`pocketful/corrections.py`) serves single corrections and
  batches: field rules, which payments may be corrected, the expected revision, refunded
  amounts, then one combined check of current available funds and history, and all new
  revisions recorded at one instant.
- **B34. Correction check order** extends S3-D2: ... 422 linked_payment_immutable (captures,
  refunds; settlement members outside a batch) -> 409 stale_revision -> 422
  refund_exceeds_payment (below what was refunded) -> 409 insufficient_funds -> 409
  historical_overdraft. In a batch each item runs these per-item checks in input order, then
  settlement completeness (incomplete_settlement), then one effective instant per settlement
  (validation_failed), then the combined funds checks.
- **B35. Batch shape.** `corrections` must be an array of 1 to 32 objects, each with a
  string `payment_id`, all distinct; anything else is 422 `validation_failed`. Item fields
  follow the single-correction rules (wrong JSON types 400, rules 422).
- **B36. Refunds** are ordinary payments with `refund_of` set, recorded through the same
  guard as every payment (the receiver's available funds). `refund_of` is null on every
  other payment, including payments imported from earlier stages' exports; stored
  responses from before the upgrade replay as stored.
