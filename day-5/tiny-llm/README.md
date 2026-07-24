# Tiny LLM — Built From Scratch

Every other project in this repo calls an LLM through an API. This one
builds one: a small decoder-only transformer, a custom byte-pair-encoding
tokenizer, and a training loop — all written from scratch on top of
PyTorch's tensors and autograd (no `nn.Transformer`, no pretrained
tokenizer, no borrowed model code).

It's trained to do two things well: **addition** and **string reversal**.
Not because those are useful on their own, but because they're objectively
checkable — the model either got `47+68=115` right or it didn't, which
means every claim below ("it generalizes," "it doesn't extrapolate") is a
number, not a vibe.

## The tasks

```
47+68=115
reverse(hello)=olleh
```

No natural-language instructions — this is a raw language model, not a
chat model. A "query" is just a prompt in the training format, and the
model completes it.

## What's actually being tested

Three splits per task, not two:

1. **Train** — what the model learns from.
2. **Held-out** — same difficulty range as training (1-4 digit addition,
   3-10 letter strings), but examples never seen during training. This is
   the real "did it learn the operation, or memorize specific answers"
   check.
3. **Extrapolation** — harder than anything seen in training (6-7 digit
   addition, 15-20 letter strings). Plain transformers are known to
   struggle here, and the reason is structural, not just empirical:
   position embeddings for positions beyond the longest training example
   barely ever receive a gradient update, so the model is relying on
   undertrained parameters. Expect a real accuracy drop on this split —
   that's the documented limitation being demonstrated, not a bug to fix.

See `train.py`'s final output for the actual numbers from this run.

## The tokenizer: BPE, with one deliberate fix

`tokenizer.py` implements byte-pair encoding from scratch — the same
algorithm GPT/Llama/Claude's tokenizers use: start from individual
characters, repeatedly merge the most frequent adjacent pair into a new
token, until the vocabulary hits a target size.

One rule added on top of textbook BPE: **digits are never allowed to merge
with anything.** Naive BPE tokenizes numbers inconsistently depending on
context (`115` might be one token here, `11`+`5` there), which breaks a
model's ability to align digit positions and reason about carries — a
real, documented reason GPT-3/GPT-4 struggled with arithmetic. GPT-4 and
Llama's actual tokenizers special-case digits for exactly this reason;
`_contains_digit()` in `tokenizer.py` enforces the same rule here.

## The model

`model.py`: token + position embeddings, a stack of pre-norm transformer
blocks (causal self-attention + feed-forward, each in its own residual
branch), a final layernorm, and a linear head to vocab logits. Every
component is its own class with a clear name — `CausalSelfAttention`,
`FeedForward`, `TransformerBlock` — so the whole architecture reads
top-to-bottom in `TinyGPT.__init__`.

## Files

| File | What it does |
|---|---|
| `data.py` | Generates the synthetic corpus (train/held-out/extrapolation, both tasks). Run standalone to regenerate `data/*.txt`. |
| `tokenizer.py` | `BPETokenizer` — train, encode, decode, save, load. |
| `model.py` | `TinyGPT` and its building blocks. |
| `train.py` | Runs the whole pipeline: generate data → train tokenizer → train model → evaluate held-out and extrapolation accuracy → save `checkpoints/model.pt` + `checkpoints/tokenizer.json`. |
| `generate.py` | **Inference only.** Loads a checkpoint and answers prompts. Doesn't import `train.py` or `data.py` at all — this is the one file you need on a machine that never trained anything. |

## Running it

Training (needs the full `day-5` env, including `torch`):
```
cd day-5
python3 -m venv .venv && source .venv/bin/activate   # if not already set up
pip install -r requirements.txt

cd tiny-llm
python train.py
```
No API key needed — this is fully local and offline, unlike the other
day-5 projects.

### Inference on a different machine (e.g. Windows), without retraining

Copy exactly three things to the other machine:
- `checkpoints/model.pt`
- `checkpoints/tokenizer.json`
- `model.py`, `tokenizer.py`, `generate.py` (if you didn't already `git
  clone` the whole repo there)

Then:
```
pip install torch rich
python generate.py
```
`generate.py` auto-detects the available device (`cuda` → `mps` → `cpu`),
so the exact same script runs whether it's on the Mac that trained it or a
Windows box with no GPU at all — inference on a model this size is fast on
CPU alone. A `.pt` checkpoint is just serialized tensors; the only reason
you need `model.py` alongside it is that `state_dict` holds weights, not
architecture — PyTorch needs the class definition to know what to load
them into.

## Design choices worth knowing about

- **Training data is entirely synthetic and reproducible** — a fixed
  random seed (`SEED = 42` in `data.py`), no external dataset, no download.
- **Char-level base vocabulary, BPE on top** — the base alphabet is every
  character that appears (`0-9`, `a-z`, `+`, `=`, `(`, `)`, `\n`, `<PAD>`),
  and BPE merges compress frequent multi-character sequences (like the
  literal string `reverse(`, which appears in every reversal example) into
  single tokens.
- **Greedy decoding, not sampling** — `TinyGPT.generate()` always takes the
  highest-probability next token. Correctness is what's being measured
  here, not creative variation.
- **Eval is batched by prompt token length, not looped one example at a
  time** — digits are always exactly one token each (thanks to the
  digit-splitting rule above), so addition prompts group into a handful of
  exact-length buckets with zero padding needed. This turned what was
  initially a ~16-minute eval pass into a few seconds; see the comment on
  `exact_match_accuracy` in `train.py` for the full reasoning.
