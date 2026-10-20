"""The default Template copied into every new Bundle (`.stonepedia/template.yaml`)."""

DEFAULT_TEMPLATE: dict = {
    "types": [
        {
            "name": "Specification",
            "rule": "Defines obligations: what must be satisfied, and how conformance is judged.",
            "sections": ["Purpose", "Requirements", "Conformance", "Open questions"],
        },
        {
            "name": "Guidance",
            "rule": "Explains the domain or how to perform work: what to understand, how to proceed.",
            "sections": ["Question", "Explanation", "Limits"],
        },
        {
            "name": "Decision",
            "rule": "Preserves a specific choice and its rationale, and when to reconsider it.",
            "sections": ["Choice", "Rationale", "Reconsider when"],
        },
    ],
    "fields": [
        {"name": "type", "written_by": "ai", "required": True, "description": "One of the types above."},
        {"name": "title", "written_by": "ai", "required": True, "description": "Specific, searchable title."},
        {"name": "description", "written_by": "ai", "required": True, "description": "One sentence on what the Article covers."},
        {"name": "tags", "written_by": "ai", "required": False, "description": "Short topic tags."},
        {"name": "maintenance", "written_by": "ai", "required": False, "description": "triggers: changes that should prompt review."},
        {"name": "status", "written_by": "system"},
        {"name": "sources", "written_by": "system"},
        {"name": "generated", "written_by": "system"},
        {"name": "review", "written_by": "system"},
    ],
    "guidance": (
        "Prefer updating an existing Article over creating a near-duplicate; keep one home per fact.\n"
        "Mark assumptions and unknowns explicitly; never invent values.\n"
        "Keep original technical terms."
    ),
}
