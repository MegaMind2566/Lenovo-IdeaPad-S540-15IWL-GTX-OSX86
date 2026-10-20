# Paid native CI

GitHub Actions macOS minutes are paid. Keep native validation focused on the current milestone.

- Work on a non-main branch and batch related fixes before updating main.
- Complete local syntax, exact source-hash, symbol-contract and relevant CLI checks before starting native CI. Review all available failure logs and downloaded objects together.
- Keep only one native workflow running at a time. Inspect active runs first and confirm obsolete runs are cancelled before starting another paid build.
- The idle package workflow is the default native build for the closed loader ABI milestone. The extended development workflow is manual and should run only when its additional checks are needed.
- Use `[skip ci]` for intermediate or documentation-only main commits. Workflow-only cost controls must also avoid triggering another native build.
- Do not retry unchanged sources unless evidence shows the infrastructure problem has been resolved.
- Preserve exact callback/export checks. Admit a compiler memory helper only for the reviewed source and actual compiler evidence; never weaken private symbol closure globally.
- Report native compilation, successful packaging, target kernel loading and GPU initialization as separate milestones.
