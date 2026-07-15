from pathlib import Path
import re

import pytest

from conftest import app_client


@pytest.mark.anyio
async def test_shell_contains_phase3_views_and_task_tab():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'id="view-lip-sync-video-select"' in html
    assert 'id="view-lip-sync-scripts"' in html
    assert 'id="view-lip-sync-confirm"' in html
    assert 'data-task-tab="lip-sync"' in html
    assert 'id="lip-sync-task-list"' in html


@pytest.mark.anyio
async def test_phase3_shell_contains_required_copy():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert "进入对口型生成" in html
    assert "每张卡片内都可直接预览" in html
    assert "超过 30 秒的视频仍会显示预览，但不能进入下一步。" in html
    assert "字数" in html
    assert "预估 TTS 时长" in html
    assert "最终TTS必须小于30秒，否则系统会自动拦截。" in html
    assert "选择非默认比例可能会改变原视频结构。" in html
    assert 'id="lip-sync-submit-status"' in html
    assert "视频生成时间较长，可前往任务进度页查看状态。" in html


@pytest.mark.anyio
async def test_phase3_titles_match_route_semantics():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert "对口型生成 - 基础视频选择" in html
    assert "对口型生成 - 文案生成与选择" in html
    assert "对口型生成 - 生成确认" in html


@pytest.mark.anyio
async def test_phase3_script_inputs_use_unified_visual_hooks():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'class="panel lip-sync-input-panel"' in html
    assert 'class="field-label field-label-strong"' in html
    assert 'id="lip-sync-prompt-input" class="text-field text-field-prominent"' in html
    assert 'id="lip-sync-product-doc-input" class="text-field text-field-prominent"' in html


def test_lip_sync_video_cards_render_inline_preview_and_keep_overlength_preview_structure():
    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")

    match = re.search(
        r"function renderLipSyncVideoList\(\) \{(?P<body>.*?)\n    \}\n\n    function renderLipSyncScriptPreview",
        script,
        re.S,
    )
    assert match, "未找到 renderLipSyncVideoList 函数体"
    body = match.group("body")

    assert '<div class="video-card-media">' in body
    assert '<video class="media-preview-small" controls preload="metadata" src="/api/videos/${video.id}/stream"></video>' in body
    assert "video-card-body" in body
    assert "data-lip-sync-preview" not in body
    assert "data-lip-sync-preview" not in script
    assert "function renderLipSyncPreview(videoId)" not in script
    assert "lipSyncVideoPreview" not in script
    assert 'const disabled = !video.selectable;' in body
    assert 'card.className = `panel video-card ${disabled ? "video-card-disabled" : ""}`;' in body
    assert 'disabled ? "ghost-btn" : "primary-btn"' in body
    assert "该视频超过30秒，无法用于对口型生成。" in body


@pytest.mark.anyio
async def test_phase3_lip_sync_select_page_uses_single_column_layout_without_side_preview_panel():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    section_match = re.search(
        r'<section id="view-lip-sync-video-select" class="view" data-view="lip-sync-video-select">(?P<body>.*?)</section>',
        html,
        re.S,
    )
    assert section_match, "未找到对口型视频选择区块"
    section_html = section_match.group("body")

    assert 'class="video-manager-grid lip-sync-video-manager-grid"' in section_html
    assert 'id="lip-sync-video-preview"' not in section_html
    assert section_html.count('class="panel"') == 1
    assert "每张卡片内都可直接预览" in section_html

    css = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.css"
    ).read_text(encoding="utf-8")
    assert "#view-lip-sync-video-select .video-manager-grid" in css
    assert "grid-template-columns: 1fr;" in css
    assert "#view-lip-sync-video-select .video-list" in css
    assert "repeat(auto-fit, minmax(260px, 1fr))" in css
    assert "#view-lip-sync-video-select .video-card-media" in css
    assert "aspect-ratio: 9 / 16;" in css
    assert "max-height: 360px;" in css
    assert "#view-lip-sync-video-select .video-card-media .media-preview-small" in css
    assert "object-fit: contain;" in css
