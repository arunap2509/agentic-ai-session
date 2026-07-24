"""
Generate - generate.py

Inference only - no training happens here, and this file doesn't import
train.py or data.py at all. It just loads whatever train.py already saved
to checkpoints/ (model.pt + tokenizer.json) and answers prompts.

This is the one script you need on a machine that never ran training: copy
the checkpoints/ folder over and run this - it auto-detects whatever device
is available (cuda -> mps -> cpu), so the exact same code runs on the Mac
that trained it or a Windows box that didn't, with zero edits.

Run:
    python generate.py
"""

import sys
from pathlib import Path

import torch
from rich.console import Console

sys.path.insert(0, str(Path(__file__).resolve().parent))
from model import TinyGPT
from tokenizer import BPETokenizer

console = Console()

CHECKPOINT_DIR = Path(__file__).resolve().parent / "checkpoints"


def get_device() -> torch.device:
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def load_model(device: torch.device) -> tuple[TinyGPT, BPETokenizer]:
    tokenizer = BPETokenizer.load(CHECKPOINT_DIR / "tokenizer.json")
    checkpoint = torch.load(CHECKPOINT_DIR / "model.pt", map_location=device)
    model = TinyGPT(**checkpoint["config"])
    model.load_state_dict(checkpoint["model_state_dict"])
    model.to(device)
    model.eval()
    return model, tokenizer


def answer(model: TinyGPT, tokenizer: BPETokenizer, device: torch.device, prompt: str) -> str:
    encoded = tokenizer.encode(prompt)
    if tokenizer.unk_id in encoded:
        # Better to say so than to silently feed the model a token it was
        # never trained on and hand back a confident-looking wrong answer.
        raise ValueError(
            f"'{prompt}' contains a character this model was never trained on "
            f"(only digits, lowercase letters, and + = ( ) are known)."
        )
    ids = torch.tensor([encoded], dtype=torch.long, device=device)
    max_new_tokens = min(25, model.block_size - ids.size(1))
    out_ids = model.generate(ids, max_new_tokens=max_new_tokens)
    full_text = tokenizer.decode(out_ids[0].tolist())
    return full_text[len(prompt) :].split("\n")[0]


def main() -> None:
    if not (CHECKPOINT_DIR / "model.pt").exists():
        console.print(
            f"[bold red]No checkpoint found at {CHECKPOINT_DIR}/model.pt[/bold red] - "
            f"run train.py first, or copy a trained checkpoints/ folder here."
        )
        return

    device = get_device()
    console.rule("[bold]Tiny LLM - Inference[/bold]")
    console.print(f"[dim]Device: {device}[/dim]\n")
    console.print(
        "Prompt format matters - this model only knows what it was trained on:\n"
        "  [cyan]47+68=[/cyan]            (addition)\n"
        "  [cyan]reverse(hello)=[/cyan]   (string reversal)\n"
    )
    model, tokenizer = load_model(device)

    while True:
        prompt = console.input("[bold cyan]Prompt (blank to quit):[/bold cyan] ").strip()
        if not prompt:
            break
        try:
            result = answer(model, tokenizer, device, prompt)
        except ValueError as e:
            # A prompt using a character the tokenizer never saw in training
            # (e.g. "-" instead of "+") shouldn't kill the whole session -
            # report it and keep the REPL open for the next attempt.
            console.print(f"  [red]{e}[/red]\n")
            continue
        console.print(f"  -> [green]{result}[/green]\n")


if __name__ == "__main__":
    main()
