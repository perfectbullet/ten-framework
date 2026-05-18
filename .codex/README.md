# Codex Harness

This directory contains lightweight project harness files for Codex-style agents working in this repository.

## Files

- `project-map.json`: machine-readable project map and task routing hints
- `workflows/debug-voice-assistant.md`: runbook for issues in the default voice assistant example
- `workflows/edit-extension.md`: runbook for modifying Python TEN extensions safely
- `handoff-template.md`: compact template for pausing and resuming longer tasks

## Usage

Start with `../AGENTS.md` for the high-level repository guide, then use:

- `project-map.json` when a tool or agent needs structured routing hints
- `workflows/*.md` when the task already fits a common pattern
- `handoff-template.md` when work spans multiple sessions or needs a clean baton pass
