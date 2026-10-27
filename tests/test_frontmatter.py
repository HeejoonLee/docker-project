from stonepedia import bundle, frontmatter


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


def test_import_infers_nested_id_field_without_numeric_ids(tmp_path):
    article = tmp_path / "topic.md"
    article.write_text(frontmatter.join(
        {"type": "Guidance", "cornerstone": {"knowledge_id": "boot-flow"}}, "\n# Boot\n"
    ))
    field, prefix, digits, warning = bundle.infer_id_scheme(tmp_path)
    assert (field, prefix, digits) == ("cornerstone.knowledge_id", "", 2)
    assert "Review ID generation" in warning


def test_import_reports_ambiguous_id_fields(tmp_path):
    article = tmp_path / "topic.md"
    article.write_text(frontmatter.join(
        {"id": "KB-01", "cornerstone": {"knowledge_id": "BK-01"}}, "\n# Boot\n"
    ))
    field, _, _, warning = bundle.infer_id_scheme(tmp_path)
    assert field == "id"
    assert "cornerstone.knowledge_id" in warning and "id" in warning
