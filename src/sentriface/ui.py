from __future__ import annotations

import sys

from sentriface.licensing.activation import is_activated
from sentriface.licensing.activation_helper import run_activation_helper


def run() -> int:
    helper_result = run_activation_helper(sys.argv[1:])
    if helper_result is not None:
        return helper_result

    if not is_activated():
        from sentriface.licensing.activation_ui import run_activation_ui

        if not run_activation_ui():
            return 1

    from sentriface.api_server import main

    return main()


if __name__ == "__main__":
    raise SystemExit(run())
