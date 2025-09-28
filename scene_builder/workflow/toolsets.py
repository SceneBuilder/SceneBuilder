from pydantic_ai.toolsets import FunctionToolset

from scene_builder.database.object import ObjectDatabase

obj_db = ObjectDatabase()

shopping_toolset = FunctionToolset([obj_db.search, obj_db.pack])
