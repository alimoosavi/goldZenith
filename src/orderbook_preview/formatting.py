"""Human-readable formatters for volumes and prices."""


def fmt_vol(n: int) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


def fmt_price(p: float) -> str:
    if not p:
        return "—"
    return f"{int(p):,}"