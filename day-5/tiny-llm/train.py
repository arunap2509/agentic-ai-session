"""
Train - train.py

Generates the corpus (data.py), trains a BPE tokenizer on it (tokenizer.py),
trains TinyGPT (model.py) on next-token prediction, and evaluates two
different things at the end - not just one:

  1. Held-out accuracy: examples in the SAME digit/length range as
     training, but never seen during training. This is the real "did it
     learn or memorize" check.
  2. Extrapolation accuracy: examples HARDER than anything seen in
     training (more digits, longer strings). Plain transformers are known
     to struggle here - a real drop is the documented limitation, not a
     bug to chase. Positions beyond the longest training example are
     structurally undertrained: their position-embedding vectors barely
     ever got a gradient update, so anything relying on them is close to
     random - that's the actual mechanism behind the failure, not just an
     empirical observation.

Saves checkpoints/model.pt + checkpoints/tokenizer.json at the end - the
only two files generate.py needs, on this machine or any other with
PyTorch installed (see generate.py's docstring for the portability story).

Run:
    python train.py
"""

import sys
import time
from pathlib import Path

import torch
from rich import box
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).resolve().parent))
from data import build_corpus, save_corpus
from model import TinyGPT
from tokenizer import BPETokenizer

console = Console()

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"

BLOCK_SIZE = 80  # comfortably covers the longest extrapolation example after tokenization
TOKENIZER_VOCAB_SIZE = 200
TOKENIZER_TRAIN_SAMPLE_SIZE = 5_000  # a sample is plenty - the corpus is highly repetitive

EMBED_DIM = 128
NUM_HEADS = 4
NUM_LAYERS = 4
DROPOUT = 0.1

BATCH_SIZE = 128
NUM_EPOCHS = 25  # exact-match accuracy on arithmetic needs more training than the loss curve alone suggests
LEARNING_RATE = 3e-4


def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def encode_lines(tokenizer: BPETokenizer, lines: list[str]) -> torch.Tensor:
    rows = []
    for line in lines:
        ids = tokenizer.encode(line)[:BLOCK_SIZE]
        ids = ids + [tokenizer.pad_id] * (BLOCK_SIZE - len(ids))
        rows.append(ids)
    return torch.tensor(rows, dtype=torch.long)


def iterate_batches(data: torch.Tensor, batch_size: int, device: torch.device, generator: torch.Generator):
    perm = torch.randperm(data.size(0), generator=generator)
    for start in range(0, data.size(0), batch_size):
        batch = data[perm[start : start + batch_size]].to(device)
        yield batch[:, :-1], batch[:, 1:]


MAX_ANSWER_TOKENS = 25  # generous margin over the longest possible answer (a 21-char reversed word)


@torch.no_grad()
def exact_match_accuracy(
    model: TinyGPT,
    tokenizer: BPETokenizer,
    device: torch.device,
    examples: list[str],
    sample_size: int,
    eval_batch_size: int = 200,
) -> float:
    """For each example "prompt=answer\\n", feeds the model just the prompt
    and checks whether its generated completion exactly matches the true
    answer - the strictest, clearest correctness check for these tasks.

    Batches examples by prompt TOKEN length so each generate() call is one
    plain rectangular tensor with no padding needed (digits are always one
    token each, so addition prompts group by digit count exactly; reversal
    prompts group almost as cleanly). This matters a lot in practice:
    calling generate() once per example is dominated by per-call overhead
    on a model this small, not actual compute - grouping into batches is
    the difference between an eval pass taking minutes instead of seconds.
    """
    sample = examples[:sample_size]
    parsed = []
    for line in sample:
        prompt, true_answer = line.split("=", 1)
        prompt += "="
        parsed.append((prompt, true_answer.rstrip("\n"), tokenizer.encode(prompt)))

    by_prompt_length: dict[int, list[int]] = {}
    for i, (_, _, ids) in enumerate(parsed):
        by_prompt_length.setdefault(len(ids), []).append(i)

    correct = 0
    for prompt_len, indices in by_prompt_length.items():
        max_new_tokens = min(MAX_ANSWER_TOKENS, BLOCK_SIZE - prompt_len)
        for start in range(0, len(indices), eval_batch_size):
            chunk = indices[start : start + eval_batch_size]
            ids = torch.tensor([parsed[i][2] for i in chunk], dtype=torch.long, device=device)
            out_ids = model.generate(ids, max_new_tokens=max_new_tokens)
            for row, i in zip(out_ids.tolist(), chunk):
                prompt, true_answer, _ = parsed[i]
                generated = tokenizer.decode(row)[len(prompt) :].split("\n")[0]
                if generated == true_answer:
                    correct += 1
    return correct / len(sample)


