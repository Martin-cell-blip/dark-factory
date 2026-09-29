# Acceptance ledger - Pocketful stage 3 (folder `stage-3/`)

Source: `pocketful/spec/stage-3.md`; stage-1.md and stage-2.md still apply. The shipped checks cover about 9% of this stage; every requirement is graded.

**How items are checked.** Every command runs from the stage-3 folder against a running service started from its Dockerfile (own container name and port). Tests read POCKETFUL_URL, POCKETFUL_URL_B, and for upgrade tests POCKETFUL_STAGE1_URL and POCKETFUL_STAGE2_URL (containers built from the frozen stage-1/ and stage-2/ folders); a test fails, never skips, when a variable it needs is unset. Black-box pytest.

## Decisions recorded by the foreman

- S3-D1. Stage-1 D1-D8 and stage-2 S2-D1-S2-D8 still apply. Stage-3 items live in tests/stage3.
- S3-D2. Correction check order, following the stage-1 order (B1): 401 token -> 400 body -> Idempotency-Key 400/422 -> claimed key (200 replay / 409 reuse) -> field types 400 and rules 422 validation_failed -> 404 unknown payment -> 403 non-sender -> 422 linked_payment_immutable -> 409 stale_revision -> 409 insufficient_funds -> 409 historical_overdraft.
- S3-D3. effective_at equal to now is allowed ("not later than now"); a later one is 422 validation_failed.
- S3-D4. With as_of or known_at, GET /me still returns every money field (balance, total, available, held) for that view plus the echoed as_of / known_at; without them the response is unchanged from stage 2.
- S3-D5. Snapshot tokens and revisions are part of the exported state, so import keeps them valid (stage 4 requires stages 1-3 exports to retain snapshots).
- S3-D6. In a statement entry, payment is the ordinary payment object with amount replaced by the selected amount; every other field is the original.
- S3-D7. Boundary item 23: stage 4 adds POST /payments/{payment_id}/refunds; it must be absent here.

## Items

1. Stages 1 and 2 still hold: the carried tests (tests/acceptance, tests/holdout, tests/stage2, tests/holdout_s2) pass against the stage-3 service, changed only where stage 3 changes a stated behaviour, each change named in the packet  
   check: `python -m pytest tests/acceptance tests/holdout tests/stage2 tests/holdout_s2 -q`
2. Payment timestamps: every endpoint returning a payment includes created_at, an RFC 3339 instant with offset identifying when it moved money; GET /activity keeps ordering by it; seeded payments may supply created_at, and omission uses reset time, before any later API-created payment; a seeded created_at in the future -> 422 validation_failed from POST /_test/reset with no state change; loading seeded payments never changes the seeded balance  
   check: `python -m pytest tests/stage3/test_i02.py -q`
3. GET /me?as_of=<instant>: optional; must be an RFC 3339 instant with an offset, and a naive local time, a bare date or an empty value -> 422 validation_failed; without temporal parameters the response keeps the existing money fields with current corrected values; with as_of, balance is the balance after every payment of the caller with created_at at or before as_of and before every later one (a payment exactly at as_of counts); as_of at or after the latest payment -> current balance; before the earliest -> the opening balance; the response carries as_of back exactly as given  
   check: `python -m pytest tests/stage3/test_i03.py -q`
4. GET /statement?from&to&limit&offset -> {opening_balance, entries: [{payment, delta, balance_after, revision, effective_at, recorded_at}], closing_balance, has_more, snapshot}: from defaults to the opening of the wallet and to to now; only payments the caller sent or received, in the half-open window [from, to), even when other payments are public; oldest first; a sent payment has negative delta and a received one positive; opening_balance is the balance immediately before from and closing_balance immediately before to; opening_balance plus every delta in the full window equals closing_balance; invalid or empty instants -> 422 validation_failed; limit and offset exactly as GET /requests  
   check: `python -m pytest tests/stage3/test_i04.py -q`
5. Statement ordering and pagination: entries ordered by (selected) effective_at ascending, then payment id ascending for ties; pagination never changes an entry's balance_after or the window's opening and closing balances; the final partial page and offsets beyond the end report has_more correctly  
   check: `python -m pytest tests/stage3/test_i05.py -q`
