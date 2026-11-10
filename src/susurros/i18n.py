"""Interface language. English is the source text in the code; Spanish lives in `ES`.

Use `tr("Text")` (or `tr("Hold {key} to dictate.", key=name)`) for every string a user can see.
Nothing here touches the dictation language, which is a separate setting.
"""
from __future__ import annotations

from datetime import date, timedelta

_language = "en"

_MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
           "septiembre", "octubre", "noviembre", "diciembre"],
}

# English source text -> Spanish. Keep entries grouped by where they appear.
ES: dict[str, str] = {
    # key names (hotkey.py)
    "Caps Lock": "Bloq Mayús", "Num Lock": "Bloq Num", "Scroll Lock": "Bloq Despl", "Pause": "Pausa",
    "Print Screen": "Impr Pant", "Menu": "Menú", "Space": "Espacio", "Shift": "Mayús", "Win": "Windows",
    "Left Ctrl": "Ctrl izquierdo", "Right Ctrl": "Ctrl derecho", "Left Alt": "Alt izquierdo",
    "Right Alt": "Alt derecho", "Left Shift": "Mayús izquierda", "Right Shift": "Mayús derecha",
    "Right Win": "Windows derecha",
    # macOS key names
    "Control": "Control", "Left Control": "Control izquierdo", "Right Control": "Control derecho",
    "Option": "Opción", "Left Option": "Opción izquierda", "Right Option": "Opción derecha",
    "Command": "Comando", "Right Command": "Comando derecho",
    "Same as macOS": "El de macOS",
    # option lists (config.py, sounds.py)
    "Bottom": "Abajo", "Top": "Arriba", "Left": "Izquierda", "Right": "Derecha",
    "Spanish": "Español", "English": "Inglés", "Detect automatically": "Detectar automáticamente",
    "Same as Windows": "El de Windows",
    "Bubble": "Burbuja", "Chord": "Acorde", "Two notes": "Dos notas", "Knock": "Toc",
    # cleanup notices (cleaner.py)
    "The Anthropic API key is not valid": "La clave de Anthropic no es válida",
    "The Anthropic API key has no access to the model": "La clave de Anthropic no tiene acceso al modelo",
    "Anthropic usage limit reached": "Límite de uso de Anthropic alcanzado",
    "Claude rejected the request; using the local rules": "Claude ha rechazado la petición; se usan las reglas",
    # tray menu and startup notice (app.py)
    "Open Susurros": "Abrir Susurros", "Pause dictation": "Pausar el dictado", "Quit": "Salir",
    "The history was damaged and a new one has been started. The previous file is kept as {file}.":
        "El historial estaba dañado y se ha empezado uno nuevo. El fichero anterior se conserva como {file}.",
    # status line in the sidebar (app.py)
    "Paused. {key} does not start a dictation.": "En pausa. {key} no inicia el dictado.",
    "Couldn't load the speech model: {error}": "No se pudo cargar el modelo de voz: {error}",
    "Loading the speech model…": "Cargando el modelo de voz…",
    "Couldn't capture the dictation key.": "No se ha podido capturar la tecla de dictado.",
    "Allow Susurros in System Settings › Privacy & Security › Accessibility.":
        "Permite Susurros en Ajustes del Sistema › Privacidad y seguridad › Accesibilidad.",
    "Allow Susurros in System Settings › Privacy & Security › Input Monitoring.":
        "Permite Susurros en Ajustes del Sistema › Privacidad y seguridad › Monitorización de entrada.",
    "A single key or a combination, such as Option + 1 or Control + Command. The key keeps doing its normal job too.":
        "Una tecla o una combinación, como Opción + 1 o Control + Comando. "
        "La tecla sigue haciendo también su función normal.",
    "A key is saved in the macOS Keychain.": "Hay una clave guardada en el Llavero de macOS.",
    "Open at login": "Abrir al iniciar sesión",
    "Starts hidden in the menu bar.": "Arranca oculto en la barra de menús.",
    "Ready to dictate · {device}": "Listo para dictar · {device}",
    "Microphone unavailable: {error}": "Micrófono no disponible: {error}",
    # indicator: caption and hover buttons (app.py, pill.py)
    "Couldn't load the speech model": "No se pudo cargar el modelo de voz",
    "The speech model is still loading": "El modelo de voz aún se está cargando",
    "Can't access the microphone": "No se puede acceder al micrófono",
    "Dictation cancelled": "Dictado cancelado",
    "Nothing heard": "No se ha oído nada",
    "Couldn't transcribe": "No se ha podido transcribir",
    "Couldn't save the dictation to the history": "El dictado no se ha podido guardar en el historial",
    "Hands-free · double {key} to finish": "Manos libres · doble {key} para terminar",
    "Expand": "Desplegar", "Collapse against the edge": "Replegar contra el borde",
    "Hide the indicator": "Ocultar el indicador",
    # sidebar and theme switcher (main_window.py)
    "History": "Historial", "Dictionary": "Diccionario", "Settings": "Ajustes",
    "Light theme": "Tema claro", "Dark theme": "Tema oscuro", "Same as system": "Igual que el sistema",
    # history page
    "Hold {key} to dictate. Press it twice in a row to dictate hands-free.":
        "Mantén pulsado {key} para dictar. Púlsalo dos veces seguidas para dictar con las manos libres.",
    "Search your dictations": "Buscar en tus dictados",
    "Clear history": "Vaciar historial",
    'No dictation contains "{query}".': "Ningún dictado contiene «{query}».",
    "No dictations yet. Hold {key}, speak and release: the text appears where your cursor is and is saved here.":
        "Aún no hay dictados. Mantén pulsado {key}, habla y suelta: "
        "el texto aparecerá donde tengas el cursor y quedará guardado aquí.",
    "Showing the {n} most recent. Use search to find older ones.":
        "Se muestran los {n} más recientes. Usa el buscador para llegar a los anteriores.",
    "Showing the {n} most recent matches.": "Se muestran las {n} coincidencias más recientes.",
    "{n} words": "{n} palabras", "1 word": "1 palabra",
    "polished with Claude": "pulido con Claude", "typed while speaking": "sobre la marcha",
    "Click to copy": "Clic para copiar", "Copied": "Copiado", "Delete": "Borrar",
    "Delete all saved dictations?": "¿Borrar todos los dictados guardados?",
    "This can't be undone.": "No se puede deshacer.",
    "Delete all": "Borrar todo", "Cancel": "Cancelar",
    # insights page
    "How much you dictate, how fast, and how much cleanup changes.":
        "Cuánto dictas, a qué ritmo y cuánto retoca la limpieza.",
    "PACE AND VOLUME": "RITMO Y VOLUMEN",
    "words per minute": "palabras por minuto", "words dictated in total": "palabras dictadas en total",
    "dictations": "dictados", "saved compared with typing": "ahorrados frente a teclear",
    "CLEANUP": "LIMPIEZA",
    "edits per dictation": "retoques por dictado", "words edited": "palabras retocadas",
    "filler words removed": "muletillas quitadas", "of what you say gets edited": "de lo que dices se retoca",
    "{value}%": "{value} %",
    "An edit is a word that cleanup removed or changed from what was transcribed: filler words (uh, um), "
    "repetitions and self-corrections. Changes to punctuation and capitalization don't count.":
        "Un retoque es una palabra que la limpieza ha quitado o cambiado respecto a lo que "
        "se transcribió: muletillas (eh, mmm), repeticiones y autocorrecciones. "
        "Los cambios de puntuación y de mayúsculas no cuentan.",
    "Cleanup figures come from {measured} of your {count} dictations: earlier ones didn't record edits.":
        "Los datos de limpieza salen de {measured} de tus {count} dictados: "
        "los anteriores no registraron retoques.",
    # dictionary page
    "Names, acronyms and technical terms you want spelled the same way every time.":
        "Nombres propios, siglas y términos técnicos que quieres que se escriban siempre igual.",
    "For example: PySide, kubectl, Zaragoza": "Por ejemplo: PySide, kubectl, Zaragoza",
    "Add": "Añadir", "Remove": "Quitar",
    "The dictionary is empty. Add the words dictation tends to get wrong.":
        "El diccionario está vacío. Añade las palabras que el dictado suele escribir mal.",
    # settings page: dictation
    "Changes are saved right away.": "Los cambios se guardan al momento.",
    "DICTATION": "DICTADO",
    "Dictation shortcut": "Atajo de dictado",
    "A single key or a combination, such as Alt + 1 or Ctrl + Win. The key keeps doing its normal job too.":
        "Una tecla o una combinación, como Alt + 1 o Ctrl + Windows. "
        "La tecla sigue haciendo también su función normal.",
    "Press the shortcut…": "Pulsa el atajo…",
    "Microphone": "Micrófono", "System default": "Predeterminado del sistema",
    "Dictation language": "Idioma del dictado",
    "Setting the language avoids mistakes in very short dictations.":
        "Fijar el idioma evita errores en dictados muy cortos.",
    "Type where the cursor is": "Escribir donde esté el cursor",
    "If you turn this off, dictations are only saved to the history.":
        "Si lo desactivas, el dictado solo se guarda en el historial.",
    "Type as I speak": "Escribir sobre la marcha",
    "Text appears while you speak, a second or two behind. In exchange, only filler words are removed: "
    "no polishing with Claude and no self-corrections applied.":
        "El texto aparece mientras hablas, con uno o dos segundos de retraso. A cambio "
        "solo se quitan las muletillas: no se pule con Claude ni se aplican rectificaciones.",
    "Add a trailing space": "Añadir un espacio al final",
    "So consecutive dictations don't run together.": "Para encadenar dictados sin que se peguen las frases.",
    "Sounds": "Sonidos", "A short cue when dictation starts and ends.": "Un aviso breve al empezar y al terminar.",
    "Sound style": "Tipo de sonido",
    "Choosing one plays its start and end sounds.": "Al elegir uno suena cómo empieza y cómo termina.",
    # settings page: on-screen indicator
    "ON-SCREEN INDICATOR": "INDICADOR EN PANTALLA",
    "Always show it": "Mostrarlo siempre",
    "If you turn this off, it only appears while you dictate. Its × button also closes it.":
        "Si lo desactivas, solo aparece mientras dictas. También se cierra con su botón ×.",
    "Position": "Posición",
    "You can also drag the indicator with the mouse and drop it in one of the four slots.":
        "También puedes arrastrar el indicador con el ratón y soltarlo en uno de los cuatro huecos.",
    # settings page: text cleanup
    "TEXT CLEANUP": "LIMPIEZA DEL TEXTO",
    "Polish with Claude": "Pulir con Claude",
    "Removes rambling and self-corrections and improves punctuation. Only the text is sent, never the audio. "
    "Without a key, the local rules are used.":
        "Quita rodeos y autocorrecciones y mejora la puntuación. Solo se envía el texto, "
        "nunca el audio. Sin clave se usan las reglas locales.",
    "Anthropic API key": "Clave de API de Anthropic", "Save": "Guardar",
    "A key is saved in Windows Credential Manager.":
        "Hay una clave guardada en el Administrador de credenciales de Windows.",
    "No key. Create one at console.anthropic.com and paste it here.":
        "Sin clave. Créala en console.anthropic.com y pégala aquí.",
    "Couldn't save the key: {error}": "No se ha podido guardar la clave: {error}",
    # settings page: privacy and system
    "PRIVACY AND SYSTEM": "PRIVACIDAD Y SISTEMA",
    "Interface language": "Idioma de la interfaz",
    "Also keep the original transcription": "Guardar también la transcripción original",
    "By default only the cleaned text is saved.": "Por defecto solo se guarda el texto limpio.",
    "Open when Windows starts": "Abrir al iniciar Windows",
    "Starts hidden in the system tray.": "Arranca oculto en la bandeja del sistema.",
    "Esc cancels a dictation in progress.": "Esc cancela un dictado en curso.",
}


