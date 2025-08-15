```mermaid
---
title: room_design_graph
---
stateDiagram-v2
  [*] --> DesignLoopEntry
  DesignLoopEntry --> [*]
  RoomDesignAgent --> UpdateScene
  UpdateScene --> DesignLoopEntry
```