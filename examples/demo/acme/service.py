from .config import CACHE


def normalize(value):
    if value == 'legacy':
        return 'standard'
    return value.strip().lower()


def calculate(value, use_cache=True):
    normalized = normalize(value)
    if use_cache:
        CACHE[normalized] = len(normalized)
    return len(normalized)


def calculate_duplicate(other, use_cache=True):
    normalized = normalize(other)
    if use_cache:
        CACHE[normalized] = len(normalized)
    return len(normalized)


def wrapper(value):
    return calculate(value)


def obsolete_unreferenced_helper(value):
    return value * 314159
