```mermaid
---
title: app
---
stateDiagram-v2
  [*] --> MetadataAgent
  MetadataAgent --> ScenePlanningAgent
  ScenePlanningAgent --> FloorPlanAgent
  FloorPlanAgent --> DesignLoopEntry
  DesignLoopEntry --> RoomDesignAgent
  DesignLoopEntry --> [*]
  RoomDesignAgent --> UpdateMainStateAfterDesign
  UpdateMainStateAfterDesign --> DesignLoopEntry
```
