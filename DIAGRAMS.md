# SceneBuilder System Diagrams and Descriptions

This document provides an overview of the SceneBuilder system's architecture, workflows, and key components. SceneBuilder is an AI-driven tool for generating 3D scenes from natural language prompts, leveraging Pydantic models, LLM agents, and Blender integration. The system operates through modular graphs and nodes that handle planning, object selection, placement, and visualization.

## Overall System Architecture

The high-level flow starts with a user prompt, processes it through AI agents and graphs to generate a scene definition (YAML), and optionally decodes it into Blender for rendering/export.

### Mermaid Flowchart: Main Generation Workflow
```mermaid
flowchart TD
    A[User Prompt] --> B[Main Graph Execution]
    B --> C{Design Rooms?}
    C -->|Yes| D[DesignLoopRouter]
    D --> E[RoomDesignNode]
    E --> F[Shopping for Objects]
    F --> G[PlacementNode]
    G --> H[PlacementVisualFeedback]
    H --> I{Approved?}
    I -->|No| G
    I -->|Yes| J[Next Room or End]
    J --> C
    C -->|No| K[Save Scene YAML]
    K --> L[Decode to Blender Optional]
    L --> M[Export .blend / .gltf]
```

**Description**: 
- The `main_graph` orchestrates scene generation by iterating over rooms via `DesignLoopRouter`.
- Each room undergoes design (planning, object selection, placement) until complete.
- Output is a YAML scene definition, which can be decoded into Blender scenes.

## Room Design Workflow

The room design process involves iterative refinement: planning the room, selecting objects (shopping), placing them, and critiquing via visual feedback.

### Mermaid Flowchart: Room Design Process
```mermaid
flowchart TD
    A[Room State Init] --> B[Generate Design Plan LLM Call]
    B --> C[Material Selection?]
    C -->|Change| D[Search Material DB]
    D --> E[Apply Floor Material]
    C -->|Keep| E
    E --> F[Shopping Agent: Select Objects]
    F --> G[Add to Shopping Cart]
    G --> H[Placement Loop Start]
    H --> I[Place Objects LLM Call]
    I --> J[Render Top-Down & Isometric Views]
    J --> K[Critique LLM: Approve/Reject]
    K -->|Reject| L[Feedback to Placement]
    L --> H
    K -->|Approve| M[Finalize Room]
    M --> N{Continue Design?}
    N -->|Yes| B
    N -->|No| O[Room Complete]
```

**Description**:
- `RoomDesignNode` manages the loop: Initial plan generation, material tweaks, object shopping, and iterative placement with visual critique.
- Uses `room_design_agent` for LLM decisions, integrated with tools for database queries.
- Termination based on run count, early config, or explicit completion signal.

## Placement Workflow

Placement focuses on positioning objects within a room, with visual feedback for refinement.

### Mermaid Flowchart: Placement Process
```mermaid
flowchart TD
    A[PlacementState Init<br/>Room + WhatToPlace] --> B[PlacementNode LLM Call]
    B --> C["Update Room Objects<br/>(Pos, Rot, Scale)"]
    C --> D[Render Views in Blender]
    D --> E[PlacementVisualFeedback]
    E --> F{Decision: Finalize?}
    F -->|No| G[Continue Placement]
    G --> B
    F -->|Yes| H[End Placement<br/>Return Updated Room]
```

**Description**:
- `PlacementNode` uses `placement_agent` to compute transformations for objects.
- `PlacementVisualFeedback` generates renders and appends to history for context.
- Loops until the agent decides to finalize (via `KeepEditingOrFinalize`).

## Key Components Table