def resolve(setting: str) -> str:
    """"es" or "en" for a stored preference; an empty one follows the Windows display language."""
    if setting in ("es", "en"):
        return setting
    from PySide6.QtCore import QLocale
    return "es" if QLocale.system().language() == QLocale.Language.Spanish else "en"


def set_language(code: str) -> None:
    global _language
    _language = "es" if code == "es" else "en"


def language() -> str:
    return _language


def tr(text: str, **values) -> str:
    """Translate an English source string, then fill its {placeholders}."""
    if _language == "es":
        text = ES.get(text, text)
    return text.format(**values) if values else text


def fmt_int(number: int) -> str:
    """Thousands separator of the interface language: 12.345 in Spanish, 12,345 in English."""
    grouped = f"{number:,}"
    return grouped.replace(",", ".") if _language == "es" else grouped


def fmt_decimal(value: float) -> str:
    text = f"{value:.1f}"
    return text.replace(".", ",") if _language == "es" else text


def day_label(day: date, today: date | None = None) -> str:
    """Section heading for a day in the history: TODAY, YESTERDAY, or the date."""
    today = today or date.today()
    if day == today:
        return tr("TODAY")
    if day == today - timedelta(days=1):
        return tr("YESTERDAY")
    month = _MONTHS[_language][day.month - 1].upper()
    if _language == "es":
        text = f"{day.day} DE {month}"
        return text if day.year == today.year else f"{text} DE {day.year}"
    text = f"{month} {day.day}"
    return text if day.year == today.year else f"{text}, {day.year}"


ES.update({"TODAY": "HOY", "YESTERDAY": "AYER"})
