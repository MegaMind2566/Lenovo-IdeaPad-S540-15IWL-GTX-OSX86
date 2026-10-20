#!/bin/sh
# SPDX-License-Identifier: MIT. Read-only observation; no load or unload.
set -eu
. "$(dirname "$0")/common.sh"
init "$@"
new_report
collect_system
target=false; snapshot=false; loaded=false
if "$PKG/s540-idle-image-ctl" --target >"$SESSION/target.json" 2>"$SESSION/target.stderr"; then target=true; fi
if "$PKG/s540-idle-image-ctl" --snapshot >"$SESSION/snapshot.json" 2>"$SESSION/snapshot.stderr"; then snapshot=true; fi
if has_expected_uuid "$SESSION/loaded.txt"; then loaded=true; fi
cat >"$SESSION/report.json" <<EOF
{"format":1,"scope":"readonly-idle-complete-image-observation","target_identity_matches":$target,"loaded_identifier_uuid_matches":$loaded,"closed_idle_snapshot_valid":$snapshot,"target_loader_abi_observed":false,"hardware_admission":false,"original_entry_admission":false,"rm_initialization_test":false,"gsp_initialization_test":false,"acceleration_test":false,"attestation_sha256":"$PIN"}
EOF
printf 'Read-only idle complete-image report: %s\n' "$SESSION"
