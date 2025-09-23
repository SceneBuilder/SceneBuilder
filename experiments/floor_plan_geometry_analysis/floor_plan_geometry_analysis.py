# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.17.2
# ---

# %% [markdown]
# # **Floor Plan Geometry Analysis**

# %%
from pydantic import BaseModel
from pydantic_ai.models.gemini import GoogleModel
from pydantic_ai import Agent

from scene_builder.utils.pai import transform_paths_to_binary


# %%
class Vector2:
    x: int
    y: int

class Room:
    vertices: list[Vector2]
    label: str | None = None

class FloorPlanData:
    rooms: list[Room]


# %%
FILTER_PROMPT = """
You are part of a data analysis system whose goal is to extract building floor plan from images in Wikipedia. 
In specific, the focus is on extracting the interior layout. Your job is to filter out images that are not suitable for this. 

Please classify whether the image shown is a floor plan that fit into these criteria:
- is clean i.e., readily shows the room outline boundary
- in top-down view (vs. front or side views)
- has substantial information about the *interior* of the building
- has enough detail about underlying rooms (i.e., not just the building outlines, or about structural supports)
- and any other relevant criterion, based on your gut feeling. 

Output: 
- accept (bool): whether the image fit the criteria and seems suited for downstream floor plan extraction
- rationale (str): a short description explaining why it is accepted or rejected
"""

GEOMETRY_ANALYSIS_PROMPT = """
You are part of a data analysis system whose goal is to extract building floor plan that details the interior layout from images in Wikipedia. 
Your job is to extract the boundary outline of rooms and areas in the form of 2D vertices. 
This will be used to create a geometry representation of the floor plan. 

Please look at the image to create structured annotation 

Output: 

"""

# %%
model = GoogleModel("gemini-2.5-pro")
agent = Agent(model, system_prompt=PROMPT, output_type=FloorPlanData)

# %%
