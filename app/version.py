"""Dashboard release metadata — auto-bumped by scripts/push.py."""

__version__ = "0.1.6"
__build__ = "0.1.6"
__name__ = "Personal Dashboard"


def bump_build(current: str) -> str:
    """0.1 -> 0.1.1 -> 0.1.2 ..."""
    parts = current.split(".")
    if len(parts) == 2:
        return f"{current}.1"
    try:
        patch = int(parts[-1])
    except ValueError:
        return f"{current}.1"
    return ".".join(parts[:-1]) + f".{patch + 1}"
