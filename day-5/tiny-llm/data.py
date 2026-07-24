"""
Data - data.py

Generates the tiny LLM's entire training corpus from scratch - no external
dataset, no download. Two tasks (addition, string reversal), each split
into:
  - a training set
  - a held-out test set: same difficulty range as training, but examples
    the model never saw - the real "did it learn or memorize" check
  - an extrapolation set: harder than anything seen in training (more
    digits, longer strings) - the classic "transformers don't reliably
    generalize past what they were trained on" demo

Run directly to regenerate the corpus files under data/:
    python data.py
"""

import random
from pathlib import Path

SEED = 42

ADDITION_TRAIN_MIN_DIGITS = 1
ADDITION_TRAIN_MAX_DIGITS = 4
ADDITION_EXTRAPOLATION_MIN_DIGITS = 6
ADDITION_EXTRAPOLATION_MAX_DIGITS = 7
ADDITION_TRAIN_SIZE = 40_000
ADDITION_HELDOUT_SIZE = 4_000
ADDITION_EXTRAPOLATION_SIZE = 500

REVERSAL_TRAIN_MIN_LEN = 3
REVERSAL_TRAIN_MAX_LEN = 10
REVERSAL_EXTRAPOLATION_MIN_LEN = 15
REVERSAL_EXTRAPOLATION_MAX_LEN = 20
REVERSAL_TRAIN_SIZE = 20_000
REVERSAL_HELDOUT_SIZE = 2_000
REVERSAL_EXTRAPOLATION_SIZE = 500

ALPHABET = "abcdefghijklmnopqrstuvwxyz"

DATA_DIR = Path(__file__).resolve().parent / "data"


def format_addition(a: int, b: int) -> str:
    return f"{a}+{b}={a + b}\n"


def format_reversal(word: str) -> str:
    return f"reverse({word})={word[::-1]}\n"


def _random_number_with_digits(rng: random.Random, num_digits: int) -> int:
    if num_digits <= 1:
        return rng.randint(0, 9)
    low, high = 10 ** (num_digits - 1), 10 ** num_digits - 1
    return rng.randint(low, high)


def generate_addition_pairs(
    rng: random.Random, count: int, min_digits: int, max_digits: int
) -> list[tuple[int, int]]:
    """Unique (a, b) pairs, each operand's digit count sampled independently
    from [min_digits, max_digits]."""
    seen: set[tuple[int, int]] = set()
    while len(seen) < count:
        a = _random_number_with_digits(rng, rng.randint(min_digits, max_digits))
        b = _random_number_with_digits(rng, rng.randint(min_digits, max_digits))
        seen.add((a, b))
    return list(seen)


def generate_reversal_words(
    rng: random.Random, count: int, min_len: int, max_len: int
) -> list[str]:
    """Unique random lowercase strings, length sampled from [min_len, max_len]."""
    seen: set[str] = set()
    while len(seen) < count:
        length = rng.randint(min_len, max_len)
        seen.add("".join(rng.choices(ALPHABET, k=length)))
    return list(seen)


def build_corpus() -> dict[str, list[str]]:
    """Returns every split as a list of formatted example strings."""
    rng = random.Random(SEED)

    addition_pairs = generate_addition_pairs(
        rng,
        ADDITION_TRAIN_SIZE + ADDITION_HELDOUT_SIZE,
        ADDITION_TRAIN_MIN_DIGITS,
        ADDITION_TRAIN_MAX_DIGITS,
    )
    rng.shuffle(addition_pairs)
    addition_train = addition_pairs[:ADDITION_TRAIN_SIZE]
    addition_heldout = addition_pairs[ADDITION_TRAIN_SIZE:]
    addition_extrapolation = generate_addition_pairs(
        rng, ADDITION_EXTRAPOLATION_SIZE, ADDITION_EXTRAPOLATION_MIN_DIGITS, ADDITION_EXTRAPOLATION_MAX_DIGITS
    )

    reversal_words = generate_reversal_words(
        rng,
        REVERSAL_TRAIN_SIZE + REVERSAL_HELDOUT_SIZE,
        REVERSAL_TRAIN_MIN_LEN,
        REVERSAL_TRAIN_MAX_LEN,
    )
    rng.shuffle(reversal_words)
    reversal_train = reversal_words[:REVERSAL_TRAIN_SIZE]
    reversal_heldout = reversal_words[REVERSAL_TRAIN_SIZE:]
    reversal_extrapolation = generate_reversal_words(
        rng, REVERSAL_EXTRAPOLATION_SIZE, REVERSAL_EXTRAPOLATION_MIN_LEN, REVERSAL_EXTRAPOLATION_MAX_LEN
    )

    return {
        "addition_train": [format_addition(a, b) for a, b in addition_train],
        "addition_heldout": [format_addition(a, b) for a, b in addition_heldout],
        "addition_extrapolation": [format_addition(a, b) for a, b in addition_extrapolation],
        "reversal_train": [format_reversal(w) for w in reversal_train],
        "reversal_heldout": [format_reversal(w) for w in reversal_heldout],
        "reversal_extrapolation": [format_reversal(w) for w in reversal_extrapolation],
    }


def save_corpus(corpus: dict[str, list[str]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    for name, lines in corpus.items():
        (DATA_DIR / f"{name}.txt").write_text("".join(lines))


def load_corpus() -> dict[str, list[str]]:
    return {path.stem: path.read_text().splitlines(keepends=True) for path in DATA_DIR.glob("*.txt")}


if __name__ == "__main__":
    corpus = build_corpus()
    save_corpus(corpus)
    for name, lines in corpus.items():
        print(f"{name}: {len(lines)} examples, e.g. {lines[0].strip()!r}")
