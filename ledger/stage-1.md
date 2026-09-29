# Acceptance ledger — Pocketful stage 1 (folder `stage-1/`)

Source: `pocketful/spec/stage-1.md` (kickoff package). Every item is graded; the shipped checks cover only part of it.

**How items are checked.** Every command runs from the stage-1 folder against a running service. Start it first: docker build -t pocketful-stage-1 . && docker run -d --rm --name pocketful-stage-1 -p 8080:8080 -e PORT=8080 pocketful-stage-1. Tests read the base URL from the environment variable POCKETFUL_URL (default http://localhost:8080), reset their own fixture through POST /_test/reset, and are black-box HTTP tests written with pytest.

## Decisions recorded by the foreman

- D1. Every payment object, on every endpoint, carries `settlement_id` (null unless it is a settlement member), per §11 "nonmembers expose null for that field". The §8 payment example omits it; §11 is the later, specific rule.
- D2. A body that parses as JSON but is not an object (array, string, number) is 400 `malformed_request` (§5: a body of the wrong type; §7 speaks of 'the body has parsed as a JSON object').
- D3. `note: null` is 422 `validation_failed` (stated in §5). A missing required field is 422 `validation_failed`; a wrong-typed field other than amount/note/visibility is 400 `malformed_request`.
- D4. The event harness run (item 37) carries no command in the committed ledger, to keep machine paths out of the repository; the auditor and gatekeeper run it from the kickoff package.
- D5. Boundary item 39: stage 2 adds authorizations (`POST /authorizations`), which must be absent here. Stage 2's browser screens are the other new capability; the authorizations check is the one additive, request-observable behaviour chosen.
- D6. `note` length is counted in Unicode code points (auditor gap G7).
- Amendment 1 (auditor coverage check): items 2, 13, 19, 24, 27, 29, 34 extended; items 41-43 added.
- D7. The spec does not bound fixture size; item 34 is held to a 1000-user reset within 5 s (half the 10 s limit, as margin for judge hardware). Seeded passwords must still be stored with a password-hashing function.
- D8 (amended in amendment 4). API routes cap bodies at 1 MiB; /_test/reset and /_test/import, which are not concurrent and may carry large exports, cap at 64 MiB. Larger bodies may be refused with 413 and the error envelope. Reason: an 8 MiB ignored array costs ~10x in memory, and 50 of them cannot meet 5 s within 2 vCPU/2 GiB.
- Amendment 4: item 34 restated with D8 amended (auditor R4b on bf911c3).
- Amendment 3: items 5 and 34 extended (auditor verdict on 704e4d9, R2 and R3).
- Amendment 2: item 41 reads its second instance from POCKETFUL_URL_B.

## Items

1. Listens on 0.0.0.0 using PORT (default 8080); GET /health -> 200 {"status": "ok"} within 60 s of container start  
   check: `python -m pytest tests/acceptance/test_i01.py -q`
2. POST /_test/reset (no auth) replaces all state with the fixture and returns 204; later requests see only that fixture; repeated resets work; seeded users log in with their password immediately; seeded balance is the post-payment balance (seeded payments are not replayed); seeded payments and requests are readable; settlement_operator_ids defaults to []; seeded user, payment and request ids come back verbatim (GET /me user_id, activity payment_id, GET /requests request_id) and seeded non-pending request statuses are honoured  
   check: `python -m pytest tests/acceptance/test_i02.py -q`
3. Reset fixture with a balance below zero -> 422 validation_failed and state unchanged; minor_units 0, 2 and 3 (JPY, EUR, BHD) accepted and reported by GET /me  
   check: `python -m pytest tests/acceptance/test_i03.py -q`
4. Conventions: responses are application/json; charset=utf-8; timestamps are RFC 3339 with an explicit offset; unknown request-body fields ignored; unknown query parameters ignored; every id is a string of at most 64 characters  
   check: `python -m pytest tests/acceptance/test_i04.py -q`
5. Amounts: JSON 1000, 1000.0 and 1e3 are the same valid amount; booleans, strings, null, non-integral numbers, values below 1 and above 1000000000 are 422 validation_failed on every endpoint that takes amount; a valid JSON integer of any length (e.g. 1 followed by 5000 zeros) is 422 validation_failed, never 400  
   check: `python -m pytest tests/acceptance/test_i05.py -q`
6. Error envelope {"error": {"code": ..., "message": ...}} on every 4xx and 5xx; unparseable body or a non-object body -> 400 malformed_request; a field of the wrong JSON type (other than amount, note, visibility, which are 422) -> 400 malformed_request; a missing required field -> 422 validation_failed  
   check: `python -m pytest tests/acceptance/test_i06.py -q`
7. POST /auth/signup -> 201 {user_id, display_name, token}; handle derived from the email local part (lowercase, every char outside [a-z0-9_] -> _, truncate to 20); 409 email_taken; password shorter than 8 -> 422 validation_failed; email not local@domain -> 422 validation_failed; derived handle taken -> 409 handle_taken and no account created; new users have balance 0 and can receive money and be asked for money immediately  
   check: `python -m pytest tests/acceptance/test_i07.py -q`
8. POST /auth/login -> 200 {user_id, display_name, token}; wrong password or unknown email -> 401 unauthenticated; tokens do not expire; several tokens for one account are valid concurrently  
   check: `python -m pytest tests/acceptance/test_i08.py -q`
9. Every endpoint except /health, /_test/reset, /_test/export, /_test/import, /auth/signup and /auth/login requires Authorization: Bearer <token>; missing, malformed or unknown token -> 401 unauthenticated  
   check: `python -m pytest tests/acceptance/test_i09.py -q`
10. Passwords stored with bcrypt, scrypt, Argon2 or equivalent, never plaintext: the exported state never contains a password in clear  
   check: `python -m pytest tests/acceptance/test_i10.py -q`
11. GET /me -> {user_id, display_name, handle, balance, currency, minor_units}  
   check: `python -m pytest tests/acceptance/test_i11.py -q`
12. POST /payments -> 201 {payment_id, from_user_id, from_handle, to_user_id, to_handle, amount, currency, note, visibility, request_id: null, settlement_id: null, created_at}; note defaults to "", visibility defaults to "public"; debit and credit are one atomic step  
   check: `python -m pytest tests/acceptance/test_i12.py -q`
13. POST /payments errors: balance below amount -> 409 insufficient_funds; to_handle is own handle -> 422 self_payment; note over 200 chars or non-string (including null) -> 422 validation_failed; visibility neither public nor private -> 422 validation_failed; unknown handle -> 404 not_found; a failed payment leaves no trace in either wallet or any feed; note length is counted in Unicode code points (200 emoji valid, 201 code points -> 422)  
   check: `python -m pytest tests/acceptance/test_i13.py -q`
14. note is stored and returned verbatim (no trim, escape or normalisation); Unicode and emoji round-trip byte for byte on payments, requests and splits  
   check: `python -m pytest tests/acceptance/test_i14.py -q`
15. Idempotency (section 7) on each of POST /payments, POST /requests, POST /requests/{id}/pay, POST /splits, POST /settlements: header absent or empty -> 400 missing_idempotency_key; longer than 255 chars -> 422 validation_failed; first use 201; same user+method+path+body -> 200 with an identical JSON body; same key, different body -> 409 idempotency_key_reuse; key reused after a 4xx is a first use; keys scoped per user; same key+body on a different path is a new request; body compared as parsed JSON (key order, whitespace ignored); a claimed key is resolved before field validation and resource checks; a replay returns the original even after the resource changed and changes nothing  
   check: `python -m pytest tests/acceptance/test_i15.py -q`
16. Concurrent identical requests with an unused key on each idempotent path: exactly one 201, the rest 200 with the same body, effect applied once  
   check: `python -m pytest tests/acceptance/test_i16.py -q`
17. Invariants under concurrent load (50 in flight): wallet balances always sum to the seeded total; no balance is ever negative; concurrent spends of one wallet never overdraw; a request moves money at most once (concurrent pays with different keys -> one 201, the rest 409 request_not_pending); no 5xx  
   check: `python -m pytest tests/acceptance/test_i17.py -q`
18. POST /requests -> 201 {request_id, requester_id, requester_handle, payer_id, payer_handle, amount, currency, note, status: "pending", payment_id: null, created_at}; payer balance not checked; payer_handle own handle -> 422 self_request; note over 200 -> 422 validation_failed; unknown handle -> 404 not_found  
   check: `python -m pytest tests/acceptance/test_i18.py -q`
19. POST /requests/{id}/pay: body {visibility} optional default public, chosen by the payer; 201 with a payment shaped exactly as POST /payments with request_id set; request becomes paid with payment_id; not pending -> 409 request_not_pending; short -> 409 insufficient_funds changing nothing and later payable when funds arrive; not the payer -> 403 forbidden; unknown -> 404 not_found; replay -> 200 original payment even though paid, never 409 request_not_pending; {} vs {"visibility": "public"} under one key -> 409 idempotency_key_reuse; the payment carries settlement_id: null  
   check: `python -m pytest tests/acceptance/test_i19.py -q`
20. POST /requests/{id}/decline (no idempotency key, payer only) -> 200 request with status declined; declining again -> 200 current state; paid or cancelled -> 409 request_not_pending; not the payer -> 403 forbidden; unknown -> 404 not_found  
   check: `python -m pytest tests/acceptance/test_i20.py -q`
21. POST /requests/{id}/cancel (no idempotency key, requester only) -> 200 request with status cancelled; cancelling again -> 200; paid or declined -> 409 request_not_pending; not the requester -> 403 forbidden; unknown -> 404 not_found  
   check: `python -m pytest tests/acceptance/test_i21.py -q`
22. GET /requests -> {requests, has_more}: only requests where the caller is requester or payer, newest first by created_at; direction incoming|outgoing|absent; status pending|paid|declined|cancelled|absent; unknown direction or status -> 422 validation_failed; limit default 50 range 1..200, offset default 0 and >= 0; has_more true exactly when items exist beyond the last returned  
   check: `python -m pytest tests/acceptance/test_i22.py -q`
23. Integer query parameters (limit, offset on /requests and /activity) are plain decimal digits: 1e9, 4.0, +4, -1, 0 (limit), 201 (limit) and non-numeric -> 422 validation_failed  
   check: `python -m pytest tests/acceptance/test_i23.py -q`
24. POST /splits -> 201 {split_id, amount, currency, note, shares:[{handle, amount}], requests:[...], created_at}; shares cover every participant including the caller in the given order and sum to amount; requests are pending, one per participant except the caller, same order, caller as requester; a share of 0 still gets a request; caller-only split is valid with requests []; no balance is checked; a split is not a feed item; each request a split creates appears in GET /requests for its requester and its payer, is payable by that payer through /requests/{id}/pay, and is not visible to a third party  
   check: `python -m pytest tests/acceptance/test_i24.py -q`
25. POST /splits errors: amount invalid -> 422 validation_failed; participant_handles empty or with a duplicate -> 422 validation_failed; note over 200 -> 422 validation_failed; any unknown handle -> 404 not_found  
   check: `python -m pytest tests/acceptance/test_i25.py -q`
26. Section 9 equal split: whole minor units, sum exact, differ by at most 1, larger shares to the first participants in order: 1000/3 -> 334,333,333; 1/3 -> 1,0,0; 10/3 -> 4,3,3; 999/3 -> 333,333,333; 5/5 -> 1,1,1,1,1; reordering handles moves the extra unit; splits independent; balances still sum to seeded total after paying splits in full  
   check: `python -m pytest tests/acceptance/test_i26.py -q`
27. GET /activity -> {payments, has_more}: payments only; a payment appears iff visibility is public or the caller is sender or receiver; private visible to both parties, hidden from third parties; requests and splits never appear; newest first by created_at; limit, offset, has_more as on GET /requests; every activity item, seeded payments included, carries settlement_id (null for nonmembers)  
   check: `python -m pytest tests/acceptance/test_i27.py -q`
28. GET /_test/export (no auth) -> 200 {track: "pocketful", format_version: 1, state: {...}}; an atomic read-only snapshot unchanged by later writes  
   check: `python -m pytest tests/acceptance/test_i28.py -q`
29. POST /_test/import (no auth) -> 204, atomic replacement not merge, repeatable without duplicates; preserves accounts and hashed-password login, existing bearer tokens, currency, balances, payments, requests, operator permissions, settlement membership, ids, timestamps, completed idempotent bodies and original responses (replay -> 200 original); failed keys stay reusable; removes all previous destination data and credentials; invalid JSON -> 400 malformed_request; missing fields, wrong track or format_version, invalid state -> 422 validation_failed with state unchanged; reset clears imported state; payments after import still carry settlement_id (null for nonmembers)  
   check: `python -m pytest tests/acceptance/test_i29.py -q`
30. POST /settlements: no token -> 401 unauthenticated; authenticated non-operator -> 403 forbidden; Idempotency-Key required; operators come from fixture settlement_operator_ids (default []); operator status grants no access to other users' requests or private activity  
   check: `python -m pytest tests/acceptance/test_i30.py -q`
31. POST /settlements validation: transfers must hold 1..32 objects and a malformed batch shape -> 422 validation_failed; each entry follows payment rules for amount, note, visibility (defaults empty note, public); unknown handle -> 404 not_found; self-transfer -> 422 self_payment; entry errors take precedence in input order and before insufficient_funds; unknown fields ignored; failed validation claims no idempotency key and creates no payment  
   check: `python -m pytest tests/acceptance/test_i31.py -q`
32. POST /settlements netting: affordable iff every wallet's balance after all incoming and outgoing transfers is nonnegative (a chain funded by an incoming transfer in the same batch succeeds); otherwise 409 insufficient_funds; all movements commit together or none do  
   check: `python -m pytest tests/acceptance/test_i32.py -q`
33. POST /settlements -> 201 {settlement_id, committed_at, payments} with payments in input order; each member is an ordinary payment with settlement_id set, request_id null and created_at equal to committed_at; members follow ordinary feed visibility; replay -> 200 original complete response  
   check: `python -m pytest tests/acceptance/test_i33.py -q`
34. Within caps (2 vCPU, 2 GiB, no outbound network): 50 concurrent requests all answered within 5 s with no 5xx; reset, export and import each answer within 10 s; reset of a 1000-user fixture answers within 5 s under the caps (decision D7); request bodies are bounded so that 50 in-flight maximal bodies stay well within 2 GiB (decision D8, amended: a body above 1 MiB on an API route, or above 64 MiB on /_test/reset and /_test/import, may be refused with 413 and the error envelope); 50 concurrent maximal API bodies (1 MiB, ignored array field) are all answered within 5 s with no 5xx  
   check: `python -m pytest tests/acceptance/test_i34.py -q`
35. The image builds, and runs on its own with -e PORT=<port> and a port mapping, with no outbound network at run time  
   check: `docker build -t pocketful-stage-1-ledger .`
36. RUN.md gives a stranger one command that builds and starts the service without manual setup; the folder holds source, tests, Dockerfile and RUN.md and no nested .git  
   check: judged by the auditor (no command)
37. The event harness claims stage 1: last line of the harness run for --stage 1 reads 'claimed stage: 1' (run from the kickoff package; strict --mode isolated at release)  
   check: judged by the auditor (no command)
38. The folder's whole test suite passes  
   check: `python -m pytest tests -q`
39. Boundary: stage 2's authorizations capability is absent: an authenticated POST /authorizations with a valid body and Idempotency-Key does not return 201 (expected 404 not_found)  
   check: `python -m pytest tests/acceptance/test_i39.py -q`
40. Every fixed name (route, field, error code, status, fixture key) appears verbatim; nothing from existing products' source, API docs or schemas is used  
   check: judged by the auditor (no command)
41. Export from one container imported into a fresh container on a different port restores logins, bearer tokens, balances, payments, requests and idempotent replays: no dependency on the source process, files, volume, port or network address; the second instance is read from env POCKETFUL_URL_B (a second container started on a different port, documented in RUN.md); the test fails, never skips, when POCKETFUL_URL_B is unset  
   check: `python -m pytest tests/acceptance/test_i41.py -q`
42. Exact arithmetic up to 2^53: a seeded balance of 9007199254740991 reads back exactly on GET /me and through export/import; a payment of 1000000000 from a balance near 2^53 leaves exact balances and the seeded total conserved  
   check: `python -m pytest tests/acceptance/test_i42.py -q`
43. An operator may execute a settlement across any wallets: an operator who is party to none of the transfers (ada->bob, bob->cy) settles successfully  
   check: `python -m pytest tests/acceptance/test_i43.py -q`
