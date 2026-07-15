(function () {
    const state = {
        route: "lobby",
        roles: [],
        selectedRole: null,
        videos: [],
        selectedVideo: null,
        remixVideos: [],
        selectedRemixVideo: null,
        selectedRemixPreviewId: null,
        smartClipProject: null,
        smartClipCandidates: [],
        preprocessJob: null,
        preprocessSegments: [],
        preprocessJobs: [],
        asrRecords: [],
        remixTasks: [],
        lipSyncVideos: [],
        selectedLipSyncVideo: null,
        lipSyncProject: null,
        lipSyncCandidates: [],
        selectedLipSyncScriptId: null,
        lipSyncGeneratingScripts: false,
        lipSyncScriptGenerationMessage: "",
        lipSyncRegeneratingCandidateId: null,
        lipSyncSubmittingTask: false,
        lipSyncSubmitStatus: "",
        lipSyncSubmitMessage: "",
        lipSyncProductDocs: [],
        selectedLipSyncProductDocId: null,
        lipSyncTasks: [],
        finalVideos: [],
        finalVideoQuery: "",
        finalVideoSourceType: "all",
        finalVideoSelectedIds: new Set(),
        finalVideoDeleting: false,
        activeTaskTab: "preprocess",
        taskPagination: {
            preprocess: 1,
            remix: 1,
            "lip-sync": 1,
        },
        taskRecordSelectedIds: {
            preprocess: new Set(),
            remix: new Set(),
            "lip-sync": new Set(),
        },
        taskRecordDeleting: false,
        uploadState: {
            active: false,
            progress: 0,
            message: "等待上传",
        },
        asrPollingTimer: null,
        taskPollingTimer: null,
        smartClipPollingTimer: null,
        smartClipCandidateListFrozen: false,
    };

    const TASK_PAGE_SIZE = 7;

    const workbenchRoutes = new Set([
        "video-manager",
        "remix-video-select",
        "smart-clip-project",
        "remix-task-create",
        "lip-sync-video-select",
        "lip-sync-scripts",
        "lip-sync-confirm",
        "tasks",
        "review",
    ]);

    const routeMap = {
        lobby: "/",
        "create-role": "/app/roles/new",
        "video-manager": "/app/roles/videos",
        "remix-video-select": "/app/remix/videos",
        "smart-clip-project": "/app/remix/smart-clips",
        "remix-task-create": "/app/remix/create",
        "lip-sync-video-select": "/app/lip-sync/videos",
        "lip-sync-scripts": "/app/lip-sync/scripts",
        "lip-sync-confirm": "/app/lip-sync/confirm",
        tasks: "/app/tasks",
        review: "/app/review",
    };
    const reverseRouteMap = {
        "/": "lobby",
        "/app/roles/new": "create-role",
        "/app/roles/videos": "video-manager",
        "/app/remix/videos": "remix-video-select",
        "/app/remix/smart-clips": "smart-clip-project",
        "/app/remix/create": "remix-task-create",
        "/app/lip-sync/videos": "lip-sync-video-select",
        "/app/lip-sync/scripts": "lip-sync-scripts",
        "/app/lip-sync/confirm": "lip-sync-confirm",
        "/app/tasks": "tasks",
        "/app/review": "review",
    };

    const views = {
        lobby: document.getElementById("view-lobby"),
        "create-role": document.getElementById("view-create-role"),
        "role-actions": document.getElementById("view-role-actions"),
        "video-manager": document.getElementById("view-video-manager"),
        "remix-video-select": document.getElementById("view-remix-video-select"),
        "smart-clip-project": document.getElementById("view-smart-clip-project"),
        "remix-task-create": document.getElementById("view-remix-task-create"),
        "lip-sync-video-select": document.getElementById("view-lip-sync-video-select"),
        "lip-sync-scripts": document.getElementById("view-lip-sync-scripts"),
        "lip-sync-confirm": document.getElementById("view-lip-sync-confirm"),
        tasks: document.getElementById("view-tasks"),
        review: document.getElementById("view-review"),
    };

    const roleGrid = document.getElementById("role-grid");
    const createRoleForm = document.getElementById("create-role-form");
    const globalRoleSearch = document.getElementById("global-role-search");
    const lobbyNav = document.getElementById("lobby-nav");
    const workbenchNav = document.getElementById("workbench-nav");
    const sidebarRoleName = document.getElementById("sidebar-role-name");
    const switchRoleBtn = document.getElementById("switch-role-btn");
    const roleOverviewTitle = document.getElementById("role-overview-title");
    const roleOverviewSubtitle = document.getElementById("role-overview-subtitle");
    const roleOverviewVideoCount = document.getElementById("role-overview-video-count");
    const roleOverviewLatestUpload = document.getElementById("role-overview-latest-upload");
    const roleOverviewTaskStatus = document.getElementById("role-overview-task-status");
    const selectedRoleName = document.getElementById("selected-role-name");
    const videoManagerRoleName = document.getElementById("video-manager-role-name");
    const roleCoverUploadInput = document.getElementById("role-cover-upload-input");
    const videoUploadInput = document.getElementById("video-upload-input");
    const uploadProgressPanel = document.getElementById("upload-progress-panel");
    const uploadProgressText = document.getElementById("upload-progress-text");
    const uploadProgressPercent = document.getElementById("upload-progress-percent");
    const uploadProgressBar = document.getElementById("upload-progress-bar");
    const videoPreviewContainer = document.getElementById("video-preview-container");
    const asrStatusPanel = document.getElementById("asr-status-panel");
    const asrSummaryPanel = document.getElementById("asr-summary-panel");
    const remixVideoList = document.getElementById("remix-video-list");
    const remixVideoPreview = document.getElementById("remix-video-preview");
    const remixVideoSearch = document.getElementById("remix-video-search");
    const smartClipProjectTitle = document.getElementById("smart-clip-project-title");
    const smartClipProjectStatus = document.getElementById("smart-clip-project-status");
    const smartClipProjectStage = document.getElementById("smart-clip-project-stage");
    const smartClipSourceSummary = document.getElementById("smart-clip-source-summary");
    const smartClipProgressPanel = document.getElementById("smart-clip-progress-panel");
    const smartClipProgressText = document.getElementById("smart-clip-progress-text");
    const smartClipProgressCounts = document.getElementById("smart-clip-progress-counts");
    const smartClipProgressBar = document.getElementById("smart-clip-progress-bar");
    const smartClipProgressSummary = document.getElementById("smart-clip-progress-summary");
    const smartClipCandidateList = document.getElementById("smart-clip-candidate-list");
    const smartClipRestartBtn = document.getElementById("smart-clip-restart-btn");
    const smartClipExportBtn = document.getElementById("smart-clip-export-btn");
    const selectedRemixVideoSummary = document.getElementById("selected-remix-video-summary");
    const remixTaskForm = document.getElementById("remix-task-form");
    const remixAspectModeInput = document.getElementById("remix-aspect-mode-input");
    const remixAspectWarning = document.getElementById("remix-aspect-warning");
    const preprocessJobList = document.getElementById("preprocess-job-list");
    const remixTaskList = document.getElementById("remix-task-list");
    const lipSyncVideoList = document.getElementById("lip-sync-video-list");
    const lipSyncVideoSearch = document.getElementById("lip-sync-video-search");
    const lipSyncScriptPreview = document.getElementById("lip-sync-script-preview");
    const lipSyncCandidateList = document.getElementById("lip-sync-candidate-list");
    const lipSyncGenerationStatus = document.getElementById("lip-sync-generation-status");
    const lipSyncProductDocInput = document.getElementById("lip-sync-product-doc-input");
    const lipSyncProductDocUploadInput = document.getElementById("lip-sync-product-doc-upload-input");
    const lipSyncProductDocList = document.getElementById("lip-sync-product-doc-list");
    const lipSyncConfirmSummary = document.getElementById("lip-sync-confirm-summary");
    const lipSyncAspectModeInput = document.getElementById("lip-sync-aspect-mode-input");
    const lipSyncAspectWarning = document.getElementById("lip-sync-aspect-warning");
    const lipSyncSubmitStatus = document.getElementById("lip-sync-submit-status");
    const submitLipSyncTaskButton = document.getElementById("submit-lip-sync-task-btn");
    const lipSyncTaskList = document.getElementById("lip-sync-task-list");
    const finalVideoSearchInput = document.getElementById("final-video-search-input");
    const finalVideoSourceTypeFilter = document.getElementById("final-video-source-type-filter");
    const finalVideoCount = document.getElementById("final-video-count");
    const finalVideoList = document.getElementById("final-video-list");
    const finalVideoBulkToolbar = document.getElementById("final-video-bulk-toolbar");
    const finalVideoSelectedCount = document.getElementById("final-video-selected-count");
    const finalVideoSelectAllBtn = document.getElementById("final-video-select-all-btn");
    const finalVideoClearSelectionBtn = document.getElementById("final-video-clear-selection-btn");
    const finalVideoDeleteSelectedBtn = document.getElementById("final-video-delete-selected-btn");
    const taskDeleteToolbar = document.getElementById("task-delete-toolbar");
    const taskSelectedCount = document.getElementById("task-selected-count");
    const taskSelectAllBtn = document.getElementById("task-select-all-btn");
    const taskClearSelectionBtn = document.getElementById("task-clear-selection-btn");
    const taskDeleteSelectedBtn = document.getElementById("task-delete-selected-btn");
    const taskPrevPageBtn = document.getElementById("task-prev-page-btn");
    const taskNextPageBtn = document.getElementById("task-next-page-btn");
    const taskPageIndicator = document.getElementById("task-page-indicator");
    const taskTabs = document.querySelectorAll("[data-task-tab]");

    const FINAL_VIDEO_DELETE_CONFIRM = "将删除成片记录及对应视频文件，不可恢复。";
    const TASK_RECORD_DELETE_CONFIRM = "仅删除任务记录，不删除已生成文件。";
    let pendingRoleCoverUploadId = null;

    function shortId(value) {
        const raw = String(value || "").trim();
        return raw ? raw.slice(0, 8) : "-";
    }

    function notifyBatchDeleteResult(label, payload, totalCount) {
        if (!payload || totalCount <= 1) {
            return;
        }
        const deletedCount = Number(payload.deleted_count || 0);
        const failedCount = Number(payload.failed_count || 0);
        if (failedCount <= 0) {
            return;
        }
        if (deletedCount > 0) {
            window.alert(`已删除 ${deletedCount} 条${label}，另有 ${failedCount} 条删除失败。失败项已保留选中，请刷新后重试。`);
            return;
        }
        window.alert(`未成功删除任何${label}。共 ${failedCount} 条删除失败，失败项已保留选中，请检查任务是否仍在运行中。`);
    }

    function syncNav(route) {
        document.querySelectorAll("[data-route]").forEach((node) => {
            node.classList.toggle("active", route === node.dataset.route);
        });
    }

    function syncWorkbenchNav() {
        const hasRole = Boolean(state.selectedRole);
        if (lobbyNav) {
            lobbyNav.hidden = hasRole;
        }
        if (workbenchNav) {
            workbenchNav.hidden = !hasRole;
        }
        if (sidebarRoleName) {
            sidebarRoleName.textContent = hasRole ? state.selectedRole.name : "未选择角色";
        }
        if (switchRoleBtn) {
            switchRoleBtn.hidden = !hasRole;
        }
        renderRoleOverview();
    }

    function formatDisplayTime(value) {
        if (!value) return "暂无";
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return "暂无";
        return date.toLocaleString("zh-CN", { hour12: false });
    }

    function hasActiveTask() {
        const activeStatuses = new Set([
            "pending",
            "running",
            "processing",
            "preprocessing",
            "rewriting",
            "tts_generating",
            "video_generating",
        ]);
        const jobs = [
            ...(state.preprocessJobs || []),
            ...(state.remixTasks || []),
            ...(state.lipSyncTasks || []),
        ];
        return jobs.some((item) => activeStatuses.has(item.status));
    }

    function renderRoleOverview() {
        const hasRole = Boolean(state.selectedRole);
        if (roleOverviewTitle) {
            roleOverviewTitle.textContent = hasRole ? state.selectedRole.name : "未选择角色";
        }
        if (roleOverviewSubtitle) {
            roleOverviewSubtitle.textContent = hasRole
                ? "这里展示当前角色的核心状态，方便快速判断素材是否充足、是否有最新上传和是否正在处理任务。"
                : "选择一个角色后，这里会显示视频数量、最新上传时间和任务状态。";
        }
        if (roleOverviewVideoCount) {
            roleOverviewVideoCount.textContent = hasRole ? String(state.videos.length) : "-";
        }
        if (roleOverviewLatestUpload) {
            const latestUpload = hasRole && state.videos.length
                ? state.videos
                    .map((video) => video.uploaded_at)
                    .filter(Boolean)
                    .map((value) => ({ value, time: new Date(value).getTime() }))
                    .filter((item) => Number.isFinite(item.time))
                    .reduce((latest, item) => (latest && latest.time > item.time ? latest : item), null)?.value || null
                : null;
            roleOverviewLatestUpload.textContent = hasRole ? formatDisplayTime(latestUpload) : "-";
        }
        if (roleOverviewTaskStatus) {
            if (!hasRole) {
                roleOverviewTaskStatus.textContent = "-";
            } else if (hasActiveTask()) {
                roleOverviewTaskStatus.textContent = "进行中";
            } else {
                roleOverviewTaskStatus.textContent = "空闲";
            }
        }
    }

    function resetWorkbenchContext() {
        clearAsrPolling();
        clearTaskPolling();
        clearSmartClipPolling();
        state.selectedRole = null;
        state.selectedVideo = null;
        state.selectedRemixVideo = null;
        state.selectedRemixPreviewId = null;
        state.smartClipProject = null;
        state.smartClipCandidates = [];
        state.preprocessJob = null;
        state.preprocessSegments = [];
        state.preprocessJobs = [];
        state.asrRecords = [];
        state.remixTasks = [];
        state.lipSyncVideos = [];
        state.selectedLipSyncVideo = null;
        state.lipSyncProject = null;
        state.lipSyncCandidates = [];
        state.selectedLipSyncScriptId = null;
        state.lipSyncGeneratingScripts = false;
        state.lipSyncScriptGenerationMessage = "";
        state.lipSyncRegeneratingCandidateId = null;
        state.lipSyncSubmittingTask = false;
        state.lipSyncSubmitStatus = "";
        state.lipSyncSubmitMessage = "";
        state.lipSyncProductDocs = [];
        state.selectedLipSyncProductDocId = null;
        state.lipSyncTasks = [];
        state.finalVideos = [];
        state.finalVideoQuery = "";
        state.finalVideoSourceType = "all";
        state.finalVideoSelectedIds = new Set();
        state.finalVideoDeleting = false;
        state.activeTaskTab = "preprocess";
        state.taskPagination = {
            preprocess: 1,
            remix: 1,
            "lip-sync": 1,
        };
        state.taskRecordSelectedIds = {
            preprocess: new Set(),
            remix: new Set(),
            "lip-sync": new Set(),
        };
        state.taskRecordDeleting = false;
        setUploadState({ active: false, progress: 0, message: "等待上传" });
        if (selectedRoleName) {
            selectedRoleName.textContent = "角色功能选择页";
        }
        if (videoManagerRoleName) {
            videoManagerRoleName.textContent = "视频管理";
        }
        if (videoPreviewContainer) {
            videoPreviewContainer.innerHTML = "<p>选择视频后可在这里预览。</p>";
        }
        if (asrStatusPanel) {
            asrStatusPanel.innerHTML = "<p>上传视频后可查看语音转文字处理状态。</p>";
        }
        if (asrSummaryPanel) {
            asrSummaryPanel.textContent = "暂无语音转文字总结";
        }
        if (remixVideoPreview) {
            remixVideoPreview.innerHTML = "<p>视频预览已移至卡片，点击左侧视频卡片即可直接预览。</p>";
        }
        if (smartClipProjectTitle) {
            smartClipProjectTitle.textContent = "原视频信息";
        }
        if (smartClipProjectStatus) {
            smartClipProjectStatus.textContent = "请选择或创建一个智能切片项目。";
        }
        if (smartClipProjectStage) {
            smartClipProjectStage.textContent = "待处理";
            smartClipProjectStage.className = "status-chip status-running";
        }
        if (smartClipSourceSummary) {
            smartClipSourceSummary.innerHTML = "<p>项目创建后，这里会展示原视频名称、时长、语音转文字状态和来源归属。</p>";
        }
        if (smartClipProgressText) {
            smartClipProgressText.textContent = "等待智能切片开始。";
        }
        if (smartClipProgressCounts) {
            smartClipProgressCounts.textContent = "0 / 0";
        }
        if (smartClipProgressSummary) {
            smartClipProgressSummary.textContent = "分析完成后会在下方展示候选切片列表。";
        }
        if (smartClipProgressBar) {
            smartClipProgressBar.style.width = "0%";
        }
        if (smartClipCandidateList) {
            smartClipCandidateList.innerHTML = "<p>候选切片生成后，这里会按时间顺序展示所有片段。</p>";
        }
        if (smartClipExportBtn) {
            smartClipExportBtn.disabled = true;
            smartClipExportBtn.textContent = "导出保留切片";
        }
        if (selectedRemixVideoSummary) {
            selectedRemixVideoSummary.innerHTML = `
                <h3>已选视频信息</h3>
                <p>选择长视频后，这里展示视频名称、时长和预处理状态。</p>
            `;
        }
        if (lipSyncScriptPreview) {
            lipSyncScriptPreview.innerHTML = "<p>请选择基础视频。</p>";
        }
        if (lipSyncCandidateList) {
            lipSyncCandidateList.innerHTML = "<p>点击“生成 3-5 版文案”后在这里展示候选文案。</p>";
        }
        if (lipSyncGenerationStatus) {
            lipSyncGenerationStatus.hidden = true;
            lipSyncGenerationStatus.textContent = "正在生成文案，请稍后";
        }
        if (lipSyncProductDocList) {
            lipSyncProductDocList.innerHTML = `
                <div class="section-head compact-head">
                    <div>
                        <h3>当前角色商品文档</h3>
                        <p class="hint-text">上传后可在当前角色内复用。</p>
                    </div>
                </div>
                <div class="candidate-list">
                    <p>当前还没有已保存的商品文档。</p>
                </div>
            `;
        }
        if (lipSyncConfirmSummary) {
            lipSyncConfirmSummary.innerHTML = `
                <h3>确认信息</h3>
                <p>这里展示当前角色、基础视频、已选文案。</p>
            `;
        }
        if (finalVideoSearchInput) {
            finalVideoSearchInput.value = "";
        }
        if (finalVideoSourceTypeFilter) {
            finalVideoSourceTypeFilter.value = "all";
        }
        if (finalVideoCount) {
            finalVideoCount.textContent = "0 条结果";
        }
        if (finalVideoList) {
            finalVideoList.innerHTML = '<div class="final-video-empty"><p>当前角色暂无成功生成的视频。</p></div>';
        }
        resetLipSyncSubmitStatus();
        syncWorkbenchNav();
        syncTaskTab();
        renderTaskLists();
    }

    function isWorkbenchRoute(route) {
        return workbenchRoutes.has(route);
    }

    function normalizeRoute(route) {
        if (!routeMap[route]) {
            return "lobby";
        }
        if (isWorkbenchRoute(route) && !state.selectedRole) {
            return "lobby";
        }
        return route;
    }

    function setRoute(route, options) {
        const nextRoute = normalizeRoute(route);
        if (nextRoute !== "smart-clip-project") {
            clearSmartClipPolling();
        }
        state.route = nextRoute;
        Object.entries(views).forEach(([key, node]) => {
            if (node) {
                node.classList.toggle("active", key === nextRoute);
            }
        });
        syncNav(nextRoute);
        syncWorkbenchNav();
        if (!options || options.push !== false) {
            window.history.pushState({ route: nextRoute }, "", routeMap[nextRoute] || "/");
        }
    }

    function applyPathRoute() {
        const route = reverseRouteMap[window.location.pathname] || "lobby";
        const nextRoute = normalizeRoute(route);
        setRoute(nextRoute, { push: false });
        if (nextRoute === "tasks") {
            loadTaskProgress().catch(console.error);
        }
        if (nextRoute === "smart-clip-project" && state.smartClipProject?.project?.id) {
            loadSmartClipProject(state.smartClipProject.project.id).catch(console.error);
        }
        if (nextRoute === "review") {
            loadFinalVideos().catch(console.error);
        }
    }

    function extractErrorMessage(payload, fallback) {
        if (!payload || typeof payload !== "object") return fallback;
        if (typeof payload.detail === "string" && payload.detail) return payload.detail;
        if (payload.error && typeof payload.error.message === "string" && payload.error.message) {
            return payload.error.message;
        }
        if (typeof payload.error === "string" && payload.error) return payload.error;
        return fallback;
    }

    async function request(url, options) {
        const response = await fetch(url, options);
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
            const message = extractErrorMessage(payload, "请求失败");
            throw new Error(message);
        }
        return payload;
    }

    function asrStatusLabel(status) {
        if (status === "success") return "语音转文字完成";
        if (status === "failed") return "语音转文字失败";
        if (status === "running") return "语音转文字处理中";
        return "等待语音转文字";
    }

    function jobStatusLabel(status) {
        const mapping = {
            starting: "启动中",
            pending: "等待中",
            queued: "排队中",
            running: "处理中",
            success: "已完成",
            failed: "失败",
            cancelled: "已取消",
            pending_preprocess: "等待预处理",
            preprocessing: "预处理中",
            ready: "待生成",
            partial_success: "部分成功",
            rewriting: "改写中",
            tts_generating: "TTS 生成中",
            video_generating: "视频生成中",
            script_generated: "文案已生成",
            script_selected: "已选择文案",
            submitted: "已提交生成",
        };
        return mapping[status] || status;
    }

    function lipSyncSubmitMessageForStatus(status) {
        if (status === "queued") {
            return "对口型任务已进入队列，前面有任务正在生成。";
        }
        if (status === "starting" || status === "video_generating") {
            return "对口型任务已开始生成，可前往任务进度页查看状态。";
        }
        return "对口型任务已提交，可前往任务进度页查看状态。";
    }

    function smartClipStageLabel(stage) {
        const mapping = {
            classifying: "带货识别中",
            building_candidates: "候选切片生成中",
            generating_previews: "预览片生成中",
            ready: "候选已生成",
            exporting: "视频导出中",
            exported: "导出完成",
            failed: "处理失败",
        };
        return mapping[stage] || mapping[String(stage || "")] || "待处理";
    }

    function smartClipProgressMeta(project) {
        const exportTotal = Number(project?.export_total_count || 0);
        const exportCurrent = Number(project?.export_current_index || 0);
        const exportCompleted = Number(project?.export_completed_count || 0);
        const candidateCount = Number(project?.candidate_clip_count || 0);
        const stage = String(project?.stage || "");
        const status = String(project?.status || "");
        if (stage === "generating_previews") {
            const total = Math.max(exportTotal || candidateCount || 1, 1);
            const current = Math.min(Math.max(exportCurrent, 0), total);
            return {
                current,
                total,
                percent: Math.max(0, Math.min(100, (current / total) * 100)),
                summary: `共 ${exportTotal || candidateCount} 个候选切片，已生成 ${exportCompleted} 个预览片`,
            };
        }
        if (status === "exporting" || stage === "exporting") {
            const total = Math.max(exportTotal, 1);
            const current = Math.min(Math.max(exportCurrent, 0), total);
            return {
                current,
                total,
                percent: Math.max(0, Math.min(100, (current / total) * 100)),
                summary: `共 ${exportTotal} 个候选切片，已完成 ${exportCompleted} 个`,
            };
        }
        if (status === "success" || stage === "exported") {
            const total = Math.max(exportTotal || candidateCount || 1, 1);
            const current = exportCompleted || exportTotal || candidateCount;
            return {
                current,
                total,
                percent: 100,
                summary: `已导出 ${current} 个切片视频`,
            };
        }
        if (status === "ready" || stage === "ready") {
            const total = Math.max(candidateCount, 1);
            return {
                current: candidateCount,
                total,
                percent: 100,
                summary: `已生成 ${candidateCount} 个候选切片，预览片已全部就绪`,
            };
        }
        if (status === "failed" || stage === "failed") {
            const total = Math.max(exportTotal || candidateCount || 1, 1);
            return {
                current: exportCompleted,
                total,
                percent: 100,
                summary: project?.error_message || "智能切片失败",
            };
        }
        const totalAsr = Math.max(Number(project?.total_asr_segments || 0), 1);
        const keptSales = Number(project?.kept_sales_segments || 0);
        return {
            current: keptSales,
            total: totalAsr,
            percent: Math.max(8, Math.min(92, (keptSales / totalAsr) * 100)),
            summary: `已识别 ${keptSales} 段带货口播，正在生成候选切片`,
        };
    }

    function statusClass(status) {
        if (status === "success" || status === "partial_success") return "status-success";
        if (status === "failed" || status === "cancelled") return "status-failed";
        return "status-running";
    }

    function asrDetailMessage(status) {
        if (status === "success") return "语音转文字已完成，结果已写入视频详情。";
        if (status === "failed") return "语音转文字失败，请查看错误信息并重新上传。";
        if (status === "running") return "语音转文字处理中，完成后会自动刷新状态。";
        return "视频已上传，正在等待语音转文字处理。";
    }

    function renderUploadProgress() {
        const { active, progress, message } = state.uploadState;
        uploadProgressPanel.hidden = !active && progress <= 0 && message === "等待上传";
        uploadProgressText.textContent = message;
        uploadProgressPercent.textContent = `${Math.max(0, Math.min(100, Math.round(progress || 0)))}%`;
        uploadProgressBar.style.width = `${Math.max(0, Math.min(100, progress || 0))}%`;
        videoUploadInput.disabled = active;
    }

    function setUploadState(nextState) {
        state.uploadState = { ...state.uploadState, ...nextState };
        renderUploadProgress();
    }

    function clearAsrPolling() {
        if (state.asrPollingTimer) {
            window.clearTimeout(state.asrPollingTimer);
            state.asrPollingTimer = null;
        }
    }

    function clearTaskPolling() {
        if (state.taskPollingTimer) {
            window.clearTimeout(state.taskPollingTimer);
            state.taskPollingTimer = null;
        }
    }

    function clearSmartClipPolling() {
        if (state.smartClipPollingTimer) {
            window.clearTimeout(state.smartClipPollingTimer);
            state.smartClipPollingTimer = null;
        }
    }

    async function pollAsrStatus(videoId) {
        clearAsrPolling();
        if (!videoId) return;
        try {
            const payload = await request(`/api/videos/${videoId}/asr`);
            asrStatusPanel.innerHTML = `
                <p><strong>当前状态：</strong>${asrStatusLabel(payload.status)}</p>
                <p><strong>阶段说明：</strong>${asrDetailMessage(payload.status)}</p>
                <p><strong>错误信息：</strong>${payload.error_message || "无"}</p>
            `;
            const summarySource = payload.summary_source || payload.summary_status || "pending";
            if (summarySource === "success") {
                asrSummaryPanel.textContent = payload.summary || "正在整理视频内容总结";
            } else if (payload.status === "failed") {
                asrSummaryPanel.textContent = "视频语音转文字失败，暂无总结。";
            } else if (summarySource === "failed") {
                asrSummaryPanel.textContent = "视频语音已识别完成，总结暂不可用，请稍后重试";
            } else {
                asrSummaryPanel.textContent = payload.status === "success"
                    ? "正在整理视频内容总结"
                    : "上传视频后可查看语音转文字总结。";
            }
            if (payload.status === "pending" || payload.status === "running") {
                state.asrPollingTimer = window.setTimeout(() => {
                    pollAsrStatus(videoId).catch(console.error);
                }, 3000);
            }
        } catch (error) {
            asrStatusPanel.innerHTML = `
                <p><strong>当前状态：</strong>语音转文字失败</p>
                <p><strong>阶段说明：</strong>查询语音转文字状态失败，请稍后刷新重试。</p>
                <p><strong>错误信息：</strong>${error.message}</p>
            `;
        }
    }

    function groupVideos(videos) {
        const now = Date.now();
        const buckets = { pinned: [], recent: [], week: [], old: [] };
        videos.forEach((video) => {
            if (video.is_pinned) {
                buckets.pinned.push(video);
                return;
            }
            const uploadedAt = new Date(video.uploaded_at).getTime();
            const diff = now - uploadedAt;
            if (diff <= 3 * 24 * 60 * 60 * 1000) {
                buckets.recent.push(video);
            } else if (diff <= 7 * 24 * 60 * 60 * 1000) {
                buckets.week.push(video);
            } else {
                buckets.old.push(video);
            }
        });
        return buckets;
    }

    function applyStaggerDelay(node, index, step = 0.05, cap = 0.24) {
        if (!node) return;
        node.style.setProperty("--enter-delay", `${Math.min(index * step, cap)}s`);
    }

    function appendTextElement(parent, tagName, text, className) {
        const node = document.createElement(tagName);
        if (className) {
            node.className = className;
        }
        node.textContent = text;
        parent.appendChild(node);
        return node;
    }

    function createRoleCoverNode(role) {
        const cover = document.createElement("div");
        cover.className = "role-card-cover";
        const imageUrl = String(role.avatar_url || "").trim();
        if (imageUrl) {
            const image = document.createElement("img");
            image.className = "role-card-cover-image";
            image.src = imageUrl;
            image.alt = `${role.name || "角色"}封面`;
            image.loading = "lazy";
            cover.appendChild(image);
            return cover;
        }

        const placeholder = document.createElement("div");
        placeholder.className = "role-card-cover-placeholder";
        placeholder.textContent = "暂无封面";
        cover.appendChild(placeholder);
        return cover;
    }

    function openRoleCoverUpload(roleId) {
        if (!roleCoverUploadInput || !roleId) return;
        pendingRoleCoverUploadId = roleId;
        roleCoverUploadInput.dataset.roleId = roleId;
        roleCoverUploadInput.value = "";
        roleCoverUploadInput.click();
    }

    async function submitRoleCoverUpload(roleId, file) {
        const formData = new FormData();
        formData.append("cover", file);
        const updatedRole = await request(`/api/roles/${roleId}/cover`, {
            method: "POST",
            body: formData,
        });
        await loadRoles(globalRoleSearch?.value.trim());
        if (state.selectedRole && state.selectedRole.id === roleId) {
            state.selectedRole = updatedRole;
            if (selectedRoleName) {
                selectedRoleName.textContent = updatedRole.name || "角色功能选择页";
            }
            if (videoManagerRoleName) {
                videoManagerRoleName.textContent = `${updatedRole.name || "视频管理"}的视频管理`;
            }
            syncWorkbenchNav();
        }
    }

    async function confirmDeleteRole(roleId) {
        if (!roleId) return;
        const role = state.roles.find((item) => item.id === roleId) || null;
        const roleName = role?.name || "该角色";
        const confirmed = window.confirm(
            `确认永久删除“${roleName}”吗？\n删除角色后将一并删除该角色下的上传视频、生成视频、任务记录及相关文件，且不可恢复。`
        );
        if (!confirmed) return;
        await request(`/api/roles/${roleId}`, { method: "DELETE" });
        if (state.selectedRole?.id === roleId) {
            resetWorkbenchContext();
            syncWorkbenchNav();
            setRoute("lobby");
        }
        await loadRoles(globalRoleSearch?.value.trim());
    }

    function renderRoles() {
        roleGrid.innerHTML = "";
        if (!state.roles.length) {
            const emptyCard = document.createElement("article");
            emptyCard.className = "panel role-card";
            appendTextElement(emptyCard, "h3", "还没有角色");
            appendTextElement(emptyCard, "p", "从“新建角色”开始。");
            roleGrid.appendChild(emptyCard);
            return;
        }
        state.roles.forEach((role, index) => {
            const card = document.createElement("article");
            card.className = "panel role-card";
            applyStaggerDelay(card, index, 0.05, 0.2);
            const tags = Array.isArray(role.tags)
                ? role.tags
                : String(role.tags || "")
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean);
            const updatedAt = role.updated_at ? new Date(role.updated_at).toLocaleString() : "暂无";

            card.appendChild(createRoleCoverNode(role));
            const content = document.createElement("div");
            content.className = "role-card-content";
            appendTextElement(content, "span", "角色", "eyebrow");
            appendTextElement(content, "h3", role.name || "未命名角色");
            appendTextElement(content, "p", role.description || "暂无描述", "role-card-description");
            const meta = document.createElement("div");
            meta.className = "role-card-meta";
            appendTextElement(meta, "p", `标签：${tags.join(" / ") || "未设置"}`);
            appendTextElement(meta, "p", `视频数量：${role.video_count || 0}`);
            appendTextElement(meta, "p", `待审核数量：${role.pending_review_count || 0}`);
            appendTextElement(meta, "p", `最近更新时间：${updatedAt}`);
            content.appendChild(meta);
            card.appendChild(content);

            const actions = document.createElement("div");
            actions.className = "role-card-actions";
            const coverButton = document.createElement("button");
            coverButton.className = "ghost-btn";
            coverButton.type = "button";
            coverButton.dataset.roleCoverUpload = role.id || "";
            coverButton.textContent = "更换封面";
            actions.appendChild(coverButton);
            const enterButton = document.createElement("button");
            enterButton.className = "primary-btn";
            enterButton.type = "button";
            enterButton.dataset.roleEnter = role.id || "";
            enterButton.textContent = "进入角色";
            actions.appendChild(enterButton);
            const deleteButton = document.createElement("button");
            deleteButton.className = "danger-btn";
            deleteButton.type = "button";
            deleteButton.dataset.roleDelete = role.id || "";
            deleteButton.textContent = "删除角色";
            actions.appendChild(deleteButton);
            card.appendChild(actions);
            roleGrid.appendChild(card);
        });
    }

    function renderVideoGroups() {
        const groups = groupVideos(state.videos);
        Object.entries(groups).forEach(([key, videos]) => {
            const node = document.getElementById(`group-${key}`);
            node.innerHTML = "";
            if (!videos.length) {
                node.innerHTML = "<p>暂无视频</p>";
                return;
            }
            videos.forEach((video, index) => {
                const card = document.createElement("article");
                card.className = "panel video-card";
                applyStaggerDelay(card, index, 0.04, 0.16);
                card.innerHTML = `
                    <h4>${video.title}</h4>
                    <p>时长：${Number(video.duration_sec || 0).toFixed(1)} 秒</p>
                    <p>上传时间：${new Date(video.uploaded_at).toLocaleString()}</p>
                    <span class="status-chip ${statusClass(video.asr_status)}">${asrStatusLabel(video.asr_status)}</span>
                    <div class="video-actions">
                        <button class="ghost-btn" type="button" data-preview-video="${video.id}">预览</button>
                        <button class="ghost-btn" type="button" data-pin-video="${video.id}">
                            ${video.is_pinned ? "取消置顶" : "置顶"}
                        </button>
                        <button class="ghost-btn" type="button" data-delete-video="${video.id}">删除</button>
                        <button class="ghost-btn" type="button" data-refresh-asr="${video.id}">查看语音转文字</button>
                    </div>
                `;
                node.appendChild(card);
            });
        });
        renderRoleOverview();
    }

    function renderRemixVideoList() {
        remixVideoList.innerHTML = "";
        if (!state.remixVideos.length) {
            remixVideoList.innerHTML = "<p>当前角色还没有可用于混剪的视频。</p>";
            return;
        }
        state.remixVideos.forEach((video) => {
            const card = document.createElement("article");
            card.className = "panel video-card";
            card.innerHTML = `
                <div class="video-card-media">
                    <video class="media-preview-small" controls preload="metadata" src="/api/videos/${video.id}/stream"></video>
                </div>
                <div class="video-card-body">
                    <h4>${video.title}</h4>
                    <p>时长：${Number(video.duration_sec || 0).toFixed(1)} 秒</p>
                    <p>上传时间：${new Date(video.uploaded_at).toLocaleString()}</p>
                    <span class="status-chip ${statusClass(video.asr_status)}">${asrStatusLabel(video.asr_status)}</span>
                    <div class="video-actions">
                        <button class="ghost-btn" type="button" data-remix-select="${video.id}">混剪生成视频</button>
                        <button class="ghost-btn" type="button" data-smart-clip-start="${video.id}">智能切片</button>
                    </div>
                </div>
            `;
            remixVideoList.appendChild(card);
        });
    }
    
    function renderLipSyncVideoList() {
        lipSyncVideoList.innerHTML = "";
        if (!state.lipSyncVideos.length) {
            lipSyncVideoList.innerHTML = "<p>当前角色还没有可用于对口型生成的视频。</p>";
            return;
        }
        state.lipSyncVideos.forEach((video) => {
            const disabled = !video.selectable;
            const card = document.createElement("article");
            card.className = `panel video-card ${disabled ? "video-card-disabled" : ""}`;
            card.innerHTML = `
                <div class="video-card-media">
                    <video class="media-preview-small" controls preload="metadata" src="/api/videos/${video.id}/stream"></video>
                </div>
                <div class="video-card-body">
                    <h4>${video.title}</h4>
                    <p>时长：${Number(video.duration_sec || 0).toFixed(1)} 秒</p>
                    <p>上传时间：${new Date(video.uploaded_at).toLocaleString()}</p>
                    <span class="status-chip ${disabled ? "status-failed" : "status-success"}">${disabled ? "超时长不可选" : "可用基础视频"}</span>
                    <div class="video-actions">
                        <button class="${disabled ? "ghost-btn" : "primary-btn"}" type="button" data-lip-sync-select="${video.id}" ${disabled ? "disabled" : ""}>${disabled ? "该视频超过30秒，无法用于对口型生成。" : "进入对口型生成"}</button>
                    </div>
                </div>
            `;
            lipSyncVideoList.appendChild(card);
        });
    }

    function renderLipSyncScriptPreview() {
        if (!state.selectedLipSyncVideo) {
            lipSyncScriptPreview.innerHTML = "<p>请选择基础视频。</p>";
            return;
        }
        lipSyncScriptPreview.innerHTML = `
            <video class="media-preview-small" controls src="/api/videos/${state.selectedLipSyncVideo.id}/stream"></video>
            <p>${state.selectedLipSyncVideo.title}</p>
            <p>时长：${Number(state.selectedLipSyncVideo.duration_sec || 0).toFixed(1)} 秒</p>
        `;
    }

    function renderLipSyncCandidateList() {
        if (!state.lipSyncCandidates.length) {
            lipSyncCandidateList.innerHTML = "<p>点击“生成 3-5 版文案”后在这里展示候选文案。</p>";
            return;
        }
        lipSyncCandidateList.innerHTML = "";
        state.lipSyncCandidates.forEach((candidate) => {
            const item = document.createElement("article");
            item.className = `panel candidate-item ${state.selectedLipSyncScriptId === candidate.id ? "candidate-selected" : ""}`;
            const draftText = candidate.edited_content || candidate.content || "";
            const isRegenerating = state.lipSyncRegeneratingCandidateId === candidate.id;
            item.innerHTML = `
                <div class="candidate-meta-row candidate-meta-values">
                    <span>文案正文</span>
                    <span>字数：${candidate.char_count}</span>
                    <span>预估 TTS 时长：${Number(candidate.estimated_tts_duration_sec || 0).toFixed(1)} 秒</span>
                </div>
                <textarea class="candidate-editor" data-candidate-edit="${candidate.id}">${draftText}</textarea>
                <div class="video-actions">
                    <button class="primary-btn" type="button" data-candidate-select="${candidate.id}">选中</button>
                    <button class="ghost-btn" type="button" data-candidate-regenerate="${candidate.id}" ${isRegenerating ? "disabled" : ""}>${isRegenerating ? "正在生成，请稍后" : "再生成类似一版"}</button>
                </div>
            `;
            lipSyncCandidateList.appendChild(item);
        });
    }

    function renderLipSyncGenerationStatus() {
        if (!lipSyncGenerationStatus) return;
        const visible = state.lipSyncGeneratingScripts || Boolean(state.lipSyncScriptGenerationMessage);
        lipSyncGenerationStatus.hidden = !visible;
        lipSyncGenerationStatus.classList.toggle("loading-text", state.lipSyncGeneratingScripts);
        lipSyncGenerationStatus.textContent = state.lipSyncScriptGenerationMessage || "正在生成文案，请稍后";
        const button = document.getElementById("generate-lip-sync-scripts-btn");
        if (button) {
            button.disabled = state.lipSyncGeneratingScripts;
            button.textContent = state.lipSyncGeneratingScripts ? "正在生成文案，请稍后" : "生成 3-5 版文案";
        }
    }

    function renderLipSyncProductDocList() {
        if (!lipSyncProductDocList) return;
        if (!state.lipSyncProductDocs.length) {
            lipSyncProductDocList.innerHTML = `
                <div class="section-head compact-head">
                    <div>
                        <h3>当前角色商品文档</h3>
                        <p class="hint-text">上传后可在当前角色内复用。</p>
                    </div>
                </div>
                <div class="candidate-list">
                    <p>当前还没有已保存的商品文档。</p>
                </div>
            `;
            return;
        }
        lipSyncProductDocList.innerHTML = `
            <div class="section-head compact-head">
                <div>
                    <h3>当前角色商品文档</h3>
                    <p class="hint-text">上传后可在当前角色内复用。</p>
                </div>
            </div>
        `;
        const container = document.createElement("div");
        container.className = "candidate-list";
        state.lipSyncProductDocs.forEach((doc) => {
            const item = document.createElement("article");
            item.className = `panel candidate-item ${state.selectedLipSyncProductDocId === doc.id ? "candidate-selected" : ""}`;
            item.innerHTML = `
                <div class="candidate-meta-row candidate-meta-values">
                    <span>${doc.name}</span>
                    <span>创建时间：${new Date(doc.created_at).toLocaleString()}</span>
                    <span>类型：TXT</span>
                </div>
                <div class="video-actions">
                    <button class="primary-btn" type="button" data-product-doc-select="${doc.id}">使用该文档</button>
                </div>
            `;
            container.appendChild(item);
        });
        lipSyncProductDocList.appendChild(container);
    }

    function renderLipSyncConfirmSummary() {
        const selectedCandidate = state.lipSyncCandidates.find((item) => item.id === state.selectedLipSyncScriptId);
        const finalText = selectedCandidate ? (selectedCandidate.edited_content || selectedCandidate.content || "") : "尚未选择文案";
        lipSyncConfirmSummary.innerHTML = `
            <h3>确认信息</h3>
            <p>角色：${state.selectedRole ? state.selectedRole.name : "-"}</p>
            <p>基础视频：${state.selectedLipSyncVideo ? state.selectedLipSyncVideo.title : "-"}</p>
            <p>已选文案：${finalText}</p>
        `;
    }

    function renderLipSyncSubmitStatus() {
        if (!lipSyncSubmitStatus || !submitLipSyncTaskButton) return;
        const visible = state.lipSyncSubmittingTask || Boolean(state.lipSyncSubmitMessage);
        lipSyncSubmitStatus.hidden = !visible;
        lipSyncSubmitStatus.textContent = state.lipSyncSubmitMessage || "正在提交任务，请稍后";
        lipSyncSubmitStatus.classList.toggle("loading-text", state.lipSyncSubmittingTask);
        lipSyncSubmitStatus.classList.toggle("status-feedback-success", !state.lipSyncSubmittingTask && state.lipSyncSubmitStatus === "success");
        lipSyncSubmitStatus.classList.toggle("status-feedback-error", !state.lipSyncSubmittingTask && state.lipSyncSubmitStatus === "error");
        submitLipSyncTaskButton.disabled = state.lipSyncSubmittingTask;
        submitLipSyncTaskButton.textContent = state.lipSyncSubmittingTask ? "正在提交任务，请稍后" : "提交对口型任务";
    }

    function sourceTypeLabel(sourceType) {
        if (sourceType === "remix") return "混合剪辑";
        if (sourceType === "smart_clip") return "智能切片";
        if (sourceType === "lip_sync") return "对口型";
        return sourceType || "未知类型";
    }

    function truncateText(text, limit = 72) {
        const raw = String(text || "").trim();
        if (!raw) return "暂无文案摘要";
        return raw.length > limit ? `${raw.slice(0, limit)}...` : raw;
    }

    function isTaskRecordDeletable(tab, item) {
        if (tab === "preprocess") {
            return ["success", "failed", "cancelled"].includes(item.status);
        }
        if (tab === "remix") {
            if (item.task_type === "smart_clip") {
                return false;
            }
            return ["success", "partial_success", "failed", "cancelled"].includes(item.status);
        }
        if (tab === "lip-sync") {
            return ["success", "failed", "cancelled"].includes(item.status);
        }
        return false;
    }

    function getTaskSelectionSet(tab) {
        return state.taskRecordSelectedIds[tab] || new Set();
    }

    function getTaskSortTime(value) {
        const time = new Date(value || "").getTime();
        return Number.isFinite(time) ? time : 0;
    }

    function buildPreprocessTaskItems() {
        const asrItems = state.asrRecords.map((record) => ({
            kind: "asr",
            id: record.video_id,
            sort_time: getTaskSortTime(record.uploaded_at),
            selectable: false,
            role_name: record.role_name || "-",
            video_title: record.video_title || "-",
            asr_status: record.asr_status || "pending",
            asr_error_message: record.asr_error_message || "",
        }));
        const preprocessItems = state.preprocessJobs.map((job) => ({
            kind: "preprocess",
            ...job,
            sort_time: getTaskSortTime(job.started_at || job.created_at),
            selectable: isTaskRecordDeletable("preprocess", job),
        }));
        return [...asrItems, ...preprocessItems].sort((left, right) => right.sort_time - left.sort_time);
    }

    function getTaskItemsForTab(tab) {
        if (tab === "preprocess") {
            return buildPreprocessTaskItems();
        }
        if (tab === "remix") {
            return state.remixTasks
                .map((task) => ({
                    kind: "remix",
                    ...task,
                    sort_time: getTaskSortTime(task.created_at),
                    selectable: task.task_type === "smart_clip" ? false : isTaskRecordDeletable("remix", task),
                }))
                .sort((left, right) => right.sort_time - left.sort_time);
        }
        if (tab === "lip-sync") {
            return state.lipSyncTasks
                .map((task) => ({
                    kind: "lip-sync",
                    ...task,
                    sort_time: getTaskSortTime(task.created_at),
                    selectable: isTaskRecordDeletable("lip-sync", task),
                }))
                .sort((left, right) => right.sort_time - left.sort_time);
        }
        return [];
    }

    function getTaskPageMeta(tab) {
        const items = getTaskItemsForTab(tab);
        const totalPages = Math.max(1, Math.ceil(items.length / TASK_PAGE_SIZE));
        const currentPage = Math.min(Math.max(Number(state.taskPagination[tab] || 1), 1), totalPages);
        state.taskPagination[tab] = currentPage;
        const startIndex = (currentPage - 1) * TASK_PAGE_SIZE;
        return {
            items,
            page: currentPage,
            totalPages,
            pageItems: items.slice(startIndex, startIndex + TASK_PAGE_SIZE),
        };
    }

    function getTaskPageSelectableIds(tab) {
        return getTaskPageMeta(tab).pageItems.filter((item) => item.selectable).map((item) => item.id);
    }

    function renderTaskHeader() {
        return `
            <div class="task-row task-row-head">
                <span>任务 ID</span>
                <span>角色</span>
                <span>视频 / 片段</span>
                <span>类型</span>
                <span>当前状态</span>
                <span>操作</span>
            </div>
        `;
    }

    function renderEmptyRow(message) {
        return `
            <div class="task-row">
                <span>${message || "暂无任务"}</span>
                <span>-</span>
                <span>-</span>
                <span>-</span>
                <span>-</span>
                <span>-</span>
            </div>
        `;
    }

    function renderTaskRow(item, tab) {
        if (tab === "preprocess" && item.kind === "asr") {
            return `
                <div class="task-row">
                    <span>${shortId(item.id)}</span>
                    <span>${item.role_name || "-"}</span>
                    <span>${item.video_title || "-"}</span>
                    <span>语音转文字</span>
                    <span><span class="status-chip ${statusClass(item.asr_status)}">${asrStatusLabel(item.asr_status)}</span></span>
                    <span class="task-cell-note">${item.asr_error_message || "后台自动处理，无需额外操作"}</span>
                </div>
            `;
        }
        if (tab === "preprocess" && item.kind === "preprocess") {
            const selected = state.taskRecordSelectedIds.preprocess.has(item.id);
            const actionButtons = [];
            if (["pending", "running"].includes(item.status)) {
                actionButtons.push(`<button class="ghost-btn" type="button" data-cancel-preprocess="${item.id}">取消</button>`);
            }
            if (isTaskRecordDeletable("preprocess", item)) {
                actionButtons.push(`<button class="ghost-btn danger-ghost" type="button" data-delete-task-type="preprocess" data-delete-task-id="${item.id}">删除</button>`);
            }
            return `
                <div class="task-row">
                    <span>
                        ${item.selectable ? `<input class="task-select-checkbox" type="checkbox" data-task-select-type="preprocess" data-task-select-id="${item.id}" ${selected ? "checked" : ""} />` : ""}
                        ${shortId(item.id)}
                    </span>
                    <span>${item.role_name || "-"}</span>
                    <span>${item.video_title || shortId(item.role_video_id)}</span>
                    <span>预处理</span>
                    <span><span class="status-chip ${statusClass(item.status)}">${jobStatusLabel(item.status)}</span></span>
                    <span class="task-actions-cell">
                        ${actionButtons.join("") || `<span>${item.error_message || "不可删除"}</span>`}
                    </span>
                </div>
            `;
        }
        if (tab === "remix") {
            if (item.task_type === "smart_clip") {
                return `
                    <div class="task-row">
                        <span>${shortId(item.project_id || item.id)}</span>
                        <span>${item.role_name || "-"}</span>
                        <span>${item.source_video_title || item.video_title || shortId(item.source_video_id)}</span>
                        <span>智能切片</span>
                        <span><span class="status-chip ${statusClass(item.status)}">${smartClipStageLabel(item.stage || item.status)}</span></span>
                        <span class="task-actions-cell">
                            <button class="ghost-btn" type="button" data-open-smart-clip-project="${item.project_id || item.id}">详情</button>
                            <span class="task-cell-note">${item.progress_summary || "等待处理"}</span>
                        </span>
                    </div>
                `;
            }
            const selected = state.taskRecordSelectedIds.remix.has(item.id);
            const actionButtons = [];
            if (!["success", "partial_success", "failed", "cancelled"].includes(item.status)) {
                actionButtons.push(`<button class="ghost-btn" type="button" data-cancel-remix-task="${item.id}">取消</button>`);
            }
            if (isTaskRecordDeletable("remix", item)) {
                actionButtons.push(`<button class="ghost-btn danger-ghost" type="button" data-delete-task-type="remix" data-delete-task-id="${item.id}">删除</button>`);
            }
            return `
                <div class="task-row">
                    <span>
                        ${item.selectable ? `<input class="task-select-checkbox" type="checkbox" data-task-select-type="remix" data-task-select-id="${item.id}" ${selected ? "checked" : ""} />` : ""}
                        ${shortId(item.id)}
                    </span>
                    <span>${item.role_name || "-"}</span>
                    <span>${item.video_title || shortId(item.source_video_id)}</span>
                    <span>混合剪辑</span>
                    <span><span class="status-chip ${statusClass(item.status)}">${jobStatusLabel(item.status)}</span></span>
                    <span class="task-actions-cell">
                        ${actionButtons.join("") || `<span>${item.error_message || "不可删除"}</span>`}
                    </span>
                </div>
            `;
        }
        if (tab === "lip-sync") {
            const selected = state.taskRecordSelectedIds["lip-sync"].has(item.id);
            const actionButtons = [`<button class="ghost-btn" type="button" data-open-lip-sync-task="${item.id}">详情</button>`];
            if (!["success", "failed", "cancelled"].includes(item.status)) {
                actionButtons.push(`<button class="ghost-btn" type="button" data-cancel-lip-sync-task="${item.id}">取消</button>`);
            }
            if (isTaskRecordDeletable("lip-sync", item)) {
                actionButtons.push(`<button class="ghost-btn danger-ghost" type="button" data-delete-task-type="lip-sync" data-delete-task-id="${item.id}">删除</button>`);
            }
            return `
                <div class="task-row">
                    <span>
                        ${item.selectable ? `<input class="task-select-checkbox" type="checkbox" data-task-select-type="lip-sync" data-task-select-id="${item.id}" ${selected ? "checked" : ""} />` : ""}
                        ${shortId(item.id)}
                    </span>
                    <span>${item.role_name || "-"}</span>
                    <span>${item.video_title || shortId(item.base_video_id)}</span>
                    <span>对口型生成</span>
                    <span><span class="status-chip ${statusClass(item.status)}">${jobStatusLabel(item.status)}</span></span>
                    <span class="task-actions-cell">
                        ${actionButtons.join("")}
                    </span>
                </div>
            `;
        }
        return "";
    }

    function renderFinalVideoBulkToolbar() {
        if (!finalVideoBulkToolbar || !finalVideoSelectedCount || !finalVideoSelectAllBtn || !finalVideoClearSelectionBtn || !finalVideoDeleteSelectedBtn) {
            return;
        }
        const selectedCount = state.finalVideoSelectedIds.size;
        finalVideoBulkToolbar.hidden = selectedCount === 0;
        finalVideoSelectedCount.textContent = String(selectedCount);
        finalVideoSelectAllBtn.textContent = selectedCount === state.finalVideos.length ? "取消全选" : "全选";
        finalVideoDeleteSelectedBtn.disabled = selectedCount === 0 || state.finalVideoDeleting;
        finalVideoDeleteSelectedBtn.textContent = state.finalVideoDeleting ? "正在删除..." : "删除选中";
        finalVideoClearSelectionBtn.disabled = selectedCount === 0 || state.finalVideoDeleting;
        finalVideoSelectAllBtn.disabled = state.finalVideoDeleting || state.finalVideos.length === 0;
    }

    function renderTaskDeleteToolbar() {
        if (!taskDeleteToolbar || !taskSelectedCount || !taskSelectAllBtn || !taskClearSelectionBtn || !taskDeleteSelectedBtn) {
            return;
        }
        const tab = state.activeTaskTab;
        const selection = getTaskSelectionSet(tab);
        const visibleSelectableIds = getTaskPageSelectableIds(tab);
        const allVisibleSelected = visibleSelectableIds.length > 0 && visibleSelectableIds.every((id) => selection.has(id));
        const selectedCount = selection.size;
        taskDeleteToolbar.hidden = selectedCount === 0;
        taskSelectedCount.textContent = String(selectedCount);
        taskSelectAllBtn.textContent = allVisibleSelected ? "取消全选当前页" : "全选当前页";
        taskDeleteSelectedBtn.disabled = selectedCount === 0 || state.taskRecordDeleting;
        taskDeleteSelectedBtn.textContent = state.taskRecordDeleting ? "正在删除..." : "删除选中";
        taskClearSelectionBtn.disabled = selectedCount === 0 || state.taskRecordDeleting;
        taskSelectAllBtn.disabled = state.taskRecordDeleting || visibleSelectableIds.length === 0;
    }

    function renderFinalVideoList() {
        if (!finalVideoList || !finalVideoCount) return;
        state.finalVideoSelectedIds = new Set(
            [...state.finalVideoSelectedIds].filter((id) => state.finalVideos.some((item) => item.id === id))
        );
        finalVideoCount.textContent = `${state.finalVideos.length} 条结果`;
        if (!state.finalVideos.length) {
            const message = state.finalVideoQuery
                ? "未找到匹配的原始视频名称"
                : "当前角色暂无成功生成的视频";
            finalVideoList.innerHTML = `<div class="final-video-empty"><p>${message}</p></div>`;
            renderFinalVideoBulkToolbar();
            return;
        }
        finalVideoList.innerHTML = "";
        state.finalVideos.forEach((item) => {
            const card = document.createElement("article");
            card.className = "panel final-video-card";
            const streamUrl = `/api/final-videos/${item.id}/stream?source_type=${encodeURIComponent(item.source_type)}`;
            const checked = state.finalVideoSelectedIds.has(item.id);
            card.innerHTML = `
                <div class="final-video-card-actions">
                    <label class="final-video-select">
                        <input type="checkbox" data-final-video-select="${item.id}" ${checked ? "checked" : ""} />
                        <span>选择</span>
                    </label>
                    <button class="ghost-btn danger-ghost" type="button" data-final-video-delete="${item.id}" data-final-video-source-type="${item.source_type}">删除</button>
                </div>
                <video class="media-preview-small" controls preload="metadata" src="${streamUrl}"></video>
                <span class="status-chip source-type-chip ${item.source_type === "remix" ? "status-running" : "status-success"}">${sourceTypeLabel(item.source_type)}</span>
                <div class="final-video-meta">
                    <p><strong>原始视频名称：</strong>${item.source_video_title || "-"}</p>
                    <p><strong>生成时间：</strong>${item.created_at ? new Date(item.created_at).toLocaleString() : "-"}</p>
                    <p><strong>生成类型：</strong>${sourceTypeLabel(item.source_type)}</p>
                </div>
                <p class="final-video-summary">${truncateText(item.summary_text)}</p>
            `;
            finalVideoList.appendChild(card);
        });
        renderFinalVideoBulkToolbar();
    }

    function resetLipSyncSubmitStatus() {
        state.lipSyncSubmittingTask = false;
        state.lipSyncSubmitStatus = "";
        state.lipSyncSubmitMessage = "";
        renderLipSyncSubmitStatus();
    }

    function renderSelectedRemixVideoSummary() {
        if (!state.selectedRemixVideo) {
            selectedRemixVideoSummary.innerHTML = `
                <h3>已选视频信息</h3>
                <p>选择长视频后，这里展示视频名称、时长和预处理状态。</p>
            `;
            return;
        }
        const job = state.preprocessJob;
        const statusText = job ? jobStatusLabel(job.status) : "待检查";
        const clipCount = state.preprocessSegments.length;
        selectedRemixVideoSummary.innerHTML = `
            <h3>${state.selectedRemixVideo.title}</h3>
            <p>时长：${Number(state.selectedRemixVideo.duration_sec || 0).toFixed(1)} 秒</p>
            <p>画面比例：${state.selectedRemixVideo.aspect_ratio || "未知"}</p>
            <p>预处理片段数：${clipCount}</p>
            <span class="status-chip ${job ? statusClass(job.status) : "status-running"}">${statusText}</span>
            <div class="video-actions">
                <button class="ghost-btn" type="button" id="summary-open-tasks-btn">查看任务页</button>
            </div>
        `;
        document.getElementById("summary-open-tasks-btn").addEventListener("click", async () => {
            setRoute("tasks");
            await loadTaskProgress();
        });
    }

    function renderSmartClipProject() {
        const project = state.smartClipProject;
        if (!project) {
            return;
        }
        const sourceVideo = project.source_video;
        const sourceVideoMeta = sourceVideo || {};
        const meta = smartClipProgressMeta(project.project);
        const stageClass = statusClass(project.project.status);
        smartClipProjectTitle.textContent = project.project.source_video_title || sourceVideoMeta.title || "智能切片项目";
        smartClipProjectStatus.textContent = meta.summary;
        smartClipProjectStage.textContent = smartClipStageLabel(project.project.stage);
        smartClipProjectStage.className = `status-chip ${stageClass}`;
        const nextMode = sourceVideo ? "source-ready" : "source-missing";
        const nextSourceVideoId = String(project.project.source_video_id || "");
        const sourceSummaryNeedsReset = smartClipSourceSummary.dataset.mode !== nextMode
            || smartClipSourceSummary.dataset.sourceVideoId !== nextSourceVideoId;
        if (sourceSummaryNeedsReset) {
            smartClipSourceSummary.innerHTML = sourceVideo
                ? `
                <video class="media-preview-small" controls preload="metadata" src="/api/videos/${project.project.source_video_id}/stream"></video>
                <p><strong>来源长视频：</strong><span data-smart-clip-source-title></span></p>
                <p><strong>视频时长：</strong><span data-smart-clip-source-duration></span></p>
                <p><strong>语音转文字状态：</strong><span data-smart-clip-source-asr></span></p>
                <p><strong>候选切片数：</strong><span data-smart-clip-source-candidates></span></p>
            `
                : `
                <div class="video-preview video-preview-compact">
                    <p>原视频已删除或不可访问，但项目记录仍保留在这里。</p>
                </div>
                <p><strong>来源长视频：</strong><span data-smart-clip-source-title></span></p>
                <p><strong>视频时长：</strong><span data-smart-clip-source-duration></span></p>
                <p><strong>语音转文字状态：</strong><span data-smart-clip-source-asr></span></p>
                <p><strong>候选切片数：</strong><span data-smart-clip-source-candidates></span></p>
            `;
            smartClipSourceSummary.dataset.mode = nextMode;
            smartClipSourceSummary.dataset.sourceVideoId = nextSourceVideoId;
        }
        const sourceTitle = smartClipSourceSummary.querySelector("[data-smart-clip-source-title]");
        const sourceDuration = smartClipSourceSummary.querySelector("[data-smart-clip-source-duration]");
        const sourceAsr = smartClipSourceSummary.querySelector("[data-smart-clip-source-asr]");
        const sourceCandidates = smartClipSourceSummary.querySelector("[data-smart-clip-source-candidates]");
        if (sourceTitle) sourceTitle.textContent = project.project.source_video_title || sourceVideoMeta.title || project.project.source_video_id || "-";
        if (sourceDuration) sourceDuration.textContent = sourceVideo ? `${Number(sourceVideoMeta.duration_sec || 0).toFixed(1)} 秒` : "-";
        if (sourceAsr) sourceAsr.textContent = sourceVideo ? asrStatusLabel(sourceVideoMeta.asr_status || "pending") : "-";
        if (sourceCandidates) sourceCandidates.textContent = `${Number(project.project.candidate_clip_count || 0)}`;
        smartClipProgressText.textContent = smartClipStageLabel(project.project.stage);
        smartClipProgressCounts.textContent = `${meta.current} / ${meta.total}`;
        smartClipProgressSummary.textContent = meta.summary;
        smartClipProgressBar.style.width = `${meta.percent}%`;
        smartClipProgressPanel.classList.toggle("loading-text", ["analyzing", "exporting"].includes(project.project.status));
        if (smartClipRestartBtn) {
            const canRestart = Boolean(project.project.source_video_id) && !["analyzing", "exporting"].includes(project.project.status);
            smartClipRestartBtn.disabled = !canRestart;
            smartClipRestartBtn.textContent = canRestart ? "重新智能切片" : "处理中，暂不可重新切片";
        }
        const canExport = project.project.status === "ready" && state.smartClipCandidates.some((item) => item.status === "active");
        smartClipExportBtn.disabled = !canExport;
        smartClipExportBtn.textContent = project.project.status === "exporting" ? "正在导出，请稍后" : "导出保留切片";
    }

    function smartClipCandidateStatusMeta(candidate) {
        if (candidate.status === "deleted") {
            return { className: statusClass("failed"), label: "已删除" };
        }
        if (candidate.status === "exported") {
            return { className: statusClass("success"), label: "已导出" };
        }
        if (candidate.status === "active") {
            return {
                className: statusClass("running"),
                label: candidate.output_video_path ? "预览已就绪" : "预览生成中",
            };
        }
        return { className: statusClass("running"), label: jobStatusLabel(candidate.status) };
    }

    function upsertSmartClipCandidateCard(candidate) {
        const projectId = state.smartClipProject?.project?.id;
        if (!projectId || !smartClipCandidateList) return null;
        let card = smartClipCandidateList.querySelector(`[data-smart-clip-candidate-id="${candidate.id}"]`);
        if (!card) {
            card = document.createElement("article");
            card.className = "panel candidate-item smart-clip-candidate-card";
            card.dataset.smartClipCandidateId = candidate.id;
            card.innerHTML = `
                <div class="candidate-meta-row candidate-meta-values">
                    <span data-smart-clip-field="clip-index"></span>
                    <span data-smart-clip-field="duration"></span>
                    <span data-smart-clip-field="source-title"></span>
                </div>
                <p data-smart-clip-field="preview-text"></p>
                <div class="smart-clip-preview-slot" data-smart-clip-field="preview-slot"></div>
                <div class="video-actions">
                    <button class="ghost-btn" type="button" data-smart-clip-delete="${candidate.id}">删除该候选</button>
                    <span data-smart-clip-field="status-chip" class="status-chip status-running">处理中</span>
                </div>
            `;
        }
        card.querySelector('[data-smart-clip-field="clip-index"]').textContent = `切片 ${candidate.clip_index}`;
        card.querySelector('[data-smart-clip-field="duration"]').textContent = `时长：${Number(candidate.duration_sec || 0).toFixed(1)} 秒`;
        card.querySelector('[data-smart-clip-field="source-title"]').textContent = `来源：${state.smartClipProject?.project?.source_video_title || "-"}`;
        card.querySelector('[data-smart-clip-field="preview-text"]').textContent = truncateText(candidate.preview_text || "暂无切片摘要", 140);
        const removeBtn = card.querySelector(`[data-smart-clip-delete="${candidate.id}"]`);
        if (removeBtn) {
            removeBtn.disabled = candidate.status !== "active";
        }
        const statusMeta = smartClipCandidateStatusMeta(candidate);
        const statusChip = card.querySelector('[data-smart-clip-field="status-chip"]');
        if (statusChip) {
            statusChip.className = `status-chip ${statusMeta.className}`;
            statusChip.textContent = statusMeta.label;
        }
        const previewSlot = card.querySelector('[data-smart-clip-field="preview-slot"]');
        const canStream = Boolean(candidate.output_video_path);
        const streamUrl = `/api/remix/smart-clips/projects/${projectId}/candidates/${candidate.id}/stream`;
        const existingVideo = previewSlot.querySelector("video");
        if (canStream) {
            if (!existingVideo) {
                previewSlot.innerHTML = "";
                const video = document.createElement("video");
                video.className = "media-preview-small";
                video.controls = true;
                video.preload = "metadata";
                video.src = streamUrl;
                previewSlot.appendChild(video);
            } else if (existingVideo.getAttribute("src") !== streamUrl) {
                existingVideo.setAttribute("src", streamUrl);
            }
        } else if (!existingVideo && !previewSlot.querySelector(".video-preview")) {
            previewSlot.innerHTML = '<div class="video-preview video-preview-compact"><p>系统正在生成该候选切片的预览视频，请稍后自动刷新。</p></div>';
        }
        return card;
    }

    function renderSmartClipCandidates() {
        if (!smartClipCandidateList) return;
        if (state.smartClipCandidateListFrozen) {
            return;
        }
        if (!state.smartClipCandidates.length) {
            smartClipCandidateList.innerHTML = "<p>候选切片生成后，这里会按时间顺序展示所有片段。</p>";
            return;
        }
        if (!smartClipCandidateList.querySelector("[data-smart-clip-candidate-id]")) {
            smartClipCandidateList.innerHTML = "";
        }
        const activeIds = new Set(state.smartClipCandidates.map((candidate) => candidate.id));
        smartClipCandidateList.querySelectorAll("[data-smart-clip-candidate-id]").forEach((node) => {
            if (!activeIds.has(node.dataset.smartClipCandidateId)) {
                node.remove();
            }
        });
        state.smartClipCandidates.forEach((candidate) => {
            const card = upsertSmartClipCandidateCard(candidate);
            if (card) {
                smartClipCandidateList.appendChild(card);
            }
        });
    }

    async function loadSmartClipProject(projectId) {
        if (!projectId) return;
        const detail = await request(`/api/remix/smart-clips/projects/${projectId}`);
        state.smartClipProject = detail;
        state.smartClipCandidates = detail.candidates || [];
        renderSmartClipProject();
        renderSmartClipCandidates();
        clearSmartClipPolling();
        if (["analyzing", "exporting"].includes(detail.project.status)) {
            state.smartClipPollingTimer = window.setTimeout(() => {
                loadSmartClipProject(projectId).catch(console.error);
            }, 3000);
        }
    }

    async function startSmartClipProject(videoId, options = {}) {
        if (!state.selectedRole) return;
        const forceRecreate = Boolean(options.forceRecreate);
        if (!forceRecreate) {
            const taskPayload = await request(`/api/remix/tasks?role_id=${encodeURIComponent(state.selectedRole.id)}`);
            const existing = (taskPayload.items || []).find((item) => item.task_type === "smart_clip"
                && item.source_video_id === videoId
                && ["analyzing", "ready", "exporting"].includes(item.status));
            const projectId = existing?.project_id || existing?.id;
            if (projectId) {
                await loadSmartClipProject(projectId);
                setRoute("smart-clip-project");
                return;
            }
        }
        const detail = await request("/api/remix/smart-clips/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ source_video_id: videoId, force_recreate: forceRecreate }),
        });
        state.smartClipProject = detail;
        state.smartClipCandidates = detail.candidates || [];
        renderSmartClipProject();
        renderSmartClipCandidates();
        setRoute("smart-clip-project");
        if (detail.project?.id) {
            await loadSmartClipProject(detail.project.id);
        }
    }

    async function exportSmartClipProject() {
        if (!state.smartClipProject?.project?.id) return;
        const detail = await request(`/api/remix/smart-clips/projects/${state.smartClipProject.project.id}/export`, {
            method: "POST",
        });
        state.smartClipProject = detail;
        state.smartClipCandidates = detail.candidates || [];
        renderSmartClipProject();
        renderSmartClipCandidates();
        await loadSmartClipProject(state.smartClipProject.project.id);
    }

    function renderTaskLists() {
        state.taskRecordSelectedIds.preprocess = new Set(
            [...state.taskRecordSelectedIds.preprocess].filter((id) => state.preprocessJobs.some((item) => item.id === id))
        );
        state.taskRecordSelectedIds.remix = new Set(
            [...state.taskRecordSelectedIds.remix].filter((id) => state.remixTasks.some((item) => item.id === id))
        );
        state.taskRecordSelectedIds["lip-sync"] = new Set(
            [...state.taskRecordSelectedIds["lip-sync"]].filter((id) => state.lipSyncTasks.some((item) => item.id === id))
        );

        const asrRunning = state.asrRecords.filter((record) => ["pending", "running"].includes(record.asr_status)).length;
        const preprocessRunning = asrRunning + state.preprocessJobs.filter((job) => job.status === "running").length;
        const remixRunning = state.remixTasks.filter((task) => (
            task.task_type === "smart_clip"
                ? ["analyzing", "exporting"].includes(task.status)
                : !["success", "failed", "cancelled", "partial_success"].includes(task.status)
        )).length;
        const lipSyncRunning = state.lipSyncTasks.filter((task) => !["success", "failed", "cancelled"].includes(task.status)).length;
        const taskBubbles = document.querySelector(".task-bubbles");
        if (taskBubbles) {
            taskBubbles.innerHTML = `
                <span class="status-chip status-running">预处理中：${preprocessRunning}</span>
                <span class="status-chip status-running">混合剪辑中：${remixRunning}</span>
                <span class="status-chip status-running">对口型生成中：${lipSyncRunning}</span>
            `;
        }

        const preprocessMeta = getTaskPageMeta("preprocess");
        const remixMeta = getTaskPageMeta("remix");
        const lipSyncMeta = getTaskPageMeta("lip-sync");
        if (preprocessJobList) {
            preprocessJobList.innerHTML = renderTaskHeader();
            preprocessJobList.innerHTML += preprocessMeta.pageItems.length
                ? preprocessMeta.pageItems.map((item) => renderTaskRow(item, "preprocess")).join("")
                : renderEmptyRow("暂无预处理或语音转文字记录");
        }
        if (remixTaskList) {
            remixTaskList.innerHTML = renderTaskHeader();
            remixTaskList.innerHTML += remixMeta.pageItems.length
                ? remixMeta.pageItems.map((item) => renderTaskRow(item, "remix")).join("")
                : renderEmptyRow("暂无混合剪辑任务");
        }
        if (lipSyncTaskList) {
            lipSyncTaskList.innerHTML = renderTaskHeader();
            lipSyncTaskList.innerHTML += lipSyncMeta.pageItems.length
                ? lipSyncMeta.pageItems.map((item) => renderTaskRow(item, "lip-sync")).join("")
                : renderEmptyRow("暂无对口型生成任务");
        }
        syncTaskTab();
        renderTaskDeleteToolbar();
    }

    function syncTaskTab() {
        taskTabs.forEach((tab) => {
            tab.classList.toggle("active", tab.dataset.taskTab === state.activeTaskTab);
        });
        preprocessJobList.hidden = state.activeTaskTab !== "preprocess";
        remixTaskList.hidden = state.activeTaskTab !== "remix";
        lipSyncTaskList.hidden = state.activeTaskTab !== "lip-sync";
        if (taskPrevPageBtn && taskNextPageBtn && taskPageIndicator) {
            const meta = getTaskPageMeta(state.activeTaskTab);
            taskPageIndicator.textContent = `第 ${meta.page} / ${meta.totalPages} 页，每页 ${TASK_PAGE_SIZE} 条`;
            taskPrevPageBtn.disabled = meta.page <= 1 || state.taskRecordDeleting;
            taskNextPageBtn.disabled = meta.page >= meta.totalPages || state.taskRecordDeleting;
        }
        renderTaskDeleteToolbar();
    }

    async function loadRoles(search) {
        const query = search ? `?search=${encodeURIComponent(search)}` : "";
        const payload = await request(`/api/roles${query}`);
        state.roles = payload.items || [];
        renderRoles();
    }

    async function loadVideos() {
        if (!state.selectedRole) return;
        const payload = await request(`/api/roles/${state.selectedRole.id}/videos`);
        state.videos = payload.items || [];
        renderVideoGroups();
    }

    async function loadRemixVideos(search) {
        if (!state.selectedRole) return;
        const payload = await request(`/api/roles/${state.selectedRole.id}/remix/videos`);
        const keyword = String(search || "").trim().toLowerCase();
        state.remixVideos = (payload.items || []).filter((item) => {
            if (!keyword) return true;
            return String(item.title || "").toLowerCase().includes(keyword);
        });
        renderRemixVideoList();
    }

    async function loadLipSyncVideos(search) {
        if (!state.selectedRole) return;
        const payload = await request(`/api/roles/${state.selectedRole.id}/lip-sync/videos`);
        const keyword = String(search || "").trim().toLowerCase();
        state.lipSyncVideos = (payload.items || []).filter((item) => {
            if (!keyword) return true;
            return String(item.title || "").toLowerCase().includes(keyword);
        });
        renderLipSyncVideoList();
    }

    async function loadLipSyncProductDocs() {
        if (!state.selectedRole) return;
        const payload = await request(`/api/roles/${state.selectedRole.id}/product-docs`);
        state.lipSyncProductDocs = payload.items || [];
        renderLipSyncProductDocList();
    }

    async function loadFinalVideos() {
        if (!state.selectedRole) return;
        const params = new URLSearchParams();
        params.set("role_id", state.selectedRole.id);
        if (state.finalVideoQuery) {
            params.set("q", state.finalVideoQuery);
        }
        if (state.finalVideoSourceType && state.finalVideoSourceType !== "all") {
            params.set("source_type", state.finalVideoSourceType);
        }
        const payload = await request(`/api/final-videos?${params.toString()}`);
        state.finalVideos = payload.items || [];
        renderFinalVideoList();
    }

    async function loadTaskProgress() {
        if (!state.selectedRole) return;
        const roleQuery = `?role_id=${encodeURIComponent(state.selectedRole.id)}`;
        const [preprocessPayload, remixPayload, lipSyncPayload] = await Promise.all([
            request(`/api/remix/preprocess-jobs${roleQuery}`),
            request(`/api/remix/tasks${roleQuery}`),
            request(`/api/lip-sync/tasks${roleQuery}`),
        ]);
        state.preprocessJobs = preprocessPayload.items || [];
        state.asrRecords = preprocessPayload.asr_records || [];
        state.remixTasks = remixPayload.items || [];
        state.lipSyncTasks = lipSyncPayload.items || [];
        renderTaskLists();
        clearTaskPolling();
        const hasActiveAsr = state.asrRecords.some((record) => ["pending", "running"].includes(record.asr_status));
        const hasActivePreprocess = state.preprocessJobs.some((job) => ["pending", "running"].includes(job.status));
        const hasActiveRemix = state.remixTasks.some((task) => (
            task.task_type === "smart_clip"
                ? ["analyzing", "exporting"].includes(task.status)
                : !["success", "failed", "cancelled", "partial_success"].includes(task.status)
        ));
        const hasActiveLipSync = state.lipSyncTasks.some((task) => !["success", "failed", "cancelled"].includes(task.status));
        if (state.route === "tasks" && (hasActiveAsr || hasActivePreprocess || hasActiveRemix || hasActiveLipSync)) {
            state.taskPollingTimer = window.setTimeout(() => {
                loadTaskProgress().catch(console.error);
            }, 3000);
        }
    }

    function getSelectedTaskIds(tab) {
        return [...(state.taskRecordSelectedIds[tab] || new Set())];
    }

    function getFinalVideoItemsByIds(ids) {
        return state.finalVideos.filter((item) => ids.includes(item.id));
    }

    async function deleteFinalVideosByIds(ids) {
        if (!state.selectedRole || !ids.length) return;
        const items = getFinalVideoItemsByIds(ids);
        if (!items.length) return;
        const confirmText = ids.length === 1
            ? FINAL_VIDEO_DELETE_CONFIRM
            : `将删除 ${ids.length} 条成片记录及对应视频文件，不可恢复。`;
        if (!window.confirm(confirmText)) return;
        state.finalVideoDeleting = true;
        renderFinalVideoBulkToolbar();
        try {
            let deletedIds = [...ids];
            let result = null;
            if (ids.length === 1) {
                const item = items[0];
                await request(`/api/final-videos/${encodeURIComponent(item.id)}?role_id=${encodeURIComponent(state.selectedRole.id)}&source_type=${encodeURIComponent(item.source_type)}`, {
                    method: "DELETE",
                });
            } else {
                result = await request("/api/final-videos/batch-delete", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        role_id: state.selectedRole.id,
                        items: items.map((item) => ({ id: item.id, source_type: item.source_type })),
                    }),
                });
                const failedItems = Array.isArray(result.failed_items) ? result.failed_items : [];
                const failedKeys = new Set(failedItems.map((item) => `${item.id}::${item.source_type}`));
                deletedIds = items
                    .filter((item) => !failedKeys.has(`${item.id}::${item.source_type}`))
                    .map((item) => item.id);
                notifyBatchDeleteResult("成片记录", result, ids.length);
            }
            state.finalVideoSelectedIds = new Set([...state.finalVideoSelectedIds].filter((id) => !deletedIds.includes(id)));
            await loadFinalVideos();
        } finally {
            state.finalVideoDeleting = false;
            renderFinalVideoBulkToolbar();
        }
    }

    async function deleteTaskRecords(tab, ids) {
        if (!state.selectedRole || !ids.length) return;
        const confirmText = ids.length === 1
            ? TASK_RECORD_DELETE_CONFIRM
            : `将删除 ${ids.length} 条任务记录，不删除已生成文件。`;
        if (!window.confirm(confirmText)) return;
        state.taskRecordDeleting = true;
        renderTaskDeleteToolbar();
        const roleId = state.selectedRole.id;
        try {
            let deletedIds = [...ids];
            let result = null;
            if (tab === "preprocess") {
                if (ids.length === 1) {
                    await request(`/api/remix/preprocess-jobs/${encodeURIComponent(ids[0])}?role_id=${encodeURIComponent(roleId)}`, { method: "DELETE" });
                } else {
                    result = await request("/api/remix/preprocess-jobs/batch-delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ role_id: roleId, ids }),
                    });
                }
            } else if (tab === "remix") {
                if (ids.length === 1) {
                    await request(`/api/remix/tasks/${encodeURIComponent(ids[0])}?role_id=${encodeURIComponent(roleId)}`, { method: "DELETE" });
                } else {
                    result = await request("/api/remix/tasks/batch-delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ role_id: roleId, ids }),
                    });
                }
            } else if (tab === "lip-sync") {
                if (ids.length === 1) {
                    await request(`/api/lip-sync/tasks/${encodeURIComponent(ids[0])}?role_id=${encodeURIComponent(roleId)}`, { method: "DELETE" });
                } else {
                    result = await request("/api/lip-sync/tasks/batch-delete", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ role_id: roleId, ids }),
                    });
                }
            }
            if (result && ids.length > 1) {
                const failedIds = Array.isArray(result.failed_ids) ? result.failed_ids.map((id) => String(id)) : [];
                const failedSet = new Set(failedIds);
                deletedIds = ids.filter((id) => !failedSet.has(id));
                notifyBatchDeleteResult("任务记录", result, ids.length);
            }
            state.taskRecordSelectedIds[tab] = new Set(
                [...state.taskRecordSelectedIds[tab]].filter((id) => !deletedIds.includes(id))
            );
            await loadTaskProgress();
        } finally {
            state.taskRecordDeleting = false;
            renderTaskDeleteToolbar();
        }
    }

    async function handleSelectLipSyncVideo(videoId) {
        const video = state.lipSyncVideos.find((item) => item.id === videoId);
        if (!video || !video.selectable) return;
        state.selectedLipSyncVideo = video;
        state.lipSyncProject = null;
        state.lipSyncCandidates = [];
        state.selectedLipSyncScriptId = null;
        state.selectedLipSyncProductDocId = null;
        state.lipSyncGeneratingScripts = false;
        state.lipSyncScriptGenerationMessage = "";
        state.lipSyncRegeneratingCandidateId = null;
        resetLipSyncSubmitStatus();
        renderLipSyncScriptPreview();
        renderLipSyncCandidateList();
        await loadLipSyncProductDocs();
        renderLipSyncGenerationStatus();
        setRoute("lip-sync-scripts");
    }

    async function createLipSyncProjectIfNeeded() {
        if (state.lipSyncProject || !state.selectedRole || !state.selectedLipSyncVideo) return state.lipSyncProject;
        state.lipSyncProject = await request("/api/lip-sync/projects", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                role_id: state.selectedRole.id,
                base_video_id: state.selectedLipSyncVideo.id,
                prompt_text: document.getElementById("lip-sync-prompt-input").value.trim() || "默认对口型提示词",
                product_doc_text: lipSyncProductDocInput.value.trim(),
            }),
        });
        return state.lipSyncProject;
    }

    async function createOrRefreshLipSyncProjectByPrompt() {
        state.lipSyncProject = null;
        return createLipSyncProjectIfNeeded();
    }

    function toggleLipSyncAspectWarning() {
        if (!lipSyncAspectModeInput || !lipSyncAspectWarning) return;
        lipSyncAspectWarning.hidden = lipSyncAspectModeInput.value === "default";
    }

    async function showAsr(videoId) {
        return pollAsrStatus(videoId);
    }

    function showPreview(videoId) {
        state.selectedVideo = state.videos.find((item) => item.id === videoId) || null;
        if (!state.selectedVideo) return;
        videoPreviewContainer.innerHTML = `
            <video class="media-preview-small" controls src="/api/videos/${videoId}/stream"></video>
            <p>${state.selectedVideo.title}</p>
        `;
    }

    function createUploadRequest(url, formData, onProgress) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open("POST", url);
            xhr.responseType = "json";
            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable && typeof onProgress === "function") {
                    const percent = (event.loaded / event.total) * 100;
                    onProgress(percent);
                }
            };
            xhr.onload = () => {
                const payload = xhr.response || {};
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(payload);
                    return;
                }
                const message = extractErrorMessage(payload, "请求失败");
                reject(new Error(message));
            };
            xhr.onerror = () => reject(new Error("上传失败，请检查网络连接"));
            xhr.send(formData);
        });
    }

    async function createRole(formData) {
        const payload = {
            name: formData.get("name"),
            description: formData.get("description"),
            avatar_url: formData.get("avatar_url"),
            tags: String(formData.get("tags") || "")
                .split(",")
                .map((item) => item.trim())
                .filter(Boolean),
        };
        const role = await request("/api/roles", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        await loadRoles();
        await enterRole(role);
    }

    async function enterRole(role) {
        resetWorkbenchContext();
        state.selectedRole = role;
        if (selectedRoleName) {
            selectedRoleName.textContent = role.name;
        }
        if (videoManagerRoleName) {
            videoManagerRoleName.textContent = `${role.name}的视频管理`;
        }
        syncWorkbenchNav();
        setRoute("video-manager");
        await loadVideos();
    }

    function leaveRole() {
        resetWorkbenchContext();
        setRoute("lobby");
        renderRoles();
    }

    async function uploadVideo(file) {
        if (!state.selectedRole || !file) return;
        const body = new FormData();
        body.append("video", file);
        setUploadState({
            active: true,
            progress: 0,
            message: `正在上传 ${file.name}，请稍候`,
        });
        try {
            const created = await createUploadRequest(`/api/roles/${state.selectedRole.id}/videos/upload`, body, (progress) => {
                setUploadState({
                    progress,
                    message: `正在上传 ${file.name}，请稍候`,
                });
            });
        setUploadState({
            active: false,
            progress: 100,
            message: "上传完成，正在进入语音转文字处理",
        });
            if (created && created.id) {
                clearAsrPolling();
                state.selectedVideo = created;
                showPreview(created.id);
                await pollAsrStatus(created.id);
            }
            await loadVideos();
            window.setTimeout(() => {
                if (!state.uploadState.active) {
                    setUploadState({ progress: 0, message: "等待上传" });
                }
            }, 1200);
        } catch (error) {
            setUploadState({
                active: false,
                progress: 0,
                message: `上传失败：${error.message}`,
            });
            throw error;
        }
    }

    async function handleSelectRemixVideo(videoId) {
        const video = state.remixVideos.find((item) => item.id === videoId);
        if (!video) return;
        state.selectedRemixVideo = video;
        state.preprocessJob = null;
        state.preprocessSegments = [];
        renderSelectedRemixVideoSummary();
        setRoute("remix-task-create");
        const payload = await request("/api/remix/preprocess", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ video_id: videoId }),
        });
        state.preprocessJob = payload.job;
        state.preprocessSegments = payload.segments || [];
        renderSelectedRemixVideoSummary();
        await loadTaskProgress();
    }

    function toggleAspectWarning() {
        if (!remixAspectModeInput || !remixAspectWarning) return;
        remixAspectWarning.hidden = remixAspectModeInput.value === "default";
    }

    document.querySelectorAll("[data-route]").forEach((node) => {
        node.addEventListener("click", async () => {
            const route = node.dataset.route;
            if (!route || !routeMap[route]) return;
            setRoute(route);
            if (route === "video-manager") {
                await loadVideos();
            }
            if (route === "remix-video-select") {
                await loadRemixVideos();
            }
            if (route === "smart-clip-project" && state.smartClipProject?.project?.id) {
                await loadSmartClipProject(state.smartClipProject.project.id);
            }
            if (route === "lip-sync-video-select") {
                await loadLipSyncVideos();
            }
            if (route === "tasks") {
                await loadTaskProgress();
            }
            if (route === "review") {
                await loadFinalVideos();
            }
        });
    });
    document.addEventListener("fullscreenchange", () => {
        const fullscreenNode = document.fullscreenElement;
        const shouldFreeze = Boolean(fullscreenNode && smartClipCandidateList?.contains(fullscreenNode));
        const wasFrozen = state.smartClipCandidateListFrozen;
        state.smartClipCandidateListFrozen = shouldFreeze;
        if (wasFrozen && !shouldFreeze) {
            renderSmartClipCandidates();
        }
    });

    document.getElementById("create-role-btn")?.addEventListener("click", () => setRoute("create-role"));
    document.getElementById("top-create-role-btn")?.addEventListener("click", () => setRoute("create-role"));
    document.getElementById("cancel-create-role-btn")?.addEventListener("click", () => setRoute("lobby"));
    if (switchRoleBtn) {
        switchRoleBtn.addEventListener("click", () => {
            leaveRole();
        });
    }
    document.getElementById("default-avatar-btn")?.addEventListener("click", () => {
        const roleAvatarInput = document.getElementById("role-avatar-input");
        if (roleAvatarInput) {
            roleAvatarInput.value = "";
        }
    });
    roleCoverUploadInput?.addEventListener("change", async (event) => {
        const input = event.currentTarget;
        const roleId = input?.dataset.roleId || pendingRoleCoverUploadId;
        const file = event.target.files?.[0];
        input.dataset.roleId = "";
        pendingRoleCoverUploadId = null;
        if (!roleId || !file) {
            return;
        }
        try {
            await submitRoleCoverUpload(roleId, file);
        } catch (error) {
            console.error(error);
            window.alert(`更换封面失败：${error.message}`);
        }
    });
    document.getElementById("enter-video-manager-btn")?.addEventListener("click", async () => {
        setRoute("video-manager");
        await loadVideos();
    });
    document.getElementById("enter-remix-btn")?.addEventListener("click", async () => {
        setRoute("remix-video-select");
        await loadRemixVideos();
    });
    document.getElementById("smart-clip-back-btn")?.addEventListener("click", async () => {
        clearSmartClipPolling();
        setRoute("remix-video-select");
        await loadRemixVideos();
    });
    smartClipRestartBtn?.addEventListener("click", async () => {
        const sourceVideoId = state.smartClipProject?.project?.source_video_id;
        if (!sourceVideoId || smartClipRestartBtn.disabled) return;
        await startSmartClipProject(sourceVideoId, { forceRecreate: true });
    });
    smartClipExportBtn?.addEventListener("click", async () => {
        await exportSmartClipProject();
    });
    document.getElementById("enter-lip-sync-btn")?.addEventListener("click", async () => {
        setRoute("lip-sync-video-select");
        await loadLipSyncVideos();
    });
    document.getElementById("open-tasks-btn")?.addEventListener("click", async () => {
        setRoute("tasks");
        await loadTaskProgress();
    });
    document.getElementById("open-lip-sync-tasks-btn")?.addEventListener("click", async () => {
        setRoute("tasks");
        state.activeTaskTab = "lip-sync";
        await loadTaskProgress();
    });
    if (finalVideoSearchInput) {
        finalVideoSearchInput.addEventListener("input", (event) => {
            state.finalVideoQuery = event.target.value.trim();
            loadFinalVideos().catch(console.error);
        });
    }
    if (finalVideoSourceTypeFilter) {
        finalVideoSourceTypeFilter.addEventListener("change", (event) => {
            state.finalVideoSourceType = event.target.value;
            loadFinalVideos().catch(console.error);
        });
    }
    if (finalVideoSelectAllBtn) {
        finalVideoSelectAllBtn.addEventListener("click", () => {
            if (state.finalVideoSelectedIds.size === state.finalVideos.length && state.finalVideos.length) {
                state.finalVideoSelectedIds = new Set();
            } else {
                state.finalVideoSelectedIds = new Set(state.finalVideos.map((item) => item.id));
            }
            renderFinalVideoList();
        });
    }
    if (finalVideoClearSelectionBtn) {
        finalVideoClearSelectionBtn.addEventListener("click", () => {
            state.finalVideoSelectedIds = new Set();
            renderFinalVideoList();
        });
    }
    if (finalVideoDeleteSelectedBtn) {
        finalVideoDeleteSelectedBtn.addEventListener("click", async () => {
            await deleteFinalVideosByIds([...state.finalVideoSelectedIds]);
        });
    }
    finalVideoList?.addEventListener("change", (event) => {
        const select = event.target.closest("[data-final-video-select]");
        if (!select) return;
        const itemId = select.dataset.finalVideoSelect;
        if (select.checked) {
            state.finalVideoSelectedIds.add(itemId);
        } else {
            state.finalVideoSelectedIds.delete(itemId);
        }
        renderFinalVideoBulkToolbar();
    });
    finalVideoList?.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-final-video-delete]");
        if (!button) return;
        await deleteFinalVideosByIds([button.dataset.finalVideoDelete]);
    });
    if (taskSelectAllBtn) {
        taskSelectAllBtn.addEventListener("click", () => {
            const tab = state.activeTaskTab;
            const ids = getTaskPageSelectableIds(tab);
            const selection = getTaskSelectionSet(tab);
            const allVisibleSelected = ids.length > 0 && ids.every((id) => selection.has(id));
            if (allVisibleSelected) {
                state.taskRecordSelectedIds[tab] = new Set(
                    [...selection].filter((id) => !ids.includes(id))
                );
            } else {
                state.taskRecordSelectedIds[tab] = new Set([...selection, ...ids]);
            }
            renderTaskLists();
        });
    }
    if (taskClearSelectionBtn) {
        taskClearSelectionBtn.addEventListener("click", () => {
            state.taskRecordSelectedIds[state.activeTaskTab] = new Set();
            renderTaskLists();
        });
    }
    if (taskPrevPageBtn) {
        taskPrevPageBtn.addEventListener("click", () => {
            const tab = state.activeTaskTab;
            const meta = getTaskPageMeta(tab);
            state.taskPagination[tab] = Math.max(1, meta.page - 1);
            renderTaskLists();
        });
    }
    if (taskNextPageBtn) {
        taskNextPageBtn.addEventListener("click", () => {
            const tab = state.activeTaskTab;
            const meta = getTaskPageMeta(tab);
            state.taskPagination[tab] = Math.min(meta.totalPages, meta.page + 1);
            renderTaskLists();
        });
    }
    if (taskDeleteSelectedBtn) {
        taskDeleteSelectedBtn.addEventListener("click", async () => {
            await deleteTaskRecords(state.activeTaskTab, getSelectedTaskIds(state.activeTaskTab));
        });
    }
    document.getElementById("refresh-videos-btn")?.addEventListener("click", loadVideos);
    document.getElementById("change-lip-sync-video-btn")?.addEventListener("click", async () => {
        setRoute("lip-sync-video-select");
        await loadLipSyncVideos();
    });
    document.getElementById("generate-lip-sync-scripts-btn")?.addEventListener("click", async () => {
        if (!state.selectedLipSyncVideo) return;
        state.lipSyncGeneratingScripts = true;
        state.lipSyncScriptGenerationMessage = "正在生成文案，请稍后";
        renderLipSyncGenerationStatus();
        try {
            const project = await createOrRefreshLipSyncProjectByPrompt();
            const payload = await request(`/api/lip-sync/projects/${project.id}/scripts/generate`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ count: 3 }),
            });
            state.lipSyncProject = payload.project;
            state.lipSyncCandidates = payload.candidates || [];
            state.lipSyncScriptGenerationMessage = `已生成 ${state.lipSyncCandidates.length} 条候选文案`;
            renderLipSyncCandidateList();
        } finally {
            state.lipSyncGeneratingScripts = false;
            renderLipSyncGenerationStatus();
        }
    });
    document.getElementById("go-lip-sync-confirm-btn")?.addEventListener("click", () => {
        if (!state.selectedLipSyncScriptId) return;
        resetLipSyncSubmitStatus();
        renderLipSyncConfirmSummary();
        setRoute("lip-sync-confirm");
    });

    createRoleForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        await createRole(new FormData(createRoleForm));
        createRoleForm.reset();
    });

    remixTaskForm?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!state.selectedRole || !state.selectedRemixVideo) {
            return;
        }
        const payload = {
            role_id: state.selectedRole.id,
            source_video_id: state.selectedRemixVideo.id,
            prompt_text: document.getElementById("remix-prompt-input").value.trim(),
            product_doc_text: document.getElementById("remix-product-doc-input").value.trim(),
            target_count: Number(document.getElementById("remix-target-count-input").value || 1),
            is_max_mode: document.getElementById("remix-max-mode-input").checked,
            aspect_mode: remixAspectModeInput.value,
            resolution: document.getElementById("remix-resolution-input").value,
            subtitle_enabled: document.getElementById("remix-subtitle-input").checked,
        };
        await request("/api/remix/tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        setRoute("tasks");
        await loadTaskProgress();
    });

    globalRoleSearch?.addEventListener("input", (event) => {
        loadRoles(event.target.value.trim()).catch(console.error);
    });

    remixVideoSearch?.addEventListener("input", (event) => {
        loadRemixVideos(event.target.value).catch(console.error);
    });
    lipSyncVideoSearch?.addEventListener("input", (event) => {
        loadLipSyncVideos(event.target.value).catch(console.error);
    });

    roleGrid?.addEventListener("click", (event) => {
        const coverUpload = event.target.closest("[data-role-cover-upload]");
        if (coverUpload) {
            openRoleCoverUpload(coverUpload.dataset.roleCoverUpload);
            return;
        }
        const deleteRole = event.target.closest("[data-role-delete]");
        if (deleteRole) {
            confirmDeleteRole(deleteRole.dataset.roleDelete).catch(console.error);
            return;
        }
        const target = event.target.closest("[data-role-enter]");
        if (!target) return;
        const role = state.roles.find((item) => item.id === target.dataset.roleEnter) || null;
        if (!role) return;
        enterRole(role).catch(console.error);
    });

    document.getElementById("video-groups")?.addEventListener("click", async (event) => {
        const preview = event.target.closest("[data-preview-video]");
        const pin = event.target.closest("[data-pin-video]");
        const remove = event.target.closest("[data-delete-video]");
        const refresh = event.target.closest("[data-refresh-asr]");

        if (preview) {
            showPreview(preview.dataset.previewVideo);
            await showAsr(preview.dataset.previewVideo);
        } else if (refresh) {
            showPreview(refresh.dataset.refreshAsr);
            await showAsr(refresh.dataset.refreshAsr);
        } else if (pin) {
            const videoId = pin.dataset.pinVideo;
            const video = state.videos.find((item) => item.id === videoId);
            await request(`/api/videos/${videoId}/pin`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ is_pinned: !video.is_pinned }),
            });
            await loadVideos();
        } else if (remove) {
            await request(`/api/videos/${remove.dataset.deleteVideo}`, { method: "DELETE" });
            if (state.selectedVideo && state.selectedVideo.id === remove.dataset.deleteVideo) {
                state.selectedVideo = null;
                clearAsrPolling();
                videoPreviewContainer.innerHTML = "<p>选择视频后可在这里预览。</p>";
                asrStatusPanel.innerHTML = "<p>上传视频后可查看语音转文字处理状态。</p>";
                asrSummaryPanel.textContent = "暂无语音转文字总结";
            }
            await loadVideos();
            if (state.route === "tasks") {
                await loadTaskProgress();
            }
        }
    });

    remixVideoList?.addEventListener("click", async (event) => {
        const select = event.target.closest("[data-remix-select]");
        const smartClipStart = event.target.closest("[data-smart-clip-start]");
        if (select) {
            await handleSelectRemixVideo(select.dataset.remixSelect);
            return;
        }
        if (smartClipStart) {
            await startSmartClipProject(smartClipStart.dataset.smartClipStart);
        }
    });
    lipSyncVideoList?.addEventListener("click", async (event) => {
        const select = event.target.closest("[data-lip-sync-select]");
        if (select) {
            await handleSelectLipSyncVideo(select.dataset.lipSyncSelect);
        }
    });
    lipSyncCandidateList?.addEventListener("click", async (event) => {
        const select = event.target.closest("[data-candidate-select]");
        const regenerate = event.target.closest("[data-candidate-regenerate]");
        if (select) {
            const candidateId = select.dataset.candidateSelect;
            const editor = lipSyncCandidateList.querySelector(`[data-candidate-edit="${candidateId}"]`);
            if (editor) {
                const editedContent = editor.value.trim();
                await request(`/api/lip-sync/projects/${state.lipSyncProject.id}/scripts/${candidateId}/edit`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ edited_content: editedContent }),
                });
                const local = state.lipSyncCandidates.find((item) => item.id === candidateId);
                if (local) {
                    local.edited_content = editedContent;
                    local.is_edited = true;
                }
            }
            const payload = await request(`/api/lip-sync/projects/${state.lipSyncProject.id}/select-script`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ script_id: candidateId }),
            });
            state.lipSyncProject = payload.project;
            state.selectedLipSyncScriptId = candidateId;
            renderLipSyncCandidateList();
            renderLipSyncConfirmSummary();
        } else if (regenerate) {
            const candidateId = regenerate.dataset.candidateRegenerate;
            state.lipSyncRegeneratingCandidateId = candidateId;
            renderLipSyncCandidateList();
            try {
                const regenerated = await request(`/api/lip-sync/projects/${state.lipSyncProject.id}/scripts/${candidateId}/regenerate`, {
                    method: "POST",
                });
                state.lipSyncCandidates = state.lipSyncCandidates.map((item) => (
                    item.id === candidateId ? { ...item, ...regenerated } : item
                ));
                renderLipSyncCandidateList();
                renderLipSyncConfirmSummary();
            } finally {
                state.lipSyncRegeneratingCandidateId = null;
                renderLipSyncCandidateList();
            }
        }
    });

    lipSyncProductDocList?.addEventListener("click", async (event) => {
        const select = event.target.closest("[data-product-doc-select]");
        if (!select) return;
        const detail = await request(`/api/product-docs/${select.dataset.productDocSelect}`);
        state.selectedLipSyncProductDocId = detail.id;
        lipSyncProductDocInput.value = detail.content || "";
        renderLipSyncProductDocList();
    });

    lipSyncProductDocUploadInput?.addEventListener("change", async (event) => {
        if (!state.selectedRole) return;
        const [file] = event.target.files || [];
        if (!file) return;
        const formData = new FormData();
        formData.append("file", file);
        const payload = await createUploadRequest(`/api/roles/${state.selectedRole.id}/product-docs/upload`, formData);
        state.selectedLipSyncProductDocId = payload.id;
        lipSyncProductDocInput.value = payload.content || "";
        await loadLipSyncProductDocs();
        lipSyncProductDocUploadInput.value = "";
    });

    preprocessJobList?.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-cancel-preprocess]");
        const deleteButton = event.target.closest("[data-delete-task-type='preprocess']");
        if (button) {
            await request(`/api/remix/preprocess-jobs/${button.dataset.cancelPreprocess}/cancel`, { method: "POST" });
            await loadTaskProgress();
            return;
        }
        if (deleteButton) {
            await deleteTaskRecords("preprocess", [deleteButton.dataset.deleteTaskId]);
        }
    });
    preprocessJobList?.addEventListener("change", (event) => {
        const select = event.target.closest("[data-task-select-type='preprocess']");
        if (!select) return;
        const next = state.taskRecordSelectedIds.preprocess;
        if (select.checked) {
            next.add(select.dataset.taskSelectId);
        } else {
            next.delete(select.dataset.taskSelectId);
        }
        renderTaskDeleteToolbar();
    });

    remixTaskList?.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-cancel-remix-task]");
        const deleteButton = event.target.closest("[data-delete-task-type='remix']");
        const openSmartClip = event.target.closest("[data-open-smart-clip-project]");
        if (openSmartClip) {
            await loadSmartClipProject(openSmartClip.dataset.openSmartClipProject);
            setRoute("smart-clip-project");
            return;
        }
        if (button) {
            await request(`/api/remix/tasks/${button.dataset.cancelRemixTask}/cancel`, { method: "POST" });
            await loadTaskProgress();
            return;
        }
        if (deleteButton) {
            await deleteTaskRecords("remix", [deleteButton.dataset.deleteTaskId]);
        }
    });
    remixTaskList?.addEventListener("change", (event) => {
        const select = event.target.closest("[data-task-select-type='remix']");
        if (!select) return;
        const next = state.taskRecordSelectedIds.remix;
        if (select.checked) {
            next.add(select.dataset.taskSelectId);
        } else {
            next.delete(select.dataset.taskSelectId);
        }
        renderTaskDeleteToolbar();
    });
    lipSyncTaskList?.addEventListener("click", async (event) => {
        const cancel = event.target.closest("[data-cancel-lip-sync-task]");
        const open = event.target.closest("[data-open-lip-sync-task]");
        const remove = event.target.closest("[data-delete-task-type='lip-sync']");
        if (cancel) {
            await request(`/api/lip-sync/tasks/${cancel.dataset.cancelLipSyncTask}/cancel`, { method: "POST" });
            await loadTaskProgress();
        } else if (open) {
            const detail = await request(`/api/lip-sync/tasks/${open.dataset.openLipSyncTask}`);
            window.alert(`任务详情\n状态：${jobStatusLabel(detail.task.status)}\n失败原因：${detail.task.error_message || "无"}`);
        } else if (remove) {
            await deleteTaskRecords("lip-sync", [remove.dataset.deleteTaskId]);
        }
    });
    lipSyncTaskList?.addEventListener("change", (event) => {
        const select = event.target.closest("[data-task-select-type='lip-sync']");
        if (!select) return;
        const next = state.taskRecordSelectedIds["lip-sync"];
        if (select.checked) {
            next.add(select.dataset.taskSelectId);
        } else {
            next.delete(select.dataset.taskSelectId);
        }
        renderTaskDeleteToolbar();
    });

    smartClipCandidateList?.addEventListener("click", async (event) => {
        const remove = event.target.closest("[data-smart-clip-delete]");
        if (!remove || !state.smartClipProject?.project?.id) return;
        await request(`/api/remix/smart-clips/candidates/${remove.dataset.smartClipDelete}`, {
            method: "DELETE",
        });
        await loadSmartClipProject(state.smartClipProject.project.id);
    });

    videoUploadInput?.addEventListener("change", async (event) => {
        const file = event.target.files[0];
        try {
            await uploadVideo(file);
        } catch (error) {
            console.error(error);
        } finally {
            videoUploadInput.value = "";
        }
    });

    taskTabs.forEach((tab) => {
        tab.addEventListener("click", () => {
            state.activeTaskTab = tab.dataset.taskTab;
            renderTaskLists();
        });
    });

    remixAspectModeInput?.addEventListener("change", toggleAspectWarning);
    lipSyncAspectModeInput?.addEventListener("change", toggleLipSyncAspectWarning);
    toggleAspectWarning();
    toggleLipSyncAspectWarning();
    renderUploadProgress();
    renderRoles();
    loadRoles().catch(console.error);
    applyPathRoute();
    window.addEventListener("popstate", applyPathRoute);
    window.addEventListener("beforeunload", () => {
        clearAsrPolling();
        clearTaskPolling();
        clearSmartClipPolling();
    });

    document.getElementById("lip-sync-confirm-form")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        if (!state.lipSyncProject || !state.selectedLipSyncScriptId) return;
        state.lipSyncSubmittingTask = true;
        state.lipSyncSubmitStatus = "";
        state.lipSyncSubmitMessage = "正在提交任务，请稍后";
        renderLipSyncSubmitStatus();
        try {
            const task = await request("/api/lip-sync/tasks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    project_id: state.lipSyncProject.id,
                    selected_script_id: state.selectedLipSyncScriptId,
                    aspect_mode: lipSyncAspectModeInput.value,
                    resolution: document.getElementById("lip-sync-resolution-input").value,
                    subtitle_enabled: document.getElementById("lip-sync-subtitle-input").checked,
                }),
            });
            state.activeTaskTab = "lip-sync";
            await loadTaskProgress();
            state.lipSyncSubmitStatus = "success";
            state.lipSyncSubmitMessage = lipSyncSubmitMessageForStatus(task?.status);
        } catch (error) {
            state.lipSyncSubmitStatus = "error";
            state.lipSyncSubmitMessage = error.message || "提交任务失败，请稍后重试";
        } finally {
            state.lipSyncSubmittingTask = false;
            renderLipSyncSubmitStatus();
        }
    });
})();
