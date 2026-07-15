import pytest

from conftest import app_client


@pytest.mark.anyio
async def test_review_page_has_bulk_delete_controls():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'id="view-review"' in html
    assert 'id="final-video-bulk-toolbar"' in html
    assert 'id="final-video-selected-count"' in html
    assert 'id="final-video-select-all-btn"' in html
    assert 'id="final-video-clear-selection-btn"' in html
    assert 'id="final-video-delete-selected-btn"' in html


@pytest.mark.anyio
async def test_tasks_page_has_bulk_delete_controls():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'id="view-tasks"' in html
    assert 'id="task-delete-toolbar"' in html
    assert 'id="task-selected-count"' in html
    assert 'id="task-select-all-btn"' in html
    assert 'id="task-clear-selection-btn"' in html
    assert 'id="task-delete-selected-btn"' in html
    assert 'id="task-prev-page-btn"' in html
    assert 'id="task-next-page-btn"' in html
    assert 'id="task-page-indicator"' in html


@pytest.mark.anyio
async def test_frontend_script_contains_delete_confirm_copy():
    async with app_client() as client:
        response = await client.get("/static/platform/app.js")

    script = response.text
    assert "将删除成片记录及对应视频文件" in script
    assert "仅删除任务记录，不删除已生成文件" in script
