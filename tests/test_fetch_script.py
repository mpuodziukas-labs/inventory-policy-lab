"""fetch_data downloads the pinned archive and refuses anything whose SHA-256 differs. No network is used."""
import hashlib
import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "fetch_data.py"
PINNED_URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
PINNED_SHA256 = "f5385cbb54bbebf7196389109c6b0621faab0c304e3702548165e71c84aede8b"
BLOB = b"PK\x03\x04 pretend archive bytes \x00\xff"


def load():
    spec = importlib.util.spec_from_file_location("fetch_data_script", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class FakeResponse:
    def __init__(self, blob):
        self.blob = blob

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self.blob


@pytest.fixture
def fetch(monkeypatch, tmp_path):
    """Load the script with a fake download; returns (module, requested urls)."""
    m = load()
    urls = []

    def fake_urlopen(url, timeout=None):
        urls.append(url)
        return FakeResponse(BLOB)

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)
    return m, urls


def test_pinned_digest_equals_the_one_in_the_data_provenance_doc():
    m = load()
    source = (ROOT / "data" / "SOURCE.md").read_text()
    assert re.search(r"SHA-256 against `([0-9a-f]{64})`", source).group(1) == m.SHA256
    assert m.SHA256 == PINNED_SHA256


def test_a_matching_download_is_written_whole_and_reported_with_its_digest(fetch, tmp_path, capsys):
    m, _ = fetch
    m.SHA256 = hashlib.sha256(BLOB).hexdigest()
    out = tmp_path / "dl"
    m.main(["fetch_data.py", str(out)])
    assert (out / "online_retail.zip").read_bytes() == BLOB
    assert capsys.readouterr().out == f"ok {out / 'online_retail.zip'} {m.SHA256}\n"


def test_a_missing_nested_out_dir_is_created(fetch, tmp_path):
    m, _ = fetch
    m.SHA256 = hashlib.sha256(BLOB).hexdigest()
    out = tmp_path / "a" / "b" / "c"
    m.main(["fetch_data.py", str(out)])
    assert (out / "online_retail.zip").read_bytes() == BLOB


def test_the_out_dir_argument_is_honoured_not_the_default(fetch, tmp_path):
    m, _ = fetch
    m.SHA256 = hashlib.sha256(BLOB).hexdigest()
    m.main(["fetch_data.py", str(tmp_path / "chosen")])
    assert (tmp_path / "chosen" / "online_retail.zip").exists()
    assert not (tmp_path / ".tmp").exists()


def test_the_pinned_url_is_the_one_requested(fetch, tmp_path):
    m, urls = fetch
    m.SHA256 = hashlib.sha256(BLOB).hexdigest()
    m.main(["fetch_data.py", str(tmp_path / "dl")])
    assert urls == [PINNED_URL]
    assert m.URL == PINNED_URL
    assert PINNED_URL in (ROOT / "data" / "SOURCE.md").read_text()


def test_a_non_matching_download_exits_non_zero_and_writes_nothing(fetch, tmp_path):
    m, _ = fetch
    out = tmp_path / "dl"
    with pytest.raises(SystemExit) as exc:
        m.main(["fetch_data.py", str(out)])
    assert exc.value.code not in (0, None)
    assert "sha256 mismatch" in str(exc.value.code)
    assert hashlib.sha256(BLOB).hexdigest() in str(exc.value.code)
    assert not (out / "online_retail.zip").exists()


def test_without_an_argument_the_archive_goes_to_the_hidden_default_dir(fetch, tmp_path):
    m, _ = fetch
    m.SHA256 = hashlib.sha256(BLOB).hexdigest()
    m.main(["fetch_data.py"])
    assert (tmp_path / ".tmp" / "online_retail.zip").read_bytes() == BLOB


def test_the_out_dir_is_the_first_argument_not_the_last(fetch, tmp_path):
    m, _ = fetch
    m.SHA256 = hashlib.sha256(BLOB).hexdigest()
    m.main(["fetch_data.py", str(tmp_path / "first"), str(tmp_path / "last")])
    assert (tmp_path / "first" / "online_retail.zip").read_bytes() == BLOB
    assert not (tmp_path / "last").exists()
