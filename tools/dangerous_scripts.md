
1. cleanup_sentriface_test_creds.ps1
- delete stale db encryption keys used by test scripts
- to be run after tests success, and before installing sentrifaceEdge on system


2. wipe_clean_this_machine_installation_and_data.py
- run only on test machines, destructive


3. cleanup_sentriface_all_creds
- delete db encryption keys (test, & prod included)

Combination of 2, and 3 clean wipes the machine of sentriface entirely.