6. Revision history: every payment has revision 1 with the original amount and effective_at = recorded_at = created_at (a seeded payment's supplied created_at, or reset time); opening balances equal seeded ending balances minus the net effect of the original seeded payments and never change through corrections; new accounts open at zero  
   check: `python -m pytest tests/stage3/test_i06.py -q`
7. POST /payments/{payment_id}/corrections (Idempotency-Key required, original sender only): body {expected_revision, amount, effective_at, reason}, all required; expected_revision a positive integer, amount an integer 0..1000000000 (0 reverses the whole payment), reason a string of 1..200 characters, effective_at an RFC 3339 instant not later than now; invalid input -> 422 validation_failed; authenticated non-sender -> 403 forbidden; unknown payment -> 404 not_found; no token -> 401 unauthenticated; returns 201 {payment_id, revision, amount, effective_at, recorded_at, reason}; parties and visibility never change; recorded times for one payment strictly increase  
   check: `python -m pytest tests/stage3/test_i07.py -q`
8. Corrections and idempotency: a stale expected_revision -> 409 stale_revision; a successful replay returns that original revision with 200 even after newer revisions exist; the same key with a different body -> 409 idempotency_key_reuse; the full stage-1 section 7 set applies to this path (missing or empty key 400, key over 255 -> 422, a key that met a 4xx is a first use, keys per user, claimed key resolved before validation)  
   check: `python -m pytest tests/stage3/test_i08.py -q`
9. Correction money movement: the difference from the previous amount moves between the same two wallets in one atomic step (an increase debits the original sender, a decrease debits the original receiver); a currently unaffordable debit (against available) -> 409 insufficient_funds; otherwise, if any user's corrected balance would be negative at any effective-time boundary (including the combined effect of every movement at that instant) -> 409 historical_overdraft; either failure leaves balances, revision history, statements and idempotency state unchanged; the sum of balances equals the seeded total in every historical view  
   check: `python -m pytest tests/stage3/test_i09.py -q`
10. Originals preserved: the original payment and every original idempotent response stay unchanged; GET /activity keeps showing the original payment; corrections are never new feed payments  
   check: `python -m pytest tests/stage3/test_i10.py -q`
11. GET /payments/{payment_id}/revisions -> {"revisions": [...]} in revision order including revision 1 with reason ""; only the two parties may read it; a third party gets 404 not_found even for a public payment; no token -> 401 unauthenticated  
   check: `python -m pytest tests/stage3/test_i11.py -q`
12. known_at on GET /me and GET /statement: an RFC 3339 instant with offset; for each payment the latest revision recorded at or before known_at is selected, and a payment with none recorded yet contributes nothing; omission means everything known when the read begins; selected revisions apply by their effective times; as_of stays inclusive and the statement window half-open; both instants may be in the future; invalid or empty -> 422 validation_failed; a supplied known_at is echoed exactly  
   check: `python -m pytest tests/stage3/test_i12.py -q`
13. Statements with corrections: entries carry the selected revision, effective_at and recorded_at; payment.amount is the selected amount for this statement; zero-amount revisions still appear as entries with zero delta; no correction is counted beside the revision it replaces; a correction may move a payment into or out of a window; with no corrections and no known_at the statement equals the uncorrected one  
   check: `python -m pytest tests/stage3/test_i13.py -q`
14. Stable statement pagination: every first GET /statement returns an opaque snapshot token that freezes the caller's selected revisions, window, balances, entries and default to at that read; GET /statement?snapshot=<token>&limit&offset pages exactly that result even after later payments or corrections; from, to or known_at supplied with snapshot -> 422 validation_failed; an unknown token, another user's token or a token from before a reset -> 404 not_found; tokens last until reset; other unrecognised query parameters stay ignored  
   check: `python -m pytest tests/stage3/test_i14.py -q`
15. Concurrency: concurrent corrections using the same expected revision never both succeed (exactly one 201, the others 409 stale_revision); concurrent identical corrections with one unused key -> one 201 and the rest 200 replays; existing snapshots stay unchanged under concurrent payments or corrections; balances conserved and never negative  
   check: `python -m pytest tests/stage3/test_i15.py -q`
16. Settlement history: stage-1 settlements keep their original receipts and privacy rules; each member's revision 1 uses the shared committed_at as effective_at and recorded_at; a single-payment correction of a settlement member -> 422 linked_payment_immutable  
   check: `python -m pytest tests/stage3/test_i16.py -q`
17. Exports: a stage-3 service accepts, unchanged, exports produced by this team's stage-1 and stage-2 services, and accounts for authorizations and captures; captures are immutable linked payments, so correcting a capture -> 422 linked_payment_immutable; a stage-3 export/import round-trips revisions, snapshot tokens and correction replays  
   check: `python -m pytest tests/stage3/test_i17.py -q`
18. Historical holds: GET /me?as_of=T&known_at=K reports balance = total, held and available = total - held for that same view; a hold starts at authorization creation, a nonfinal capture reduces it at capture time, and a final capture, void or expiry releases the remainder at that event's time (expiry at expires_at); events other than clock expiry are known at their server-assigned event time, and once creation is known the expiry deadline is known too; for instants beyond now an open hold expires at its deadline; without as_of use the instant the request began; authorizations expose closed_at (null while open, the event time once closed); seeded open holds count as created at reset unless created_at is supplied  
   check: `python -m pytest tests/stage3/test_i18.py -q`
19. Corrections against holds: a correction is rejected with 409 historical_overdraft if it makes either total or available negative at any past effective or event boundary under the latest known revisions; a current unaffordable debit still takes precedence as 409 insufficient_funds; GET /statement contains money movements only (authorisation, release and expiry are not entries); captures appear exactly once with their links; old snapshots stay unchanged after any lifecycle action or correction  
   check: `python -m pytest tests/stage3/test_i19.py -q`
20. The image builds and runs on its own with -e PORT and a port mapping, no outbound network at run time; RUN.md gives one command a stranger can follow; no nested .git  
   check: `docker build -t pocketful-stage-3-ledger .`
21. The event harness claims stage 3: the --stage 3 run reports 'claimed stage: 3' (stage 4 suite fails)  
   check: judged by the auditor (no command)
22. The folder's whole test suite passes  
   check: `python -m pytest tests -q`
23. Boundary: stage 4's refund capability is absent: the receiver's POST /payments/{payment_id}/refunds with a valid body and Idempotency-Key does not return 201 (expected 404 not_found)  
   check: `python -m pytest tests/stage3/test_i23.py -q`
24. Every fixed name (route, field, code, query parameter) appears verbatim; code another developer can maintain; the stage-2 screens keep working  
   check: judged by the auditor (no command)
25. Memory headroom: peak container memory stays below 1.5 GiB through the whole suite under --memory 2g, with no OOM kill  
   check: judged by the auditor (no command)
