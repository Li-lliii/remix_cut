import pytest

from conftest import app_client


@pytest.mark.anyio
async def test_index_serves_phase1_shell():
    async with app_client() as client:
        response = await client.get("/")

    assert response.status_code == 200
    html = response.text
    assert 'id="app-shell"' in html
    assert "角色大厅" in html
    assert "新建角色" in html
    assert "任务进度" in html


@pytest.mark.anyio
async def test_app_subroutes_fallback_to_same_shell():
    async with app_client() as client:
        response = await client.get("/app/roles/demo")

    assert response.status_code == 200
    assert 'id="app-shell"' in response.text


@pytest.mark.anyio
async def test_shell_exposes_phase2_remix_entry_and_task_shell():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert "进入混合剪辑" in html
    assert "商品提示词" in html
    assert "目标生成数量" in html
    assert "选择非默认比例可能会改变原视频结构。" in html


@pytest.mark.anyio
async def test_shell_exposes_phase3_lip_sync_entry_and_routes():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert "进入对口型生成" in html
    assert 'id="view-lip-sync-video-select"' in html
    assert 'id="view-lip-sync-scripts"' in html
    assert 'id="view-lip-sync-confirm"' in html


@pytest.mark.anyio
async def test_shell_contains_role_overview_panel_contract():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'data-testid="role-overview-panel"' in html
    assert 'id="role-overview-title"' in html
    assert 'id="role-overview-video-count"' in html
    assert 'id="role-overview-latest-upload"' in html
    assert 'id="role-overview-task-status"' in html
