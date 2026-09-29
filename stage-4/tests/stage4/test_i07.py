"""Item 7: settlement members in batches."""
from datetime import datetime, timedelta, timezone

from refundfx import batch, item, settle
from timefx import ago, correct, pay


def _members(world):
    return settle(world.ann, ("ben", "cat", 100), ("cat", "ben", 40), ("ben", "ann", 5))["payments"]


def test_every_member_is_required(world):
    members = _members(world)
    when = members[0]["created_at"]
    batch(world.ann, [item(members[0], 50, when), item(members[1], 40, when)], status=422,
          code="incomplete_settlement")
    batch(world.ann, [item(m, m["amount"], when) for m in members])


def test_members_share_one_effective_instant(world):
    members = _members(world)
    moment = datetime.fromisoformat(members[0]["created_at"])
    spellings = [moment.astimezone(timezone.utc).isoformat(),
                 moment.astimezone(timezone(timedelta(hours=2))).isoformat(),
                 moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")]
    body = batch(world.ann, [item(m, m["amount"] - 1 if m["amount"] > 1 else 1, s)
                             for m, s in zip(members, spellings)]).json()
    assert len(body["revisions"]) == 3
    fresh = _members(world)
    batch(world.ann, [item(fresh[0], 1, ago(seconds=5)), item(fresh[1], 1, ago(seconds=4)),
                      item(fresh[2], 1, ago(seconds=5))], status=422, code="validation_failed")


def test_single_corrections_stay_for_nonmembers_only(world):
    members = _members(world)
    correct(world.ben, members[0]["payment_id"], 10, ago(seconds=2), status=422,
            code="linked_payment_immutable")
    outside = pay(world.ben, "cat", 100)
    correct(world.ben, outside["payment_id"], 10, outside["created_at"])
