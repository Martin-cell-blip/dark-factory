# Acceptance ledger - Pocketful stage 4 (folder `stage-4/`)

Source: `pocketful/spec/stage-4.md`; stages 1-3 still apply. The shipped checks cover about 16% of this stage; every requirement is graded.

**How items are checked.** Every command runs from the stage-4 folder against a running service started from its Dockerfile (own container name and port). Tests read POCKETFUL_URL, POCKETFUL_URL_B, and for upgrade tests POCKETFUL_STAGE1_URL, POCKETFUL_STAGE2_URL and POCKETFUL_STAGE3_URL (containers built from the frozen stage-1/, stage-2/ and stage-3/ folders); a test fails, never skips, when a variable it needs is unset. Black-box pytest. Compare server timestamps only with server timestamps, or with at least a second of margin.

## Decisions recorded by the foreman

- S4-D1. All earlier decisions (D1-D8, S2-D1-S2-D8, S3-D1-S3-D8) still apply. Stage-4 items live in tests/stage4.
- S4-D2. A refund is a new ordinary payment: settlement_id null, created_at the refund time, revision 1 like any payment; it is never a settlement member even when its target is one.
- S4-D3. Refund check order, following B1 and S3-D2: 401 -> 400 body -> Idempotency-Key -> claimed key (200 replay / 409 reuse) -> amount 422 validation_failed -> 404 unknown payment -> 403 not the original receiver -> 422 invalid_refund_target -> 422 refund_exceeds_payment -> 409 insufficient_funds.
- S4-D4. "Current corrected amount" is the amount of the latest revision (as known now); refund_exceeds_payment compares cumulative refunds including this one against it.
- S4-D5. Every revision object gains correction_batch_id (null unless created by a batch). Responses stored before the upgrade replay exactly as stored (S2-D8).
- S4-D6. Stage 4 is the last stage, so the ledger carries no boundary item.

## Items

1. Stages 1-3 still hold: the carried tests (tests/acceptance, tests/holdout, tests/stage2, tests/holdout_s2, tests/stage3, tests/holdout_s3) pass against the stage-4 service, changed only where stage 4 changes a stated behaviour, each change named in the packet; retired: tests/stage3/test_i23.py and the holdout_s3 test that asserts refunds are absent; whole-shape assertions gain refund_of on payments and correction_batch_id on revisions  
   check: `python -m pytest tests/acceptance tests/holdout tests/stage2 tests/holdout_s2 tests/stage3 tests/holdout_s3 -q`
2. POST /payments/{payment_id}/refunds with body {"amount": 200} (Idempotency-Key required) -> 201 with a new payment in the opposite direction: from the original receiver to the original sender, refund_of naming the target, request_id: null, authorization_id: null, the original note and visibility; a replay returns 200 with the original body; every other payment carries refund_of: null; the full stage-1 section 7 set applies  
   check: `python -m pytest tests/stage4/test_i02.py -q`
3. Refund rules: only the original receiver may refund, else 403 forbidden; unknown payment -> 404 not_found; the target may be a direct payment, a request payment, a capture or a settlement member, never a refund (-> 422 invalid_refund_target); invalid amount -> 422 validation_failed; cumulative refunds above the payment's current corrected amount -> 422 refund_exceeds_payment; the receiver's available below amount -> 409 insufficient_funds; all atomic  
   check: `python -m pytest tests/stage4/test_i03.py -q`
4. Refund effects: money moves from the receiver's available funds to the sender in one atomic step; a refund never reopens a request or an authorization and never restores a released hold; refunds never change settlement membership; the refund appears in the activity feed by the ordinary visibility rule and in both parties' statements  
   check: `python -m pytest tests/stage4/test_i04.py -q`
5. Corrections after stage 4: stage-3 corrections stay available for ordinary direct and request payments; captures and refund payments cannot be corrected (422 linked_payment_immutable); a correction cannot reduce a payment below its already-refunded amount (422 refund_exceeds_payment); correction debits are checked against available funds  
   check: `python -m pytest tests/stage4/test_i05.py -q`
6. POST /correction-batches (settlement operator and Idempotency-Key required; no token -> 401, authenticated non-operator -> 403 forbidden): body {corrections: [{payment_id, expected_revision, amount, effective_at, reason}]} with 1..32 objects and distinct payment_ids, else 422 validation_failed; every item has the ordinary correction fields and validation; unknown payment -> 404 not_found; stale expected revision -> 409 stale_revision; the operator may correct ordinary, request and settlement payments without being a party; captures and refunds stay immutable (422 linked_payment_immutable); unknown fields ignored  
   check: `python -m pytest tests/stage4/test_i06.py -q`
7. Settlement members in batches: correcting any settlement member requires every member of that settlement in the batch, else 422 incomplete_settlement; members of one settlement must have identical effective instants (offset spellings may differ), else 422 validation_failed; single-payment corrections stay available for nonmembers  
   check: `python -m pytest tests/stage4/test_i07.py -q`
8. Batch precedence and atomicity: item errors in input order, then settlement completeness, then resulting current available funds (409 insufficient_funds), then historical total and available at every effective or event boundary (409 historical_overdraft); refund_exceeds_payment and linked_payment_immutable apply per item; affordability uses the combined effect of all proposed revisions; a rejected batch leaves history, balances and idempotency records unchanged  
   check: `python -m pytest tests/stage4/test_i08.py -q`
9. Batch response: 201 {correction_batch_id, recorded_at, revisions} with revisions in input order; all new revisions share recorded_at, strictly later than the previous recorded_at of every member; each revision exposes correction_batch_id; effective times cannot be later than now; a replay returns the original batch response with 200  
   check: `python -m pytest tests/stage4/test_i09.py -q`
10. Originals preserved: original payments and receipts never change; original payment and settlement retries return their original bodies; new statements reflect the new revisions; earlier snapshot tokens keep paging their frozen entries  
   check: `python -m pytest tests/stage4/test_i10.py -q`
11. Concurrency: concurrent corrections (single or batch) sharing any expected payment revision never both succeed; concurrent refunds of one payment never exceed its corrected amount; concurrent identical requests on the new paths with one key -> one 201, the rest 200; balances conserved and available never negative  
   check: `python -m pytest tests/stage4/test_i11.py -q`
12. Exports: a stage-4 service accepts, unchanged, exports produced by this team's stage-1, stage-2 and stage-3 services, keeping settlement membership, corrections and snapshots (tokens keep paging); a stage-4 export/import round-trips refunds, correction batches and their replays  
   check: `python -m pytest tests/stage4/test_i12.py -q`
13. Ten idempotent write paths: POST /payments, /requests, /requests/{id}/pay, /splits, /settlements, /authorizations, /authorizations/{id}/capture, /payments/{id}/corrections, /payments/{id}/refunds and /correction-batches each follow the stage-1 section 7 rules independently  
   check: `python -m pytest tests/stage4/test_i13.py -q`
14. The image builds and runs on its own with -e PORT and a port mapping, no outbound network at run time; RUN.md gives one command a stranger can follow; no nested .git  
   check: `docker build -t pocketful-stage-4-ledger .`
15. The event harness claims stage 4: the --stage 4 run reports 'claimed stage: 4'  
   check: judged by the auditor (no command)
16. The folder's whole test suite passes  
   check: `python -m pytest tests -q`
17. Every fixed name (route, field, code) appears verbatim; code another developer can maintain; the stage-2 screens keep working  
   check: judged by the auditor (no command)
18. Memory headroom: peak container memory stays below 1.5 GiB through the whole suite under --memory 2g, with no OOM kill  
   check: judged by the auditor (no command)
