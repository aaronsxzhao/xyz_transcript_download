"""Video postprocessing must preserve content that looks like Markdown syntax."""
import pytest
from note_summarizer import NoteSummarizer, _repair_numbered_heading_markers


def test_repeated_heading_markers_are_repaired_without_rewriting_source_examples():
    source = '## 8. 学习\n\n### 8.2 #### 优化模式识别的重要性\n\n### 8.3 ### 视频风格说明\n\n`### 8.2 #### Inline`\n\n```md\n### 8.2 #### Literal\n```\n\n> ### 8.2 #### Quoted original\n\n    ### 8.2 #### Indented code\n\n8.2 #### Plain text\n\n### C# and ## symbols\n'
    expected = source.replace('### 8.2 #### 优化模式识别的重要性', '### 8.2 优化模式识别的重要性').replace('### 8.3 ### 视频风格说明', '### 8.3 视频风格说明')
    assert _repair_numbered_heading_markers(source) == expected
    assert _repair_numbered_heading_markers(expected) == expected
    assert NoteSummarizer._clean_markdown(source) == expected.rstrip('\n')
    document = NoteSummarizer(api_key='fixture')._merge_chunk_notes('Title', [source], True)
    assert '### 1.1 优化模式识别的重要性' in document
    assert '### 1.2 视频风格说明' in document
    assert '```md\n### 8.2 #### Literal\n```' in document
    assert '[1.1 优化模式识别的重要性](#11-优化模式识别的重要性)' in document


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


def test_toc_tracks_nested_and_hidden_headings_and_uses_visible_link_text():
    note = NoteSummarizer(api_key="fixture")
    toc = note._generate_toc("## [Plan](https://example.com)\n\n> ## Plan\n\n### Plan-1\n\n#### Plan\n\n## Plan")
    assert '[Plan](#plan)' in toc
    assert '[Plan](#plan-1)' in toc
    assert '[Plan-1](#plan-1-1)' in toc
    assert '[Plan](#plan-3)' in toc
    assert 'https://example.com' not in toc


def test_slug_reserves_emitted_suffixes_and_supplies_an_anchor_for_symbol_only_titles():
    counts = {}
    anchors = [NoteSummarizer._github_slug(title, counts) for title in ['Plan', 'Plan', 'Plan-1', 'Plan', '🎯', '🎯']]
    assert len(set(anchors)) == len(anchors)
    assert all(anchors)


def test_exported_toc_accounts_for_the_episode_title_before_its_first_chapter():
    note = NoteSummarizer(api_key="fixture")
    document = note._merge_chunk_notes('1. Plan', ['## Plan\n\nFirst detail.', '## End\n\nLast detail.'], True)
    assert '[1. Plan](#1-plan-1)' in document
    assert 'First detail.' in document and 'Last detail.' in document
