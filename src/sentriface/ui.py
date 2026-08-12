from __future__ import annotations

from sentriface.licensing.activation import is_activated
from sentriface.licensing.activate import activate
from sentriface.api_server import main


def run():

    if not is_activated():
        print("SentriFace Edge is not activated.")
        if not activate():
            return 1

    return main()


if __name__ == "__main__":
    raise SystemExit(run())