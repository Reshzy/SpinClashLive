"""Generate YouTube streamList gRPC stubs from the vendored proto."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTO = ROOT / "backend" / "third_party" / "youtube" / "stream_list.proto"
OUT = ROOT / "backend" / "src" / "color_rush" / "infrastructure" / "youtube" / "generated"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{PROTO.parent}",
        f"--python_out={OUT}",
        f"--grpc_python_out={OUT}",
        str(PROTO),
    ]
    subprocess.check_call(command)
    pb2 = OUT / "stream_list_pb2_grpc.py"
    if pb2.exists():
        text = pb2.read_text(encoding="utf-8")
        pb2.write_text(text.replace("import stream_list_pb2", "from . import stream_list_pb2"), encoding="utf-8")
    print(f"generated stubs in {OUT}")


if __name__ == "__main__":
    main()
