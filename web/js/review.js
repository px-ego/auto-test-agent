const TASK_LABELS = {
    planning: '生成中', awaiting_review: '待审核', approved: '审核通过',
    rejected: '已驳回', executing: '执行中', reporting: '报告生成中',
    done: '已完成', stopped: '已停止', report_failed: '报告生成失败',
    error: '任务失败', execution_uncertain: '执行中断，待检查设备',
    diagnosing: '失败诊断中', diagnostic_failed: '诊断中断，可继续'
};

function refreshReviewControls() {
    var status = document.getElementById('review-status');
    var state = currentTask ? currentTask.state : 'awaiting_review';
    status.textContent = (TASK_LABELS[state] || state)
        + (currentTask ? ' · 版本 ' + currentTask.revision : '')
        + (reviewDirty ? ' · 有未审核修改' : '');
    var editable = currentTask && (['awaiting_review', 'rejected'].includes(state) || state === 'approved' && reviewDirty);
    document.getElementById('btn-approve-plan').disabled = !editable;
    document.getElementById('btn-reject-plan').disabled = !editable;
    document.getElementById('btn-start-test').disabled = !currentTask || state !== 'approved' || reviewDirty;
}

function markPlanEdited() {
    if (!currentTask) return;
    syncPlanFromView();
    reviewDirty = JSON.stringify(cleanPlanForSend(currentPlan)) !== JSON.stringify(currentTask.plan);
    refreshReviewControls();
}

function applyTask(task, restore) {
    if (!task || !task.task_id) return;
    var changedTask = !currentTask || task.task_id !== currentTask.task_id;
    currentTask = JSON.parse(JSON.stringify(task));
    if (restore || changedTask || !currentPlan) {
        document.getElementById('params-fields').replaceChildren();
        currentPlan = task.plan ? JSON.parse(JSON.stringify(task.plan)) : null;
        reviewDirty = false;
        if (currentPlan) {
            enterPlanPhase(currentPlan.name);
            loadParamsPanel();
        }
    }
    reportReady = Boolean(task.report);
    reportGenerating = ['diagnosing', 'reporting'].includes(task.state);
    if (task.report) document.getElementById('report-content').textContent = task.report;
    renderDiagnosis(task.diagnosis, task.state);
    if (['executing', 'diagnosing', 'diagnostic_failed', 'reporting', 'report_failed', 'done', 'stopped', 'execution_uncertain'].includes(task.state)) {
        setTestState(task.state === 'executing' ? testState === 'paused' ? 'paused' : 'running' : 'idle');
        if (restore || changedTask) PhaseManager.goTo(task.report ? 'report' : 'execute');
        if (!['executing', 'diagnosing'].includes(task.state)) ModuleTracker.showDoneActions();
    }
    if (task.error) {
        var error = document.getElementById('api-error');
        error.textContent = task.error;
        error.hidden = false;
    }
    if (reportReady && reportUserWaiting) {
        reportUserWaiting = false;
        PhaseManager.goTo('report');
    }
    refreshReviewControls();
    syncReportButton();
}

async function saveTaskDraft() {
    if (!currentTask || !currentPlan) return false;
    syncPlanFromView();
    var data = await apiFetch('/api/update-plan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({plan: cleanPlanForSend(currentPlan),
            task_id: currentTask.task_id, revision: currentTask.revision})
    });
    if (!data) return false;
    applyTask(data.task, false);
    reviewDirty = false;
    refreshReviewControls();
    return true;
}

async function reviewPlan(approved) {
    if (!await saveTaskDraft()) return;
    var data = await apiFetch('/api/review-plan', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({task_id: currentTask.task_id, revision: currentTask.revision,
            approved: approved, comment: document.getElementById('review-comment').value})
    });
    if (data) { applyTask(data.task, false); loadTasks(); }
}

async function loadTasks() {
    var tasks = await apiFetch('/api/tasks');
    if (!tasks) return;
    var list = document.getElementById('task-library');
    list.replaceChildren();
    tasks.forEach(function(task) {
        var button = document.createElement('button');
        button.className = 'task-item';
        var name = document.createElement('span');
        name.textContent = task.name;
        var state = document.createElement('small');
        state.textContent = (TASK_LABELS[task.state] || task.state) + ' · 版本 ' + task.revision;
        button.append(name, state);
        button.addEventListener('click', async function() {
            var data = await apiFetch('/api/load-task', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({task_id: task.task_id})
            });
            if (data) { await loadSkills(); applyTask(data.task, true); }
        });
        list.appendChild(button);
    });
}

async function restoreTask(restore) {
    var task = await apiFetch('/api/state');
    if (task && task.task_id) applyTask(task, restore);
}

async function initTaskReview() {
    document.getElementById('btn-approve-plan').addEventListener('click', function() { reviewPlan(true); });
    document.getElementById('btn-reject-plan').addEventListener('click', function() { reviewPlan(false); });
    document.getElementById('phase-plan').addEventListener('input', markPlanEdited);
    await restoreTask(true);
    await loadTasks();
    setInterval(function() {
        if (currentTask && ['planning', 'executing', 'diagnosing', 'reporting'].includes(currentTask.state)) restoreTask(false);
    }, 2000);
}
