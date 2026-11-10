from susurros.streaming import StreamState, Word


def hyp(text: str, start: float = 0.0, step: float = 0.4) -> list[Word]:
    """Synthetic hypothesis: one word every `step` seconds."""
    return [Word(start + i * step, start + (i + 1) * step, " " + w) for i, w in enumerate(text.split())]


def said(words: list[Word]) -> str:
    return "".join(w.text for w in words).strip()


def test_words_are_committed_only_when_two_passes_agree():
    state = StreamState()
    assert state.update(hyp("hola qué")) == []                       # first pass: nothing firm yet
    assert said(state.update(hyp("hola qué tal estás"))) == "hola qué"
    assert said(state.update(hyp("hola qué tal estamos hoy"))) == "tal"   # "estás" changed: not committed
    assert said(state.update(hyp("hola qué tal estamos hoy"), final=True)) == "estamos hoy"
    assert said(state.committed) == "hola qué tal estamos hoy"


def test_punctuation_and_case_changes_still_count_as_agreement():
    state = StreamState()
    state.update(hyp("vale pues"))
    assert said(state.update(hyp("Vale, pues nada"))) == "Vale, pues"


def test_committed_words_are_not_repeated_when_timestamps_drift():
    state = StreamState()
    state.update(hyp("uno dos tres"))
    state.update(hyp("uno dos tres cuatro"))
    # The next pass shifts the timestamps and "tres" lands again after what is already committed.
    drifted = hyp("tres cuatro cinco", start=1.15)
    state.update(drifted)
    state.update(drifted, final=True)
    assert said(state.committed) == "uno dos tres cuatro cinco"


def test_buffer_is_trimmed_at_the_last_committed_word():
    state = StreamState()
    long = "a b c d e f g h i j k l m n o p q r s t u v w x y z a2 b2"
    state.update(hyp(long))
    state.update(hyp(long + " c2"))
    state.trim(total_seconds=12.0)
    assert state.trim_s == state.committed_time > 10
    state.trim(total_seconds=13.0)            # with less than 10 s pending it trims no further
    assert state.trim_s == state.committed_time
    assert state.prompt.endswith("a2 b2")


def test_final_pass_with_nothing_heard_commits_nothing():
    state = StreamState()
    assert state.update([], final=True) == [] and state.committed == []


def test_real_repetitions_survive_a_commit_boundary():
    # "no no no vale": the third "no" starts after the last committed one; it is not a timestamp echo.
    state = StreamState()
    state.update(hyp("no no"))
    state.update(hyp("no no no vale"))
    state.update(hyp("no no no vale"), final=True)
    assert said(state.committed) == "no no no vale"


def test_short_word_right_after_the_boundary_is_kept_despite_jitter():
    state = StreamState()
    base = hyp("voy a casa")                                  # 0–1.2 s
    state.update(base)
    state.update(base + [Word(1.2, 1.3, " y")])               # commits "voy a casa"
    shifted = [Word(1.26, 1.36, " y"), Word(1.36, 1.8, " luego"), Word(1.8, 2.2, " vuelvo")]
    state.update(shifted)
    state.update(shifted, final=True)
    assert said(state.committed) == "voy a casa y luego vuelvo"


def test_flush_commits_the_pending_hypothesis():
    state = StreamState()
    state.update(hyp("esto es el fin"))
    assert said(state.flush()) == "esto es el fin" and state.pending == []


def test_overdue_when_passes_never_agree():
    state = StreamState()
    assert not state.overdue(15.0) and state.overdue(21.0)
    state.update(hyp("a b"))
    state.update(hyp("a b c"))                                # commits up to 0.8 s
    assert not state.overdue(20.0) and state.overdue(21.0)


def test_prompt_only_contains_text_that_left_the_buffer():
    state = StreamState()
    state.update(hyp("uno dos tres"))
    state.update(hyp("uno dos tres cuatro"))
    assert state.prompt == ""                                 # everything is still in the pending audio
    state.trim_s = 0.8
    assert state.prompt == "uno dos"
