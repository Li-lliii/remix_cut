from pathlib import Path
import re

import pytest

from conftest import app_client


@pytest.mark.anyio
async def test_shell_contains_phase2_views():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'id="view-remix-video-select"' in html
    assert 'id="view-remix-task-create"' in html
    assert 'id="view-tasks"' in html
    assert 'data-testid="task-tabs"' in html
    assert 'data-task-tab="preprocess"' in html
    assert 'data-task-tab="remix"' in html
    assert "混合剪辑 - 视频选择" in html
    assert "混合剪辑 - 任务创建" in html
    assert "任务进度页" in html
    assert 'id="remix-video-list"' in html
    assert 'id="remix-task-form"' in html
    assert 'id="selected-remix-video-summary"' in html
    assert 'id="preprocess-job-list"' in html
    assert 'id="remix-task-list"' in html
    assert 'id="remix-video-preview"' in html
    assert 'id="remix-prompt-input"' in html
    assert 'required' in html.split('id="remix-prompt-input"', 1)[1].split(">", 1)[0]
    assert 'id="task-delete-toolbar"' in html
    assert 'id="task-prev-page-btn"' in html
    assert 'id="task-next-page-btn"' in html
    assert 'id="task-page-indicator"' in html


@pytest.mark.anyio
async def test_shell_contains_three_task_tabs_without_asr_tab():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert html.count('data-task-tab="') == 3
    assert 'data-task-tab="preprocess"' in html
    assert 'data-task-tab="remix"' in html
    assert 'data-task-tab="lip-sync"' in html
    assert 'data-task-tab="asr"' not in html
    assert 'id="asr-task-list"' not in html
    assert 'id="preprocess-job-table"' not in html
    assert '每页 7 条' in html


@pytest.mark.anyio
async def test_shell_contains_inline_remix_preview_hooks():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert "点击左侧视频卡片即可直接预览" in html
    assert "视频预览已移至卡片" in html
    assert 'class="video-manager-grid remix-video-manager-grid"' in html

    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")
    match = re.search(r"function renderRemixVideoList\(\) \{(?P<body>.*?)\n    \}\n\n    function renderLipSyncVideoList", script, re.S)
    assert match, "未找到 renderRemixVideoList 函数体"
    body = match.group("body")
    assert '<video class="media-preview-small" controls preload="metadata" src="/api/videos/${video.id}/stream"></video>' in body
    assert "video-card-media" in script
    assert 'data-remix-select="${video.id}">混剪生成视频</button>' in body
    assert 'data-smart-clip-start="${video.id}">智能切片</button>' in body
    assert 'data-smart-clip-restart="${video.id}"' not in body
    assert "data-remix-preview" not in script
    assert "renderRemixPreview" not in script

    css = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.css"
    ).read_text(encoding="utf-8")
    assert "#view-remix-video-select .video-manager-grid" in css
    assert "grid-template-columns: 1fr" in css
    assert "#view-remix-video-select .video-list" in css
    assert "repeat(auto-fit, minmax(260px, 1fr))" in css
    assert "#view-remix-video-select .video-card-media" in css
    assert "aspect-ratio: 9 / 16;" in css
    assert "max-height: 360px;" in css
    assert "place-items: center;" in css
    assert "#view-remix-video-select .video-card-media .media-preview-small" in css
    assert "object-fit: contain;" in css


@pytest.mark.anyio
async def test_shell_contains_smart_clip_project_view_and_hooks():
    async with app_client() as client:
        response = await client.get("/")

    html = response.text
    assert 'id="view-smart-clip-project"' in html
    assert 'id="smart-clip-project-title"' in html
    assert 'id="smart-clip-progress-panel"' in html
    assert 'id="smart-clip-progress-bar"' in html
    assert 'id="smart-clip-candidate-list"' in html
    assert 'id="smart-clip-export-btn"' in html
    assert 'id="smart-clip-restart-btn"' in html
    assert "智能切片项目" in html

    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")
    assert 'smartClipProject: null,' in script
    assert 'smartClipCandidates: [],' in script
    assert '"smart-clip-project"' in script
    assert 'data-smart-clip-start="${video.id}"' in script
    assert 'smart-clip-restart-btn' in script
    assert 'function loadSmartClipProject(projectId)' in script
    assert 'function renderSmartClipProject()' in script
    assert 'function renderSmartClipCandidates()' in script
    assert 'function upsertSmartClipCandidateCard(candidate)' in script
    assert 'smartClipCandidateListFrozen: false,' in script
    assert 'if (state.smartClipCandidateListFrozen) {' in script
    assert 'document.addEventListener("fullscreenchange"' in script
    assert 'data-open-smart-clip-project="${item.project_id || item.id}"' in script
    assert "原视频时间段：" not in script

    css = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.css"
    ).read_text(encoding="utf-8")
    assert "#view-smart-clip-project .task-create-grid" in css
    assert ".smart-clip-progress-panel" in css
    assert ".smart-clip-candidate-card" in css
    assert ".smart-clip-progress-track" in css
    assert ".smart-clip-progress-bar" in css


def test_task_page_script_uses_pagination_and_unified_preprocess_stream():
    script = Path(
        "/zhouzhiboa/bs_media/.worktrees/phase2-remix-minimal-loop/function/remix_cut/metahuman_platform/static/platform/app.js"
    ).read_text(encoding="utf-8")

    assert 'const TASK_PAGE_SIZE = 7;' in script
    assert 'state.taskPagination = {' in script
    assert 'preprocess: 1,' in script
    assert '"lip-sync": 1,' in script
    assert 'function buildPreprocessTaskItems()' in script
    assert 'state.asrRecords.map((record) => ({' in script
    assert 'state.preprocessJobs.map((job) => ({' in script
    assert 'sort_time: getTaskSortTime(record.uploaded_at),' in script
    assert 'sort_time: getTaskSortTime(job.started_at || job.created_at),' in script
    assert 'function getTaskPageMeta(tab)' in script
    assert 'state.taskPagination[tab] = currentPage;' in script
    assert 'taskPageIndicator.textContent = `第 ${meta.page} / ${meta.totalPages} 页，每页 ${TASK_PAGE_SIZE} 条`;' in script
    assert 'taskPrevPageBtn.addEventListener("click"' in script
    assert 'taskNextPageBtn.addEventListener("click"' in script
    assert 'state.taskPagination[tab] = Math.max(1, meta.page - 1);' in script
    assert 'state.taskPagination[tab] = Math.min(meta.totalPages, meta.page + 1);' in script
    assert 'taskSelectAllBtn.textContent = allVisibleSelected ? "取消全选当前页" : "全选当前页";' in script
    assert "const ids = getTaskPageSelectableIds(tab);" in script
    assert 'taskSelectAllBtn.disabled = state.taskRecordDeleting || visibleSelectableIds.length === 0;' in script
    assert 'await deleteTaskRecords(state.activeTaskTab, getSelectedTaskIds(state.activeTaskTab));' in script
    assert 'state.activeTaskTab = tab.dataset.taskTab;' in script
    assert 'tab.addEventListener("click", () => {' in script
    assert 'preprocessJobList.hidden = state.activeTaskTab !== "preprocess";' in script
    assert 'remixTaskList.hidden = state.activeTaskTab !== "remix";' in script
    assert 'lipSyncTaskList.hidden = state.activeTaskTab !== "lip-sync";' in script
    assert 'item.task_type === "smart_clip"' in script
    assert 'data-open-smart-clip-project="${item.project_id || item.id}"' in script
