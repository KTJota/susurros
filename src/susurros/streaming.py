"""Live dictation: decides which words are already final while the user keeps talking.

Whisper does not transcribe continuously, so every second the pending audio is transcribed
again and a word is only accepted when two consecutive passes agree on it
("local agreement"). What has been typed cannot be taken back, hence the caution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_BUFFER_S = 10.0   # beyond this, the already committed audio is discarded
HARD_CAP_S = 20.0     # and beyond this, what is pending is committed even without agreement
_JITTER_S = 0.15      # how much the timestamps of the same word wobble between two passes


@dataclass
class Word:
    start: float
    end: float
    text: str      # as Whisper gives it, with its leading space


def _norm(text: str) -> str:
    return re.sub(r"[^\w]", "", text.lower())


@dataclass
class StreamState:
    committed: list[Word] = field(default_factory=list)
    pending: list[Word] = field(default_factory=list)   # latest hypothesis, not yet committed
    trim_s: float = 0.0                                  # audio already discarded from the start
    typed: str = ""                                      # text delivered so far
    language: str = ""                                   # language fixed after the first pass

    @property
    def committed_time(self) -> float:
        return self.committed[-1].end if self.committed else 0.0

    def update(self, words: list[Word], final: bool = False) -> list[Word]:
        """Takes a new hypothesis and returns the words that become final."""
        boundary = self.committed_time
        # Drop what clearly lies before what is already committed…
        fresh = [w for w in words if w.end > boundary + 0.05 and w.start > boundary - _JITTER_S]
        # …and what is the last committed word seen again with shifted timestamps.
        # Only if it straddles the boundary: a real repetition ("no no", "uno uno dos") starts later.
        tail = [_norm(w.text) for w in self.committed[-5:]]
        for n in range(min(len(tail), len(fresh), 5), 0, -1):
            if fresh[n - 1].start < boundary and tail[-n:] == [_norm(w.text) for w in fresh[:n]]:
                fresh = fresh[n:]
                break
        if final:
            agreed, self.pending = fresh, []
        else:
            agreed = []
            for before, now in zip(self.pending, fresh, strict=False):
                if _norm(before.text) != _norm(now.text):
                    break
                agreed.append(now)
            self.pending = fresh[len(agreed):]
        self.committed += agreed
        return agreed

    def flush(self) -> list[Word]:
        """Accepts the pending hypothesis (closing with no new audio, or wait limit reached)."""
        agreed, self.pending = self.pending, []
        self.committed += agreed
        return agreed

    def trim(self, total_seconds: float) -> None:
        if self.committed and total_seconds - self.trim_s > MAX_BUFFER_S:
            self.trim_s = max(self.trim_s, self.committed_time)

    def overdue(self, total_seconds: float) -> bool:
        """Too much uncommitted audio: the passes do not agree and each one costs more."""
        return total_seconds - max(self.trim_s, self.committed_time) > HARD_CAP_S

    @property
    def prompt(self) -> str:
        """Context for the next pass: only committed text that has already left the pending audio
        (repeating to Whisper words it can still hear makes it skip or duplicate them)."""
        gone = "".join(w.text for w in self.committed if w.end <= self.trim_s)
        return gone[-200:].strip()
