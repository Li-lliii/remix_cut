import anyio
import pytest
from pathlib import Path

from conftest import app_client


@pytest.mark.anyio
async def test_shell_index_returns_without_hanging():
    async with app_client() as client:
        with anyio.fail_after(1):
            response = await client.get("/")

    assert response.status_code == 200


@pytest.mark.anyio
async def test_shell_contains_phase1_views():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert "角色大厅" in html
    assert "角色视频管理页" in html
    assert 'id="lobby-nav"' in html
    assert 'id="workbench-nav"' in html
    assert 'id="sidebar-role-name"' in html
    assert 'id="switch-role-btn"' in html
    assert "视频管理" in html
    assert "混合剪辑" in html
    assert "对口型生成" in html
    assert "任务进度" in html
    assert "审核与成片" in html
    assert 'data-testid="video-preview-container"' in html
    assert 'data-testid="asr-status-panel"' in html
    assert 'data-testid="asr-summary-panel"' in html
    assert 'data-testid="upload-progress-panel"' in html
    assert 'data-testid="upload-progress-bar"' in html
    assert 'video-preview-compact' in html
    assert 'data-group="pinned"' in html
    assert 'data-group="recent"' in html
    assert 'data-group="week"' in html
    assert 'data-group="old"' in html
    assert "进入对口型生成" in html
    assert 'data-route="role-actions"' not in html
    assert 'id="lip-sync-generation-status"' in html
    assert 'id="lip-sync-product-doc-upload-input"' in html
    assert 'id="lip-sync-product-doc-list"' in html


def test_workspace_nav_routes_trigger_data_loading():
    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")

    assert 'if (route === "remix-video-select")' in script
    assert "await loadRemixVideos()" in script
    assert 'if (route === "lip-sync-video-select")' in script
    assert "await loadLipSyncVideos()" in script


@pytest.mark.anyio
async def test_shell_contains_role_cover_hooks():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'id="role-cover-upload-input"' in html

    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")
    assert "role-card-cover" in script
    assert "data-role-cover-upload" in script
    assert "data-role-delete" in script
    assert "roleCoverUploadInput" in script
    assert "更换封面" in script
    assert "删除角色" in script
    assert 'const imageUrl = String(role.avatar_url || "").trim();' in script
    assert "image.src = imageUrl;" in script


def test_role_cover_click_handler_prioritizes_cover_upload_before_enter_role():
    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")

    listener_start = script.index('roleGrid?.addEventListener("click", (event) => {')
    listener_end = script.index('    });', listener_start)
    listener = script[listener_start:listener_end]

    expected_branch = (
        'const coverUpload = event.target.closest("[data-role-cover-upload]");\n'
        '        if (coverUpload) {\n'
        '            openRoleCoverUpload(coverUpload.dataset.roleCoverUpload);\n'
        '            return;\n'
        '        }\n'
        '        const deleteRole = event.target.closest("[data-role-delete]");\n'
        '        if (deleteRole) {\n'
        '            confirmDeleteRole(deleteRole.dataset.roleDelete).catch(console.error);\n'
        '            return;\n'
        '        }\n'
        '        const target = event.target.closest("[data-role-enter]");'
    )
    assert expected_branch in listener


def test_role_card_script_and_styles_support_delete_and_compact_cover():
    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")
    css = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.css"
    ).read_text(encoding="utf-8")

    assert "删除角色后将一并删除该角色下的上传视频、生成视频、任务记录及相关文件，且不可恢复。" in script
    assert "role-card-content" in script
    assert "role-card-meta" in script
    assert "danger-btn" in script
    assert ".role-card-cover" in css
    assert "grid-template-columns: repeat(auto-fill, minmax(260px, 320px));" in css
    assert "justify-content: start;" in css
    assert "width: min(100%, 320px);" in css
    assert "aspect-ratio: 9 / 16;" in css
    assert ".role-card-content" in css
    assert "min-height: 190px;" in css
    assert ".role-card-meta" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert ".role-card-actions .danger-btn" in css


@pytest.mark.anyio
async def test_shell_uses_speech_to_text_copy_in_video_manager():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert "语音转文字状态" in html
    assert "语音转文字总结" in html
    assert "ASR 摘要" not in html
    assert "刷新语音转文字状态" in html
    assert "查看语音转文字" in html

    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")
    assert 'if (status === "success") return "语音转文字完成";' in script
    assert 'if (status === "failed") return "语音转文字失败";' in script
    assert 'if (status === "running") return "语音转文字处理中";' in script
    failed_status_index = script.index('} else if (payload.status === "failed") {')
    summary_failed_index = script.index('} else if (summarySource === "failed") {')
    assert failed_status_index < summary_failed_index
    assert "视频语音已识别完成，总结暂不可用，请稍后重试" in script
    assert "正在整理视频内容总结" in script
    assert "查询语音转文字状态失败，请稍后刷新重试。" in script
