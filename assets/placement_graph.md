```mermaid
---
title: placement_graph
---
stateDiagram-v2
  [*] --> PlacementNode
  PlacementNode --> VisualFeedback
  PlacementNode --> [*]
  VisualFeedback --> PlacementNode
```