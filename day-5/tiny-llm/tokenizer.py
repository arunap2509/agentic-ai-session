"""
Tokenizer - tokenizer.py

Wraps Hugging Face's `tokenizers` library - the same production-grade BPE
implementation real tokenizers are built on - instead of a hand-rolled one,
so effort goes into the model and training loop, not into re-debugging
tokenizer internals.

Two character classes are protected from ever being merged, enforced via
pre-tokenization (splitting them into isolated single characters *before*
BPE ever runs, not as an afterthought):

  - digits: the standard fix real LLM tokenizers (GPT-4, Llama) apply, so a
    number always tokenizes the same way regardless of context, and a model
    can reason about digit positions consistently.
  - lowercase letters: this corpus's reversal-task "words" are random
    strings, not real language. Letting BPE merge them fuses arbitrary
    noise-driven letter pairs, and - worse - merges that span across the
    exact boundary between the input word and its reversed answer (since
    the input word's last letter is always the reversed answer's first
    letter, a 100%-frequent pattern BPE will happily exploit). Both break
    the character-level alignment the reversal task depends on.

BPE is left free to merge everything else, which in this corpus means
punctuation like `)=`.
"""

from pathlib import Path

from tokenizers import Regex, Tokenizer
from tokenizers.decoders import Fuse
from tokenizers.models import BPE
from tokenizers.pre_tokenizers import Digits, Sequence, Split
from tokenizers.trainers import BpeTrainer

PAD_TOKEN = "<PAD>"
UNK_TOKEN = "<UNK>"


def _protect_digits_and_letters() -> Sequence:
    return Sequence(
        [
            Digits(individual_digits=True),
            Split(pattern=Regex(r"[a-z]"), behavior="isolated"),
        ]
    )


class BPETokenizer:
    def __init__(self) -> None:
        self._hf = Tokenizer(BPE(unk_token=UNK_TOKEN))
        self._hf.pre_tokenizer = _protect_digits_and_letters()
        self._hf.decoder = Fuse()  # plain concatenation - this corpus has no word boundaries to preserve

    @property
    def vocab_size(self) -> int:
        return self._hf.get_vocab_size()

    @property
    def pad_id(self) -> int:
        return self._hf.token_to_id(PAD_TOKEN)

    @property
    def unk_id(self) -> int:
        return self._hf.token_to_id(UNK_TOKEN)

    def train(self, corpus: str, target_vocab_size: int) -> None:
        trainer = BpeTrainer(vocab_size=target_vocab_size, special_tokens=[PAD_TOKEN, UNK_TOKEN])
        self._hf.train_from_iterator(corpus.splitlines(keepends=True), trainer=trainer)

    def encode(self, text: str) -> list[int]:
        return self._hf.encode(text).ids

    def decode(self, ids: list[int]) -> str:
        return self._hf.decode(ids, skip_special_tokens=True)

    def save(self, path: Path) -> None:
        self._hf.save(str(path))

    @classmethod
    def load(cls, path: Path) -> "BPETokenizer":
        tokenizer = cls.__new__(cls)
        tokenizer._hf = Tokenizer.from_file(str(path))
        return tokenizer
