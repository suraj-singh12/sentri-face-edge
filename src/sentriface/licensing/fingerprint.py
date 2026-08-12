import hashlib
import platform
import subprocess
import winreg
import base64


SALT = "SentriFaceEdge-v1"


def get_machine_guid():
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)

    except Exception:
        return ""


def get_bios_uuid():
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystemProduct).UUID"
            ],
            text=True,
            timeout=5
        )

        return result.strip()

    except Exception:
        return ""


def get_baseboard_serial():
    try:
        result = subprocess.check_output(
            [
                "powershell",
                "-Command",
                "(Get-CimInstance Win32_BaseBoard).SerialNumber"
            ],
            text=True,
            timeout=5
        )

        return result.strip()

    except Exception:
        return ""


def collect_hardware_data():

    return {
        "machine_guid": get_machine_guid(),
        "bios_uuid": get_bios_uuid(),
        "baseboard": get_baseboard_serial(),
        "system": platform.system(),
        "machine": platform.machine(),
    }


def generate_machine_id():

    data = collect_hardware_data()

    raw = "|".join(
        [
            data["machine_guid"],
            data["bios_uuid"],
            data["baseboard"],
            data["system"],
            data["machine"],
        ]
    )

    digest = hashlib.sha256(
        (SALT + raw).encode()
    ).digest()


    short_id = base64.b32encode(
        digest[:15]
    ).decode().rstrip("=")


    groups = [
        short_id[i:i+5]
        for i in range(0, len(short_id), 5)
    ]


    return "SFE-MC-" + "-".join(groups)


if __name__ == "__main__":
    print(generate_machine_id())