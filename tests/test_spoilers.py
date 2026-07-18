"""劇透 markup: :::spoiler blocks and ||inline|| reveals render to the
click-to-reveal HTML regardless of line endings (POS editor textareas and
the AI writer emit CRLF)."""
from app import markdown_with_spoilers

BLOCK = ":::spoiler 結局重雷\n他死了。\n:::\n\n後記。"


def test_block_renders_details():
    html = markdown_with_spoilers(BLOCK)
    assert '<details class="spoiler-block">' in html
    assert "⚠️ 結局重雷（點我展開）" in html
    assert ":::" not in html


def test_block_renders_with_crlf_body():
    html = markdown_with_spoilers(BLOCK.replace("\n", "\r\n"))
    assert '<details class="spoiler-block">' in html
    assert ":::" not in html


def test_block_default_title():
    html = markdown_with_spoilers(":::spoiler\n雷。\n:::")
    assert "⚠️ 劇透警告（點我展開）" in html


def test_inline_reveal():
    html = markdown_with_spoilers("其實||兇手是管家||啦。")
    assert '<span class="spoiler-inline"' in html
    assert "||" not in html
