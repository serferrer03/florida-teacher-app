import os

import pytest

from .fake_moodle import FakeMoodle, serve

# Chromium del sistema si Playwright no trae el suyo (CI / contenedores)
os.environ.setdefault("MOODLE_TIMEOUT_MS", "10000")
os.environ.setdefault("KEY_STORAGE", "file")  # las pruebas no tocan el llavero del sistema


@pytest.fixture(scope="session")
def fake():
    fake = FakeMoodle()
    url, server = serve(fake)
    fake.url = url
    yield fake
    server.should_exit = True
