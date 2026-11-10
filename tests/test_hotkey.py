from susurros.hotkey import KeyFilter, TapMachine, combo_name, normalize_combo, parse_keys


def make():
    events, timer = [], {"armed": False}
    machine = TapMachine(
        on_start=lambda: events.append("start"), on_stop=lambda: events.append("stop"),
        on_cancel=lambda: events.append("cancel"), on_lock=lambda: events.append("lock"),
        set_timer=lambda ms: timer.update(armed=True),
        cancel_timer=lambda: timer.update(armed=False))
    return machine, events, timer


def test_hold_and_release_transcribes():
    m, events, _ = make()
    m.down(0.0)
    m.up(1.5)
    assert events == ["start", "stop"] and m.state == "idle"


def test_single_tap_is_discarded():
    m, events, timer = make()
    m.down(0.0)
    m.up(0.1)
    assert timer["armed"] and m.state == "tap_wait"
    m.timeout()
    assert events == ["start", "cancel"] and m.state == "idle"


def test_double_tap_locks_until_next_double_tap():
    m, events, timer = make()
    m.down(0.0); m.up(0.08)
    m.down(0.2); m.up(0.28)
    assert events == ["start", "lock"] and m.state == "locked" and not timer["armed"]
    m.down(5.0); m.up(5.1)          # a stray tap does not finish
    assert m.state == "locked"
    m.down(9.0); m.up(9.08)
    m.down(9.2)                      # double tap: finishes
    assert events == ["start", "lock", "stop"] and m.state == "idle"
    m.up(9.3)                        # releasing afterwards restarts nothing
    assert events == ["start", "lock", "stop"]


def test_long_hold_inside_locked_mode_is_ignored():
    m, events, _ = make()
    m.down(0.0); m.up(0.08); m.down(0.2); m.up(0.28)
    m.down(3.0); m.up(6.0)
    assert m.state == "locked" and events == ["start", "lock"]


def test_escape_cancels_every_active_state():
    for steps in ([("down", 0.0)], [("down", 0.0), ("up", 0.1)],
                  [("down", 0.0), ("up", 0.1), ("down", 0.2)]):
        m, events, _ = make()
        for name, t in steps:
            getattr(m, name)(t)
        m.cancel()
        assert events[-1] == "cancel" and m.state == "idle"
    m, events, _ = make()
    m.cancel()
    assert events == []


def test_late_timeout_after_lock_does_nothing():
    m, events, _ = make()
    m.down(0.0); m.up(0.08); m.down(0.2)
    m.timeout()
    assert m.state == "locked" and events == ["start", "lock"]


def test_refused_start_leaves_the_machine_idle():
    # Model loading or microphone down: a double tap must not leave the key "stuck".
    events, ready = [], {"ok": False}

    def start():
        events.append("start" if ready["ok"] else "refused")
        return ready["ok"]

    m = TapMachine(on_start=start, on_stop=lambda: events.append("stop"),
                   on_cancel=lambda: events.append("cancel"), on_lock=lambda: events.append("lock"),
                   set_timer=lambda ms: None, cancel_timer=lambda: None)
    m.down(0.0); m.up(0.08); m.down(0.2); m.up(0.28)
    assert m.state == "idle" and events == ["refused", "refused"]
    ready["ok"] = True
    m.down(5.0); m.up(9.0)
    assert events[-2:] == ["start", "stop"] and m.state == "idle"


# --- KeyFilter: which keys make up the shortcut and which must be swallowed ----------------

LCTRL, RCTRL, LALT, LWIN, LSHIFT, ESC, CAPS, K1, KA = 0xA2, 0xA3, 0xA4, 0x5B, 0xA0, 0x1B, 0x14, 0x31, 0x41


class Keyboard:
    """Simulated keyboard: keeps track of which keys the system sees as down, like Windows."""

    def __init__(self, keys):
        self.events, self.held, self.masked = [], set(), 0
        self.filter = KeyFilter(
            pressed=lambda vk: vk in self.held, mask=self._mask,
            on_down=lambda: self.events.append("down"), on_up=lambda: self.events.append("up"),
            on_escape=lambda: self.events.append("esc"),
            on_captured=lambda keys: self.events.append(("captured", [k for k, _s, _e in keys])))
        self.filter.set_keys(keys)

    def _mask(self):
        self.masked += 1

    def press(self, vk):
        swallowed = self.filter.process(vk, 0, False, True, False)
        if not swallowed:
            self.held.add(vk)      # a swallowed key does not reach the system
        return swallowed

    def release(self, vk):
        swallowed = self.filter.process(vk, 0, False, False, True)
        self.held.discard(vk)
        return swallowed


def test_single_key_is_observed_but_never_swallowed():
    kb = Keyboard([CAPS])
    assert not kb.press(CAPS) and not kb.press(CAPS) and not kb.press(CAPS)   # auto-repeat
    assert not kb.release(CAPS)                     # Windows sees it all: Caps Lock still toggles
    assert kb.events == ["down", "up"]
    assert not kb.press(KA) and not kb.release(KA)  # the rest of the keyboard is untouched


