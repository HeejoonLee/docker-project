from stonepedia import frontmatter


def test_finalize_rewrites_system_fields_and_keeps_unknown_ones():
    base = frontmatter.join(
        {"type": "Decision", "title": "Old", "cornerstone": {"knowledge_id": "BK-01"}, "sources": [{"id": "wbs"}],
         "status": "accepted", "review": {"reviewer": "kim"}},
        "\n# Old\n",
    )
    written = frontmatter.join(
        {"type": "Decision", "title": "New", "status": "draft", "review": {"reviewer": "agent"}}, "# New\n"
    )
    meta, body = frontmatter.split(frontmatter.finalize(written, base, {"by": "claude-code", "at": "t"}))
    assert meta["title"] == "New"
    assert meta["cornerstone"] == {"knowledge_id": "BK-01"}  # unknown field restored
    assert meta["sources"] == [{"id": "wbs"}]  # system field kept from base, not from agent
    assert meta["status"] == "proposed" and "review" not in meta
    assert meta["generated"] == {"by": "claude-code", "at": "t"}
    assert body == "\n# New\n"


def test_split_without_frontmatter():
    assert frontmatter.split("# Just text\n") == ({}, "# Just text\n")


def test_finalize_keeps_field_order_of_previous_version():
    base = frontmatter.join({"type": "Guidance", "status": "accepted", "title": "T", "x": 1, "review": {}}, "\n")
    written = frontmatter.join({"title": "T2", "type": "Guidance", "x": 1, "new": True}, "\n")
    meta, _ = frontmatter.split(frontmatter.finalize(written, base, {"by": "a", "at": "t"}))
    assert list(meta) == ["type", "status", "title", "x", "new", "generated"]
