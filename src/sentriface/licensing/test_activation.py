from sentriface.licensing.activation import (
    verify_activation_key,
    save_activation_key,
    is_activated,
)


key = input("Paste activation key: ").strip()


print(
    "Valid:",
    verify_activation_key(key)
)


if verify_activation_key(key):

    save_activation_key(key)

    print("Saved")


print(
    "Activated:",
    is_activated()
)