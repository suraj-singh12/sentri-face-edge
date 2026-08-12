import base64
import json
import winreg

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .public_key import PUBLIC_KEY_B64
from .fingerprint import generate_machine_id


REG_PATH = r"Software\SentriFaceEdge"
REG_VALUE = "ActivationKey"


def decode_base64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def verify_activation_key(key: str) -> bool:
    try:
        parts = key.strip().split(".")

        if len(parts) != 3:
            return False


        prefix, payload_encoded, signature_encoded = parts


        if prefix != "SFE1":
            return False


        payload = decode_base64(payload_encoded)

        signature = decode_base64(signature_encoded)


        public_key_bytes = decode_base64(
            PUBLIC_KEY_B64
        )


        public_key = Ed25519PublicKey.from_public_bytes(
            public_key_bytes
        )


        public_key.verify(
            signature,
            payload
        )


        data = json.loads(
            payload.decode()
        )


        if data.get("product") != "SentriFaceEdge":
            return False


        licensed_machine = data.get("machine")


        current_machine = generate_machine_id()


        if licensed_machine != current_machine:
            return False


        return True


    except InvalidSignature:
        return False

    except Exception:
        return False



def save_activation_key(key: str):

    if not verify_activation_key(key):
        raise ValueError(
            "Invalid activation key"
        )


    with winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        REG_PATH
    ) as registry:

        winreg.SetValueEx(
            registry,
            REG_VALUE,
            0,
            winreg.REG_SZ,
            key.strip()
        )



def load_activation_key():

    try:

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_PATH
        ) as registry:

            value, _ = winreg.QueryValueEx(
                registry,
                REG_VALUE
            )

            return value


    except FileNotFoundError:
        return None



def is_activated() -> bool:

    key = load_activation_key()

    if not key:
        return False


    return verify_activation_key(key)