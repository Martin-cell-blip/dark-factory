"""Regenerate stage1_export.json from a running stage-1 service (this team's stage-1 folder).

    cd stage-1 && PORT=18092 python -m pocketful &
    python tests/stage2/upgrade/make_stage1_export.py http://localhost:18092

The file holds the unchanged export plus what the checks need to probe it: live tokens,
a completed idempotent payment (key, body, response), a key whose request failed, and a
pending request id.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "acceptance"))

import client  # noqa: E402
import seed  # noqa: E402


def main(base: str) -> None:
    client.BASE_URL = base
    fx = seed.fixture(settlement_operator_ids=["u_ann"])
    client.expect(client.request("POST", "/_test/reset", fx), 204)
    ann = client.login("ann@pocket.test", seed.PASSWORD)
    ben = client.login("ben@pocket.test", seed.PASSWORD)
    pay_body = {"to_handle": "ben", "amount": 1250, "note": "lunch", "visibility": "private"}
    pay_key = "stage1-pay-key"
    payment = client.expect(ann.post("/payments", pay_body, key=pay_key), 201).json()
    pending = client.expect(ben.write("/requests", {"payer_handle": "ann", "amount": 300,
                                                    "note": "tickets"}), 201).json()
    settle_body = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 40}]}
    client.expect(ann.post("/settlements", settle_body, key="stage1-settle-key"), 201)
    failed_body = {"to_handle": "cat", "amount": 999999}
    client.expect(ben.post("/payments", failed_body, key="stage1-failed-key"), 409)
    export = client.expect(client.request("GET", "/_test/export"), 200).json()
    out = {
        "export": export,
        "tokens": {"ann": ann.token, "ben": ben.token},
        "payment": {"key": pay_key, "body": pay_body, "response": payment},
        "failed": {"key": "stage1-failed-key", "body": failed_body},
        "pending_request_id": pending["request_id"],
        "balances": {"ann": 10000 - 1250, "ben": 2500 + 1250 - 40, "cat": 540},
    }
    (HERE / "stage1_export.json").write_text(json.dumps(out, indent=1, ensure_ascii=False) + "\n",
                                             encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
