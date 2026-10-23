# Native CI cost controls

This repository is public. Use only standard GitHub-hosted runners, including
`macos-15-intel`, so native minutes remain free. Artifact storage still has plan
limits: keep new diagnostics briefly and batch native validation around the
current milestone.

- Work on a non-main branch and batch related fixes before updating main.
- Complete local syntax, exact source-hash, symbol-contract and relevant CLI checks before starting native CI. Review all available failure logs and downloaded objects together.
- Keep only one native workflow running at a time. Inspect active runs first and confirm obsolete runs are cancelled before starting another paid build.
- The closed idle-loader ABI checkpoint has passed. Rebuild it only when a relevant regression or new deliverable requires it; do not repeat the completed target test as routine coverage. The extended development workflow is manual and should run only when its additional checks are needed.
- Native validation is explicit: use `workflow_dispatch`, or add/update `.github/native-ci/nvidia-idle-request.json` on main in one small final request commit whose message contains `[native ci]`. Use a new batch identifier in that JSON. The file requests execution; it does not replace source, cache or target evidence. Never delete/revert it casually, and do not use `[skip ci]` on an actual request commit.
- The separate retained first-initialization package uses `build-nvidia-retained-first-init.yml` and `.github/native-ci/nvidia-retained-first-init-request.json`. Its final request commit changes only that request file, names its exact source-parent commit and uses `[native ci]`. Both jobs independently require an explicit request and a public repository; this does not reopen or repeat the completed idle test.
- The idle workflow filters push events to that request file and independently gates both jobs on the request marker. Unrequested workflow events use separate concurrency groups so they cannot cancel running or pending requested validation. Keep these guards together; path filters alone can fail open for very large pushes or GitHub diff timeouts.
- Complete local preparation and checks for the unified prerequisites plus first RM/GSP/GPU initialization milestone before one grouped native validation and one integrated target-test package. Reuse authenticated artifacts and rebuild only genuinely changed units when the exact compiler, SDK, command and full dependency bindings permit it. Preserve all existing refusal and final verification checks.
- Use `[skip ci]` for intermediate or documentation-only main commits. Workflow-only cost controls must also avoid triggering another native build.
- Do not retry unchanged sources unless evidence shows the infrastructure problem has been resolved.
- Preserve exact callback/export checks. Admit a compiler memory helper only for the reviewed source and actual compiler evidence; never weaken private symbol closure globally.
- Report native compilation, successful packaging, target kernel loading and GPU initialization as separate milestones.
