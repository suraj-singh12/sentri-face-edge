from sentriface.licensing.activation import save_activation_key
from sentriface.licensing.fingerprint import generate_machine_id


def activate():

    print()
    print("==============================")
    print(" SentriFace Edge Activation")
    print("==============================")
    print()

    machine_id = generate_machine_id()

    print("Machine ID:")
    print(machine_id)

    print()

    key = input("Activation Key: ").strip()

    try:
        save_activation_key(key)

        print()
        print("Activation successful.")

        return True

    except Exception:

        print()
        print("Invalid activation key.")

        return False