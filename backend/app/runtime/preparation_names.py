"""Explicit new preparation text, validated again after name substitution."""
from app.domains.characters.policies.authored_names import authored_fields


def authored_preparation(output, binding):
    if binding is None:
        return output
    value = output.model_dump(mode="json")
    if "daily_plan" in value:
        value["daily_plan"]["items"] = [authored_fields(row, binding,
            fields=("title", "activity_seed"), limits={"title": 120, "activity_seed": 500})
            for row in value["daily_plan"]["items"]]
    if "recommendation_topics" in value:
        value["recommendation_topics"] = [authored_fields(row, binding, fields=("name",), limits={"name": 120})
            for row in value["recommendation_topics"]]
    return type(output).model_validate(value)


def authored_topics(output, binding):
    value = output.model_dump(mode="json")
    value["topics"] = [authored_fields(row, binding, fields=("name",), limits={"name": 120})
                       for row in value["topics"]]
    return type(output).model_validate(value)
