from __future__ import annotations

from pathlib import Path

from sentriface.licensing.activation import is_activated, save_activation_key
from sentriface.licensing.fingerprint import generate_machine_id


def run_activation_helper(arguments: list[str]) -> int | None:
    """Handle installer-only activation commands without starting SentriFace."""

    if not arguments or arguments[0] != "--activation-helper":
        return None
    if len(arguments) < 2:
        return 2
    action = arguments[1]
    if action == "status" and len(arguments) == 3:
        machine_id = generate_machine_id()
        _write_result(
            Path(arguments[2]),
            is_activated(machine_id=machine_id),
            machine_id,
            "",
        )
        return 0
    if action == "activate" and len(arguments) == 4:
        key_path = Path(arguments[2])
        result_path = Path(arguments[3])
        try:
            machine_id = generate_machine_id()
            save_activation_key(
                key_path.read_text(encoding="utf-8").strip(),
                machine_id=machine_id,
            )
            _write_result(result_path, True, machine_id, "SentriFace is activated.")
            return 0
        except (OSError, UnicodeError, ValueError):
            machine_id = locals().get("machine_id") or generate_machine_id()
            _write_result(
                result_path,
                False,
                machine_id,
                "The activation key is invalid for this machine.",
            )
            return 1
        finally:
            key_path.unlink(missing_ok=True)
    return 2


def _write_result(path: Path, activated: bool, machine_id: str, message: str) -> None:
    clean_message = " ".join(message.splitlines())
    content = "\n".join(("1" if activated else "0", machine_id, clean_message)) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)