| Component | Type | Description | Key Files/Imports | Inputs | Outputs |
|-----------|------|-------------|-------------------|--------|---------|
| **MainState** | Pydantic Model | Central state for scene generation, tracks prompt, scene, messages, room index. | `states.py` | User prompt | Scene definition |
| **RoomDesignState** | Pydantic Model | State for room-level design: room, plan, shopping cart, history. | `states.py` | Room init, plan | Updated Room |
| **PlacementState** | Pydantic Model | State for object placement: room, plan, item to place, history. | `states.py` | Room, ObjectBlueprint | Updated Room |
| **RoomDesignNode** | Graph Node | Orchestrates room design loop: planning, shopping, placement, critique. | `design.py` | RoomDesignState | Room or End[Room] |
| **PlacementNode** | Graph Node | Computes positions/rotations/scales for objects using LLM. | `placement.py` | PlacementState | Updated Room or End[Room] |
| **DesignLoopRouter** | Graph Node | Manages iteration over multiple rooms in a scene. | `design.py` | MainState | Scene or End[Scene] |
| **PlacementVisualFeedback** | Graph Node | Generates Blender renders for feedback loop. | `placement.py` | PlacementState | Next Node Trigger |
| **room_design_agent** | LLM Agent | Handles design decisions, tool calls for shopping/materials. | `agents.py` (inferred) | Prompts, state | Plans, Actions, Objects |
| **placement_agent** | LLM Agent | Focuses on spatial placement reasoning. | `agents.py` (inferred) | State, renders | PlacementAction |
| **main_graph** | Pydantic Graph | Top-level workflow graph combining design and placement. | `graphs.py` | MainState | Final Scene |
| **room_design_graph** | Pydantic Graph | Subgraph for single room design. | `design.py` | Room | Updated Room |
| **placement_graph** | Pydantic Graph | Subgraph for object placement iterations. | `placement.py` | PlacementState | Updated Room |
| **ObjectDatabase** | DB Client | Interfaces with Graphics-DB for assets/materials. | `database/object.py` | Queries | Assets, Blueprints |
| **Blender Decoder** | Module | Parses YAML to Blender scenes, handles rendering/export. | `decoder/blender.py` | Scene/Room YAML | .blend / .gltf files |

## Data Flow: Sequence Diagram

### Mermaid Sequence Diagram: Prompt to Scene Generation
```mermaid
sequenceDiagram
    participant U as User
    participant MG as MainGraph
    participant RD as RoomDesignNode
    participant PA as PlacementNode
    participant B as Blender
    participant S as Save YAML

    U->>MG: Provide Prompt
    MG->>RD: Init Room Design Loop
    RD->>PA: Place Objects Iteratively
    PA->>B: Parse & Render for Feedback
    B->>PA: Renders
    Note over PA,RD: Loop until Approved
    RD->>MG: Return Updated Room
    MG->>S: Save Scene YAML
    S->>U: Generated Scene
```

**Description**:
- Asynchronous graph execution (`asyncio.run(main_graph.run())`) drives the flow.
- States propagate data (e.g., `Room` models with objects' positions).
- Visual feedback uses Blender renders converted to binary for LLM input.
- Decode tools (e.g., `decode_room`) handle post-generation rendering/export separately.

## Theory of Operation

### Core Principles
- **Modular Graphs**: Uses `pydantic_graph` for composable workflows, allowing subgraphs (e.g., placement) within larger ones (e.g., room design).
- **Agent-Driven Decisions**: LLMs (via `pydantic_ai`) act as agents with tools for DB queries, generating structured outputs (Pydantic models).
- **Iterative Refinement**: Loops with visual feedback mimic human design: plan → act → critique → refine.
- **Blender Integration**: YAML definitions are parsed into Blender scenes for visualization and export; supports .blend, .gltf/.glb.
- **State Management**: Pydantic models ensure type-safe data flow; extras like `message_history` track LLM context.
- **Termination**: Controlled by config (e.g., `terminate_early`), run counts, or agent decisions (`complete=True`).

### Limitations & Notes
- Current implementation focuses on single-room scenes; multi-room expansion via loop.
- Debug mode uses mocks; production relies on local VLLM/Graphics-DB.
- Visual feedback is binary-encoded for LLM input, enabling image-conditioned reasoning.
- Shopping cart prevents duplicates but assumes quantity=1; future enhancements could add multi-instance support.

For implementation details, refer to source files like `main.py`, `nodes/design.py`, and `workflow/graphs.py`.