"""Video postprocessing must preserve content that looks like Markdown syntax."""
import pytest
from note_summarizer import NoteSummarizer


def test_cleaning_preserves_the_last_real_code_fence():
    note = "# Title\n\n## Example\n\n```python\n# Source explanation\nprint(42)\n```"
    assert NoteSummarizer._clean_markdown(note) == note


@pytest.mark.parametrize("fence", ["```markdown", "```md", "~~~markdown", "````markdown"])
def test_only_the_outer_markdown_wrapper_is_removed(fence):
    body = "# Title\n\n```python\n# Exact source comment\nprint(42)\n```"
    # Keep the exact fence marker independently of the language label.
    closing = fence[:len(fence) - len(fence.lstrip('`~'))]
    assert NoteSummarizer._clean_markdown(fence + "\n" + body + "\n" + closing) == body


def test_a_real_python_block_is_not_treated_as_a_document_wrapper():
    block = "```python\n# Source explanation\nprint(42)\n```"
    assert NoteSummarizer._clean_markdown(block) == block


@pytest.mark.parametrize("fence", ["```", "~~~", "````"])
def test_merge_numbering_and_toc_preserve_code_comments_and_fake_headings(fence):
    note = NoteSummarizer(api_key="fixture")
    code = fence + "python\n# Original comment\n## A code comment\n## AI 总结\nprint(42)\n" + fence
    document = note._merge_chunk_notes("Title", ["## Real chapter\n\n" + code, "## Second chapter\n\nA condition."], True)
    assert code in document
    toc = document.split("\n\n---\n\n", 1)[0]
    assert "A code comment" not in toc and "AI 总结" not in toc
    assert "Second chapter" in document and "A condition." in document


def test_indented_code_is_not_deleted_or_renumbered_as_a_heading():
    note = NoteSummarizer(api_key="fixture")
    code = "    # Source comment\n    ## Another comment\n    print(42)"
    document = note._merge_chunk_notes("Title", ["## Example\n\n" + code, "## End\n\nFinal detail."], True)
    assert code in document and "Final detail." in document


def test_a_chunk_starting_with_indented_code_keeps_its_first_line():
    note = NoteSummarizer(api_key="fixture")
    code = "    # Source comment\n    print(42)"
    assert NoteSummarizer._clean_markdown(code) == code
    assert code in note._merge_chunk_notes("Title", [code, "## End\n\nFinal detail."], False)
