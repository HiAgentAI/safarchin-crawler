# Project Rules & Memory for AI Agents

## Shell Command Execution
- Always use `rtk` (Rust Token Killer) to execute shell commands (e.g. `rtk git ...`, `rtk docker ...`, `rtk pytest ...`, `rtk ls ...`, `rtk run "..."`).
- Prefixing shell commands with `rtk` filters and compresses output, reducing token consumption.
