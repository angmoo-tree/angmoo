"""HTTP and schema adapters for the WorldCharacter domain.

Routes are imported explicitly by the API composition root.  Keeping this
package initializer side-effect free lets compatibility schema imports avoid
booting the whole FastAPI dependency graph.
"""
