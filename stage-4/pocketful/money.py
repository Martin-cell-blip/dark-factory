"""Section 9: equal split in whole minor units."""


def equal_split(amount: int, n: int) -> list[int]:
    """Shares differ by at most one unit; the larger shares go to the first participants."""
    base, remainder = divmod(amount, n)
    return [base + 1 if i < remainder else base for i in range(n)]