def test_shift_plus_key_is_the_shortcut_too():
    kb = Keyboard([CAPS])
    kb.press(LSHIFT)
    assert not kb.press(CAPS) and not kb.release(CAPS)
    assert kb.events == ["down", "up"]


def test_modifier_plus_key_combo():
    kb = Keyboard([0x12, K1])                                       # Alt + 1
    assert not kb.press(K1) and not kb.release(K1) and kb.events == []   # "1" alone is not the shortcut
    assert not kb.press(LALT) and kb.events == []                   # neither is Alt alone
    assert not kb.press(K1)                                         # completes it; the app still gets Alt + 1
    assert kb.events == ["down"] and kb.masked == 1                 # and Alt will not open the menu bar
    assert not kb.press(K1) and kb.events == ["down"]               # auto-repeat
    assert not kb.release(K1) and kb.events == ["down", "up"]
    assert not kb.release(LALT) and kb.events == ["down", "up"]


def test_combo_double_tap_while_holding_the_modifier():
    kb = Keyboard([0x12, K1])
    kb.press(LALT)
    kb.press(K1); kb.release(K1); kb.press(K1); kb.release(K1)
    assert kb.events == ["down", "up", "down", "up"]


def test_modifier_only_combo_accepts_either_side():
    kb = Keyboard([0x11, 0x5B])                                     # Ctrl + Win
    assert not kb.press(RCTRL) and not kb.press(LWIN)
    assert kb.events == ["down"] and kb.masked == 1                 # without this, releasing would open Start
    assert not kb.release(LWIN) and kb.events == ["down", "up"]
    assert not kb.press(LWIN) and kb.events == ["down", "up", "down"]   # double tap of Win
    kb.release(LWIN); kb.release(RCTRL)
    kb.press(LWIN); kb.press(LCTRL)                                 # other order, other Ctrl
    assert kb.events[-1] == "down"


def test_extra_modifier_means_a_different_shortcut():
    kb = Keyboard([0x12, K1])
    kb.press(LCTRL); kb.press(LALT)
    assert not kb.press(K1) and kb.events == []                     # Ctrl + Alt + 1 is not Alt + 1


def test_capture_takes_everything_held_when_the_first_key_is_released():
    kb = Keyboard([CAPS])
    kb.filter.begin_capture()
    assert kb.press(LCTRL) and kb.press(LWIN)                       # nothing reaches the system during capture
    assert kb.release(LWIN)
    assert kb.events == [("captured", [LCTRL, LWIN])] and not kb.filter.capturing
    assert kb.release(LCTRL)                                        # the pending release is swallowed too
    kb.filter.begin_capture()
    kb.press(K1); kb.release(K1)
    assert kb.events[-1] == ("captured", [K1])


def test_pausing_and_escape():
    kb = Keyboard([CAPS])
    kb.filter.set_enabled(False)
    assert not kb.press(CAPS) and not kb.release(CAPS) and kb.events == []
    kb.filter.set_enabled(True)
    kb.filter.capture_escape = True
    assert kb.press(ESC) and kb.press(ESC)                          # swallowed until released
    kb.filter.capture_escape = False
    assert kb.press(ESC) and kb.release(ESC)
    assert kb.events == ["esc"] and not kb.press(ESC)               # outside a dictation Esc is Esc


def test_combo_normalisation_and_names():
    assert normalize_combo([(0xA3, 0x1D, True)]) == ([0xA3], "Right Ctrl")           # a single key: as is
    assert normalize_combo([(K1, 0x02, False), (LALT, 0x38, False)]) == ([0x12, K1], "Alt + 1")
    assert normalize_combo([(LWIN, 0x5B, True), (RCTRL, 0x1D, True)]) == ([0x11, 0x5B], "Ctrl + Win")
    assert normalize_combo([(LCTRL, 0, False), (LSHIFT, 0, False), (0x77, 0, False)]) == (
        [0x11, 0x10, 0x77], "Ctrl + Shift + F8")
    assert normalize_combo([(LCTRL, 0, False), (RCTRL, 0, True)]) == ([0x11], "Ctrl")
    assert parse_keys("18,49") == [18, 49] and parse_keys("") == [CAPS] and parse_keys("x") == [CAPS]


def test_shortcut_name_follows_the_interface_language():
    spanish = {"Caps Lock": "Bloq Mayús", "Shift": "Mayús", "Win": "Windows"}.get
    es = lambda name: spanish(name, name)
    assert combo_name([0x14]) == "Caps Lock" and combo_name([0x14], es) == "Bloq Mayús"
    assert combo_name([0x11, 0x10, 0x77], es) == "Ctrl + Mayús + F8"
    assert combo_name([0x12, 0x31], es) == "Alt + 1"
    assert combo_name([0xDC], es, fallback="º") == "º"       # only the keyboard layout can name it
