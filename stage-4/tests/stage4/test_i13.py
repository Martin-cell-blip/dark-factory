"""Item 13: ten idempotent write paths, each with the stage-1 section 7 rules."""
from client import expect, new_key
from refundfx import item
from timefx import pay


def _paths(world):
    """(client, path, body, other body) for each of the ten paths."""
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 10}), 201).json()
    held = expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": 500}),
                  201).json()
    to_ben = pay(world.ann, "ben", 400)
    fixable = pay(world.ann, "cat", 300)
    batchable = pay(world.cat, "ann", 20)
    return [
        (world.ann, "/payments", {"to_handle": "ben", "amount": 1},
         {"to_handle": "ben", "amount": 2}),
        (world.ann, "/requests", {"payer_handle": "ben", "amount": 1},
         {"payer_handle": "ben", "amount": 2}),
        (world.ann, f"/requests/{rq['request_id']}/pay", {}, {"visibility": "private"}),
        (world.ann, "/splits", {"amount": 9, "participant_handles": ["ben"]},
         {"amount": 8, "participant_handles": ["ben"]}),
        (world.ann, "/settlements", {"transfers": [{"from_handle": "ben", "to_handle": "cat",
                                                    "amount": 1}]},
         {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 2}]}),
        (world.ann, "/authorizations", {"to_handle": "cat", "amount": 1},
         {"to_handle": "cat", "amount": 2}),
        (world.ben, f"/authorizations/{held['authorization_id']}/capture",
         {"amount": 10, "final": False}, {"amount": 11, "final": False}),
        (world.ann, f"/payments/{fixable['payment_id']}/corrections",
         {"expected_revision": 1, "amount": 200, "effective_at": fixable["created_at"],
          "reason": "a"},
         {"expected_revision": 1, "amount": 201, "effective_at": fixable["created_at"],
          "reason": "a"}),
        (world.ben, f"/payments/{to_ben['payment_id']}/refunds", {"amount": 5}, {"amount": 6}),
        (world.ann, "/correction-batches", {"corrections": [item(batchable, 10)]},
         {"corrections": [item(batchable, 11)]}),
    ]


def test_each_path_follows_section_seven(world):
    paths = _paths(world)
    assert len(paths) == 10
    for client, path, body, other in paths:
        expect(client.post(path, body), 400, "missing_idempotency_key")
        expect(client.post(path, body, key=""), 400, "missing_idempotency_key")
        expect(client.post(path, body, key="k" * 256), 422, "validation_failed")
        key = new_key()
        first = expect(client.post(path, body, key=key), 201).json()
        assert expect(client.post(path, body, key=key), 200).json() == first, path
        expect(client.post(path, other, key=key), 409, "idempotency_key_reuse")
        stranger = world.cat if client is not world.cat else world.ben
        resp = stranger.post(path, body, key=key)
        assert resp.status != 200, f"keys are per user on {path}"
