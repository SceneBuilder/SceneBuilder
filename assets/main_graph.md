```mermaid
---
title: app
---
stateDiagram-v2
  [*] --> MetadataAgent
  MetadataAgent --> BuildingPlanAgent
  BuildingPlanAgent --> FloorPlanAgent
  FloorPlanAgent --> DesignLoopEntry
  DesignLoopEntry --> RoomDesignAgent
  DesignLoopEntry --> [*]
  RoomDesignAgent --> UpdateMainStateAfterDesign
  UpdateMainStateAfterDesign --> DesignLoopEntry
```
