"""
Model - model.py

A minimal decoder-only transformer (GPT-style), built directly on PyTorch's
tensor ops and autograd - no nn.Transformer, no borrowed attention
implementation. Every piece (embeddings, causal self-attention, the
feed-forward block, the residual+layernorm wiring) is written out here so
it's inspectable end to end.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class CausalSelfAttention(nn.Module):
    """Multi-head self-attention where each position can only attend to
    itself and earlier positions - the "causal" mask that makes this a
    left-to-right language model instead of a bidirectional encoder."""

    def __init__(self, embed_dim: int, num_heads: int, block_size: int, dropout: float) -> None:
        super().__init__()
        assert embed_dim % num_heads == 0, "embed_dim must divide evenly across num_heads"
        self.num_heads = num_heads
        self.head_dim = embed_dim // num_heads

        self.qkv_proj = nn.Linear(embed_dim, 3 * embed_dim)
        self.out_proj = nn.Linear(embed_dim, embed_dim)
        self.dropout = nn.Dropout(dropout)
        self.register_buffer("causal_mask", torch.tril(torch.ones(block_size, block_size)).bool())

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        batch_size, seq_len, embed_dim = x.shape

        q, k, v = self.qkv_proj(x).chunk(3, dim=-1)
        q = q.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)

        attn_scores = (q @ k.transpose(-2, -1)) / (self.head_dim ** 0.5)
        mask = self.causal_mask[:seq_len, :seq_len]
        attn_scores = attn_scores.masked_fill(~mask, float("-inf"))
        attn_weights = self.dropout(F.softmax(attn_scores, dim=-1))

        out = attn_weights @ v
        out = out.transpose(1, 2).contiguous().view(batch_size, seq_len, embed_dim)
        return self.out_proj(out)


class FeedForward(nn.Module):
    """Standard transformer MLP block: expand, non-linearity, project back down."""

    def __init__(self, embed_dim: int, hidden_mult: int, dropout: float) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(embed_dim, hidden_mult * embed_dim),
            nn.GELU(),
            nn.Linear(hidden_mult * embed_dim, embed_dim),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class TransformerBlock(nn.Module):
    """One attention + feed-forward block, each wrapped in a residual
    connection with pre-normalization (layernorm before the sublayer, not
    after - trains more stably than the original Transformer paper's
    post-norm arrangement, which is why every modern LLM uses pre-norm)."""

    def __init__(self, embed_dim: int, num_heads: int, block_size: int, dropout: float) -> None:
        super().__init__()
        self.ln1 = nn.LayerNorm(embed_dim)
        self.attn = CausalSelfAttention(embed_dim, num_heads, block_size, dropout)
        self.ln2 = nn.LayerNorm(embed_dim)
        self.ff = FeedForward(embed_dim, hidden_mult=4, dropout=dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.attn(self.ln1(x))
        x = x + self.ff(self.ln2(x))
        return x


class TinyGPT(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        block_size: int,
        embed_dim: int = 128,
        num_heads: int = 4,
        num_layers: int = 4,
        dropout: float = 0.1,
    ) -> None:
        super().__init__()
        self.block_size = block_size
        self.token_embedding = nn.Embedding(vocab_size, embed_dim)
        self.position_embedding = nn.Embedding(block_size, embed_dim)
        self.dropout = nn.Dropout(dropout)
        self.blocks = nn.ModuleList(
            [TransformerBlock(embed_dim, num_heads, block_size, dropout) for _ in range(num_layers)]
        )
        self.ln_final = nn.LayerNorm(embed_dim)
        self.lm_head = nn.Linear(embed_dim, vocab_size, bias=False)

    def forward(
        self, idx: torch.Tensor, targets: torch.Tensor | None = None, pad_id: int = 0
    ) -> tuple[torch.Tensor, torch.Tensor | None]:
        batch_size, seq_len = idx.shape
        positions = torch.arange(seq_len, device=idx.device)

        x = self.dropout(self.token_embedding(idx) + self.position_embedding(positions))
        for block in self.blocks:
            x = block(x)
        x = self.ln_final(x)
        logits = self.lm_head(x)

        if targets is None:
            return logits, None

        loss = F.cross_entropy(logits.view(-1, logits.size(-1)), targets.reshape(-1), ignore_index=pad_id)
        return logits, loss

    @torch.no_grad()
    def generate(self, idx: torch.Tensor, max_new_tokens: int) -> torch.Tensor:
        """Greedy autoregressive sampling: repeatedly predict the next
        token and append it, for exactly max_new_tokens steps. Greedy
        (always take the highest-probability token) rather than sampling
        with temperature, since correctness - did it get the arithmetic
        right - is what we're measuring, not creative variety.

        Always runs the full max_new_tokens rather than stopping early at
        a stop token, so one call can generate a whole batch of prompts at
        once (different rows finish "early" at different lengths - there's
        no single point to stop the whole batch at). The caller truncates
        each row's decoded text at its own first stop token; a few extra
        forward passes per call costs nothing on a model this size.
        """
        self.eval()
        for _ in range(max_new_tokens):
            idx_cropped = idx[:, -self.block_size :]
            logits, _ = self(idx_cropped)
            next_token = logits[:, -1, :].argmax(dim=-1, keepdim=True)
            idx = torch.cat([idx, next_token], dim=1)
        return idx
