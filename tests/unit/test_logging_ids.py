import io
import json

import structlog

from reelforge.ids import is_ulid, new_id
from reelforge.logging import configure_logging


def test_new_id_is_ulid():
    value = new_id()
    assert len(value) == 26 and is_ulid(value)
    assert not is_ulid("nope")


def test_logging_writes_json_lines():
    buf = io.StringIO()
    configure_logging(stream=buf)
    structlog.get_logger().info("evt.name", a=1)
    obj = json.loads(buf.getvalue().splitlines()[0])
    assert obj["event"] == "evt.name" and obj["a"] == 1
    assert obj["level"] == "info" and obj["ts"].endswith("Z")


def test_logging_file_handler(tmp_path):
    buf = io.StringIO()
    log = tmp_path / "logs" / "app.log"
    configure_logging(stream=buf, log_file=log)
    structlog.get_logger().warning("to.file")
    assert "to.file" in log.read_text()
