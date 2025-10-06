from pydantic_ai.toolsets import FunctionToolset

from scene_builder.database.material import MaterialDatabase
from scene_builder.database.object import ObjectDatabase

mat_db = MaterialDatabase()
obj_db = ObjectDatabase()

material_toolset = FunctionToolset([mat_db.query, mat_db.get_metadata])
shopping_toolset = FunctionToolset([obj_db.search, obj_db.pack])