def main() -> None:
    device = get_device()
    console.rule("[bold]Tiny LLM - Training[/bold]")
    console.print(f"[dim]Device: {device}[/dim]\n")

    console.print("Generating synthetic corpus...")
    corpus = build_corpus()
    save_corpus(corpus)
    for name, lines in corpus.items():
        console.print(f"  [dim]{name}: {len(lines)} examples, e.g. {lines[0].strip()!r}[/dim]")

    console.print("\nTraining BPE tokenizer on a sample of the training corpus...")
    train_lines = corpus["addition_train"] + corpus["reversal_train"]
    # Sample from each task separately, not the concatenated list - a blind
    # slice would land entirely inside addition_train (40k > sample size)
    # and the tokenizer would never see a single reversal-task letter.
    half = TOKENIZER_TRAIN_SAMPLE_SIZE // 2
    tokenizer_sample = "".join(corpus["addition_train"][:half] + corpus["reversal_train"][:half])
    tokenizer = BPETokenizer()
    tokenizer.train(tokenizer_sample, target_vocab_size=TOKENIZER_VOCAB_SIZE)
    console.print(f"  [dim]Vocab size: {tokenizer.vocab_size}[/dim]")

    console.print("\nEncoding training examples...")
    train_data = encode_lines(tokenizer, train_lines)

    CHECKPOINT_DIR.mkdir(exist_ok=True)
    tokenizer.save(CHECKPOINT_DIR / "tokenizer.json")

    model = TinyGPT(
        vocab_size=tokenizer.vocab_size,
        block_size=BLOCK_SIZE,
        embed_dim=EMBED_DIM,
        num_heads=NUM_HEADS,
        num_layers=NUM_LAYERS,
        dropout=DROPOUT,
    ).to(device)
    num_params = sum(p.numel() for p in model.parameters())
    console.print(f"\nModel: {num_params:,} parameters\n")

    optimizer = torch.optim.AdamW(model.parameters(), lr=LEARNING_RATE)
    generator = torch.Generator().manual_seed(42)

    summary_table = Table(box=box.SIMPLE_HEAVY)
    summary_table.add_column("Epoch", justify="right")
    summary_table.add_column("Train Loss", justify="right")
    summary_table.add_column("Addition Held-out Acc", justify="right")
    summary_table.add_column("Reversal Held-out Acc", justify="right")
    summary_table.add_column("Elapsed", justify="right")

    start_time = time.perf_counter()
    addition_acc = reversal_acc = 0.0
    for epoch in range(1, NUM_EPOCHS + 1):
        model.train()
        epoch_losses = []
        for xb, yb in iterate_batches(train_data, BATCH_SIZE, device, generator):
            _, loss = model(xb, yb, pad_id=tokenizer.pad_id)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            epoch_losses.append(loss.item())

        model.eval()
        # Full held-out sets, not a sample - batched eval is cheap enough now
        # that there's no reason to trade accuracy of the signal for speed.
        addition_acc = exact_match_accuracy(
            model, tokenizer, device, corpus["addition_heldout"], len(corpus["addition_heldout"])
        )
        reversal_acc = exact_match_accuracy(
            model, tokenizer, device, corpus["reversal_heldout"], len(corpus["reversal_heldout"])
        )
        avg_loss = sum(epoch_losses) / len(epoch_losses)
        elapsed = time.perf_counter() - start_time

        console.print(
            f"Epoch {epoch:>2}/{NUM_EPOCHS}  loss={avg_loss:.4f}  "
            f"addition_heldout={addition_acc:.1%}  reversal_heldout={reversal_acc:.1%}  "
            f"elapsed={elapsed:.0f}s"
        )
        summary_table.add_row(str(epoch), f"{avg_loss:.4f}", f"{addition_acc:.1%}", f"{reversal_acc:.1%}", f"{elapsed:.0f}s")

    console.print()
    console.print(summary_table)

    console.rule("[bold]Extrapolation Test[/bold]")
    console.print(
        "[dim]Same tasks, but harder than anything seen in training - more digits, "
        "longer strings. Expect a real drop here; that's the documented limitation, "
        "not a bug.[/dim]\n"
    )
    addition_extra_acc = exact_match_accuracy(
        model, tokenizer, device, corpus["addition_extrapolation"], len(corpus["addition_extrapolation"])
    )
    reversal_extra_acc = exact_match_accuracy(
        model, tokenizer, device, corpus["reversal_extrapolation"], len(corpus["reversal_extrapolation"])
    )

    extrapolation_table = Table(box=box.SIMPLE_HEAVY)
    extrapolation_table.add_column("Task")
    extrapolation_table.add_column("Held-out Acc (trained range)", justify="right")
    extrapolation_table.add_column("Extrapolation Acc (harder)", justify="right")
    extrapolation_table.add_row("Addition", f"{addition_acc:.1%}", f"{addition_extra_acc:.1%}")
    extrapolation_table.add_row("Reversal", f"{reversal_acc:.1%}", f"{reversal_extra_acc:.1%}")
    console.print(extrapolation_table)

    torch.save(
        {
            "model_state_dict": model.state_dict(),
            "config": {
                "vocab_size": tokenizer.vocab_size,
                "block_size": BLOCK_SIZE,
                "embed_dim": EMBED_DIM,
                "num_heads": NUM_HEADS,
                "num_layers": NUM_LAYERS,
                "dropout": DROPOUT,
            },
        },
        CHECKPOINT_DIR / "model.pt",
    )
    console.print("\n[bold green]Saved checkpoints/model.pt and checkpoints/tokenizer.json[/bold green]")
    console.print(
        "[dim]Copy the checkpoints/ folder to any machine with PyTorch installed and run "
        "generate.py there - no retraining needed.[/dim]"
    )


if __name__ == "__main__":
    main()
