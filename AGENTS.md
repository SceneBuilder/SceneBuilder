# Repository Guidelines

## Functionality & Theory of Operation
SceneBuilder exposes a Typer CLI (`scene_builder.main`) whose `generate` command seeds a `MainState` and runs `workflow.main_graph`. The graph loops through `DesignLoopRouter`, `RoomDesignNode`, and placement feedback nodes, each delegating to `pydantic_ai` agents to plan, shop, place, and critique. Blender adapters in `decoder/blender.py` turn intermediate `Room` models into renders and exports, keeping agents grounded in geometry. Object catalog queries flow through `database/object.py`, while Pydantic models in `definition/` carry structured scene data between nodes.

## Project Structure & Module Organization
The `scene_builder/` package contains workflows (`workflow/`), node logic (`nodes/`), Blender integration (`decoder/`), utilities, and global settings (`config.py`). Supporting datasets live under `assets/`, `data/`, `external/`, and `msd_integration/`. Automated coverage targets `tests/` with fixtures in `test_assets/` and cached renders in `test_output/`.

## Build, Test, and Development Commands
Use `python -m pip install -e .[dev]` for an editable install with test tooling. Run `pytest` (or module-specific invocations) before pushing, and exercise the pipeline with `python -m scene_builder.main generate "cozy loft"`. Inspect outputs or convert YAMLs via `python -m scene_builder.main decode room scenes/example.yaml -o out.blend`.

## Coding Style & Naming Conventions
PEP 8 with 4-space indents and 100-character lines is enforced via `black` and `ruff`. Keep modules lowercase with underscores, classes in `CamelCase`, and functions in `snake_case`, preserving type hints across agent interfaces.

## Testing Guidelines
Add scenarios to `tests/test_*.py`, mirroring real workflows with fixtures from `test_assets/` and expected artefacts in `test_output/`. Name tests after behaviors (`test_floor_mesh_handles_irregular_layout`). Mark GPU- or Blender-heavy cases so CI can skip when hardware is unavailable.

## Commit & Pull Request Guidelines
Write small, imperative commits (`add window cutout logic`) and mention related issues when relevant. PRs should summarize behavioral impact, attach renders or CLI transcripts when visuals change, and state that `pytest` plus formatting have been run. Call out edits to agent prompts, Blender exports, or database access so reviewers focus on high-risk areas.

## Blender & Asset Tips
Ensure Blender is on the `PATH` before invoking decode commands, and prefer adjusting `scene_builder/config.py` over hardcoding paths. Treat `external/` datasets as read-only mirrors; stash experimental assets under `test_assets/` and purge them before merge.

## Notes:
- The `bpy` module will always be available in the scope of this project!
- Tight integration with Blender is honestly fine, because it's the primary and only "decoder" (or 3D scene builder from Pydantic/YAML definitions)
- I'd like the code to be kept simple and maintainable. I'd actually prefer if exception handling is used sparingly so I can notice when something is wrong and debug/investigate.
- For tests, I want them to use the real thing (i.e., build the scene in Blender for real) instead of using mocks.  Note that `bpy` module is available even in tests.

Please let me know if you have any questions or need clarifications!
