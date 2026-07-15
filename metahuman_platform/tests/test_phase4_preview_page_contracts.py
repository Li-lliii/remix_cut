from pathlib import Path

import pytest

from conftest import app_client


@pytest.mark.anyio
async def test_review_shell_contains_final_video_preview_controls():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'id="view-review"' in html
    assert 'id="final-video-search-input"' in html
    assert 'id="final-video-source-type-filter"' in html
    assert 'id="final-video-count"' in html
    assert 'id="final-video-list"' in html
    assert "原始视频名称" in html
    assert "生成类型" in html


def test_review_page_script_loads_final_videos_for_selected_role():
    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")

    assert "finalVideos" in script
    assert "loadFinalVideos" in script
    assert 'request(`/api/final-videos?' in script
    assert 'params.set("role_id", state.selectedRole.id)' in script
    assert 'if (route === "review")' in script
    assert "await loadFinalVideos()" in script


def test_review_page_cards_show_source_video_title_and_source_type():
    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")

    assert "source_video_title" in script
    assert "source_type" in script
    assert "当前角色暂无成功生成的视频" in script
    assert "未找到匹配的原始视频名称" in script
