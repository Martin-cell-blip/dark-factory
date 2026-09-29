"""Fire many requests at once; the service must keep its invariants and never 5xx."""
import threading
from concurrent.futures import ThreadPoolExecutor


def burst(calls, width: int = 50) -> list:
    """Run each zero-argument call concurrently, released together from a barrier."""
    barrier = threading.Barrier(min(width, len(calls)))

    def run(call):
        try:
            barrier.wait(timeout=10)
        except threading.BrokenBarrierError:
            pass
        return call()

    with ThreadPoolExecutor(max_workers=width) as pool:
        return list(pool.map(run, calls))


def statuses(responses) -> list:
    assert all(r.status < 500 for r in responses), [r for r in responses if r.status >= 500]
    return [r.status for r in responses]
