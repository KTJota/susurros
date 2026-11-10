import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # UI tests open no windows


@pytest.fixture
def controller(tmp_path, monkeypatch):
    """Full controller without a real Whisper, microphone or keyboard.
    The interface is in Spanish (stored as the user's choice), so assertions on UI text are Spanish."""
    import numpy as np
    from PySide6.QtWidgets import QApplication

    import susurros.app as appmod
    from susurros import i18n
    from susurros.db import Store

    monkeypatch.setenv("SUSURROS_DATA_DIR", str(tmp_path))
    seed = Store()
    seed.set("ui_language", "es")   # otherwise it would follow the language of the machine running the tests
    seed.close()
    monkeypatch.setattr(appmod.Worker, "start", lambda self: None)
    monkeypatch.setattr(appmod.Worker, "stop", lambda self: None)
    monkeypatch.setattr(appmod, "has_input", lambda: True)
    typed, pasted = [], []
    monkeypatch.setattr(appmod.injector, "type_text", typed.append)
    monkeypatch.setattr(appmod.injector, "paste", pasted.append)

    app = QApplication.instance() or QApplication([])
    ctl = appmod.Controller(app, start_hidden=True)
    ctl.typed, ctl.pasted, ctl.jobs = typed, pasted, []
    ctl.worker.submit = ctl.jobs.append

    class FakeRecorder:
        recording = False
        fail = False
        audio = (np.random.default_rng(1).standard_normal(32_000) * 0.2).astype(np.float32)   # 2 s

        def start(self, _device=""):
            if self.fail:
                raise OSError("no microphone")
            self.recording = True

        def stop(self):
            self.recording = False
            return self.audio

        def snapshot(self):
            return self.audio

    ctl.recorder = FakeRecorder()
    yield ctl
    ctl.pill._really_hide()
    ctl.store.close()
    i18n.set_language("en")   # the module default, for the tests that do not use this fixture
