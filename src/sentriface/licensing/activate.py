from sentriface.licensing.activation import save_activation_key
from sentriface.licensing.fingerprint import generate_machine_id


def activate():

    print()
    print("SentriFace Edge Activation")
    print()

    print("Machine ID:")
    print(generate_machine_id())

    print()

    key = input("Activation Key: ")

    try:

        save_activation_key(key)

        print(
            "Activation successful."
        )

        return True

    except Exception:

        print(
            "Invalid key."
        )

        return False