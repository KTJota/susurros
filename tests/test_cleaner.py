import pytest

from susurros.cleaner import _plausible_cleanup, clean, clean_live_chunk, clean_rules, count_fixes


@pytest.mark.parametrize("raw, expected", [
    ("Ehh, pues mmm creo que sí.", "Pues creo que sí."),
    ("Eh... vamos a ver, um, mañana.", "Vamos a ver, mañana."),
    ("Yo yo yo creo que es mejor.", "Yo creo que es mejor."),
    ("Yo creo que yo creo que deberíamos esperar.", "Yo creo que deberíamos esperar."),
    ("Vamos pa- para casa.", "Vamos para casa."),
    ("Tengo que, que llamar al médico.", "Tengo que llamar al médico."),
    ("Quedamos a las a las cinco.", "Quedamos a las cinco."),
    ("Hmm. Mándalo mañana.", "Mándalo mañana."),
    ("So, uh, I think we should, um, wait.", "So, I think we should, wait."),
    # The filler opens a sentence: it takes its comma along and the capital moves to the next word.
    ("Vale. Eh, no sé.", "Vale. No sé."),
    ("Um, yes. Um, no.", "Yes. No."),
    ("¿Vienes? Eh, no.", "¿Vienes? No."),
    ("Dijo: eh, no.", "Dijo: no."),
    ("Vale, eh", "Vale"),
    ("Mm, no lo sé.", "No lo sé."),
    ("Pues, em, mañana.", "Pues, mañana."),
])
def test_fillers_and_stutters(raw, expected):
    assert clean_rules(raw) == expected


@pytest.mark.parametrize("text", [
    # Repetitions that are content: numbers, codes, emphasis, legitimate doubles, names.
    "Llama al uno uno dos.", "Mi teléfono es seis seis seis doce doce doce.", "El código es 1 2 1 2.",
    "Marca 91 555 91 555.", "Código A A B B.", "El código es 4 4 2.",
    "No, no, eso no es así.", "No no no no.", "Es muy muy importante.", "No puedo, no puedo más.",
    "Para para el coche.", "I had had enough.", "He said that that was wrong.",
    "New York, New York.", "Duran Duran.",
    "Se lo di a él, él no lo quiso.", "Sobre todo, todo lo que dijo.", "Es así, así que vamos.",
    # What looks like a filler but is not: units, acronyms, names, deliberate interjections.
    "El tornillo mide 5 mm de largo.", "Mide cinco mm de largo.", "Pon el ancho en em y no en px.",
    "We went to the ER last night.", "Hablé con Em ayer.", "Voy al HM.", "La talla M o MM.",
    "He said uh huh.", "¿Eh?", 'Me dijo "eh" tres veces.',
    "Me he comprado un ukelele y un amplificador.", "Mándale el email a Emma.",
    # Capitalization, abbreviations and punctuation that were already right.
    "p. ej. una casa.", "etc. y demás", "EE. UU. es un país.", "No sé... quizá mañana.",
    "iPhone es caro. iPad también.", "- item uno",
    "tipo O- o tipo A", "La línea A- A2 es la buena.",
    "Gracias.", "Thank you.",
    "fin de frase\nfrase nueva frase",
])
def test_real_content_is_untouched(text):
    assert clean_rules(text) == text


@pytest.mark.parametrize("raw", [
    "", "   ", "Mmm.", "Eh, um...",
    "Subtítulos realizados por la comunidad de Amara.org",
    "¡Gracias por ver el vídeo!", "Thanks for watching!",
])
def test_nothing_worth_keeping(raw):
    assert clean_rules(raw) == ""


def test_short_typical_phrases_are_dropped_only_when_audio_was_doubtful():
    assert clean_rules("Gracias.") == "Gracias."
    assert clean_rules("Gracias.", doubtful=True) == ""
    assert clean_rules("Thank you.", doubtful=True) == ""
    assert clean_rules("Gracias por venir a la reunión.", doubtful=True) == "Gracias por venir a la reunión."


def test_without_key_only_rules_run():
    result = clean("Ehh, quedamos a las a las cinco en la oficina.", api_key="")
    assert result.engine == "rules"
    assert result.text == "Quedamos a las cinco en la oficina."


def test_fix_metrics_count_words_not_punctuation():
    result = clean("Ehh, quedamos a las a las cinco, mmm, en la oficina.", api_key="")
    assert (result.raw_words, result.fillers, result.fixes) == (11, 2, 4)  # ehh, mmm, "a las"
    assert count_fixes("hola mundo", "Hola, mundo.") == 0
    assert count_fixes("el martes no perdón el miércoles", "el miércoles") == 4
    assert count_fixes("a las diez", "a las 10") == 1
    assert clean("Voy al HM a por mm de tela.", api_key="").fillers == 0


def live(chunks):
    typed = ""
    for chunk in chunks:
        typed += clean_live_chunk(chunk, typed)
    return typed


@pytest.mark.parametrize("chunks, expected", [
    ([" eh, hola a todos", " y, mmm, luego seguimos."], "Hola a todos y, luego seguimos."),
    ([" Hola.", " Eh, no sé."], "Hola. No sé."),
    ([" Eh,", " pues vale."], "Pues vale."),
    ([" 5", " mm", " de largo"], "5 mm de largo"),       # the digit is in the previous chunk
    ([" ¿cómo", " estás?"], "¿Cómo estás?"),
    ([" Hola", ",", " mundo"], "Hola, mundo"),            # bare punctuation passes too
    ([" ehh mmm"], ""),
])
def test_live_chunks_join_cleanly(chunks, expected):
    assert live(chunks) == expected


def test_llm_answer_must_look_like_a_cleanup_of_the_dictation():
    said = "Quedamos el martes, no, perdona, el miércoles a las a las diez en la oficina"
    assert _plausible_cleanup(said, "Quedamos el miércoles a las diez en la oficina.")
    # An answer to the dictated question, a summary that swallows almost everything, a longer text.
    assert not _plausible_cleanup("¿Qué hora es en Tokio ahora mismo?", "No tengo acceso a la hora actual, lo siento.")
    assert not _plausible_cleanup(
        "bueno pues eh quería decirte que mañana no voy a poder ir a la reunión porque tengo médico y eso",
        "Quedamos mañana.")
    assert not _plausible_cleanup("Escribe un poema", "Escribe un poema sobre el mar azul que brilla bajo el sol de la mañana")


def test_llm_failures_never_lose_the_dictation(monkeypatch):
    import susurros.cleaner as cleaner

    def boom(*_args, **_kwargs):
        raise ValueError("response with an unexpected shape")

    monkeypatch.setattr(cleaner, "clean_llm", boom)
    result = clean("Ehh, quedamos a las cinco en la oficina.", api_key="key")
    assert (result.engine, result.text) == ("rules", "Quedamos a las cinco en la oficina.")

    monkeypatch.setattr(cleaner, "clean_llm", lambda *_a, **_k: None)   # answer discarded
    assert clean("Ehh, quedamos a las cinco en la oficina.", api_key="key").engine == "rules"
    monkeypatch.setattr(cleaner, "clean_llm", lambda text, *_a, **_k: "Quedamos a las cinco en la oficina.")
    assert clean("Ehh, quedamos a las cinco en la oficina.", api_key="key").engine == "claude"
