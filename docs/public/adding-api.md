# Adding an API operation

Add the route, schema, service policy, persistence behavior, and tests as one
reviewable contract. State whether the operation is public, authenticated,
owner-only, or Local Bot token protected.

Update the route-security inventory and generated OpenAPI checks. If the
operation belongs to Local Bot, update the 14-path deployment subset from the
canonical FastAPI document rather than hand-maintaining a conflicting schema.

Breaking path, payload, response, status, or ownership changes require explicit
approval and release notes.
