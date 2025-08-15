```mermaid
---
title: placement_graph
---
stateDiagram-v2
  [*] --> PlacementAgent
  PlacementAgent --> VisualFeedback
  PlacementAgent --> [*]
  VisualFeedback --> PlacementAgent
```