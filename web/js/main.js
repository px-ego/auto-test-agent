// ── WebSocket ─────────────────────────────────────────
function initWebSocket() {
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        addLog('已连接到测试服务', 'success');
        restoreTask(false);
    };

    ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        handleWSMessage(msg);
    };

    ws.onerror = () => {
        addLog('WebSocket 连接异常', 'error');
    };

    ws.onclose = () => {
        addLog('连接已断开，3秒后重连...', 'warning');
        setTimeout(initWebSocket, 3000);
    };
}

function handleWSMessage(msg) {
    switch (msg.type) {
        case 'diagnosis_updated':
            if (currentTask && currentTask.task_id === msg.task_id) {
                currentTask.diagnosis = msg.diagnosis;
                renderDiagnosis(msg.diagnosis, currentTask.state);
            }
            break;
        case 'task_updated':
            applyTask(msg.task, false);
            loadTasks();
            break;
        case 'task_progress':
            if (currentTask && msg.task_id === currentTask.task_id) {
                currentTask.state = msg.state;
                reportGenerating = ['diagnosing', 'reporting'].includes(msg.state);
                renderDiagnosis(currentTask.diagnosis, msg.state);
                refreshReviewControls();
                syncReportButton();
            }
            break;
        case 'execution_started':
            // Clear log and module cards when execution actually starts
            document.getElementById('log-list').innerHTML = '';
            ModuleTracker.reset();
            updateProgressBar(0);
            addLog('测试执行开始' + (msg.total_modules ? '，共 ' + msg.total_modules + ' 个测试模块' : ''), 'info');
            if (msg.total_modules) ModuleTracker.setTotal(msg.total_modules);
            break;

        case 'module_started':
            addLog('━━ 模块 ' + msg.module_index + '/' + msg.total_modules + ': ' + msg.name + ' (' + msg.total_steps + ' 步) ━━', 'info');
            ModuleTracker.startModule(msg.module_index, msg.total_modules, msg.name, msg.total_steps);
            break;

        case 'module_completed': {
            const status = msg.passed ? '通过' : '失败';
            const logType = msg.passed ? 'success' : 'error';
            addLog('━━ 模块 ' + msg.module_index + '/' + msg.total_modules + ': ' + msg.name + ' — ' + status + ' ━━', logType);
            ModuleTracker.completeModule(msg.module_index, msg.total_modules, msg.name, msg.passed);
            if (msg.total_modules > 0) {
                updateProgressBar(Math.round((msg.module_index / msg.total_modules) * 100));
            }
            break;
        }

        case 'step_started': {
            const name = msg.name || ('步骤 ' + msg.step);
            const actionLabel = msg.action ? ' [' + msg.action + ']' : '';
            const indent = '  ' + '    '.repeat(msg.depth || 0);
            if (msg.step > 0) {
                addLog(indent + '▸ [' + msg.step + '/' + msg.total_steps + '] ' + name + actionLabel, 'info');
            } else {
                addLog(indent + '▸ ' + name + actionLabel, 'info');
            }
            ModuleTracker.startStep(msg.module_index, msg.step, msg.total_steps, name, msg.depth);
            break;
        }

        case 'step_completed': {
            const name = msg.name || ('步骤 ' + msg.step);
            const indent = '  ' + '    '.repeat(msg.depth || 0);
            if (msg.step > 0) {
                addLog(indent + '✓ [' + msg.step + '/' + msg.total_steps + '] ' + name, 'success');
            } else {
                addLog(indent + '✓ ' + name, 'success');
            }
            ModuleTracker.completeStep(msg.module_index, msg.step, name, msg.depth);
            break;
        }

        case 'step_failed': {
            const indent = '  ' + '    '.repeat(msg.depth || 0);
            const name = msg.name || '步骤';
            if (msg.step > 0) {
                addLog(indent + '✗ [' + msg.step + '/' + msg.total_steps + '] ' + name + ' — ' + msg.error, 'error');
            } else {
                addLog(indent + '✗ ' + name + ' — ' + msg.error, 'error');
            }
            ModuleTracker.failStep(msg.module_index, msg.step, name, msg.depth);
            break;
        }

        case 'loop_progress':
            var loopTotal = msg.total || msg.max_iterations || 0;
            addLog('  ↻ ' + msg.name + ' — 第 ' + msg.iteration + '/' + loopTotal + ' 轮', 'info');
            ModuleTracker.updateLoop(msg.module_index, msg.name, msg.iteration, loopTotal);
            break;

        case 'assert_result': {
            const icon = msg.passed ? '✓' : '✗';
            const logType = msg.passed ? 'success' : 'error';
            const stepName = msg.name || '验证';
            if (msg.passed) {
                addLog('  ' + icon + ' ' + stepName + ' — 通过', logType);
            } else {
                addLog('  ' + icon + ' ' + stepName + ' — ' + (msg.message || '失败'), logType);
                // 断言失败时递增循环失败计数
                ModuleTracker.trackLoopFail(msg.module_index);
            }
            break;
        }

        case 'log':
            addLog('  📝 ' + msg.message, 'info');
            break;

        case 'all_completed':
            addLog('全部完成: ' + msg.summary.passed + '/' + msg.summary.total + ' 通过, ' + msg.summary.failed + ' 失败', 'info');
            updateProgressBar(100);
            setTestState('idle');
            ModuleTracker.showDoneActions();
            // 后台生成报告，不自动跳转
            reportGenerating = true;
            syncReportButton();
            break;

        case 'execution_paused':
            addLog('⏸ 测试已暂停', 'warning');
            setTestState('paused');
            ModuleTracker.pauseAll();
            break;

        case 'execution_resumed':
            addLog('▶ 测试已恢复', 'info');
            setTestState('running');
            ModuleTracker.resumeAll();
            break;

        case 'pipeline_progress': {
            const elapsed = msg.elapsed_seconds != null ? ' (' + msg.elapsed_seconds + 's)' : '';
            const phase = msg.phase;
            let logType = 'info';
            let icon = '⏳';
            if (phase === 'done') { logType = 'success'; icon = '✅'; }
            else if (phase === 'error') { logType = 'error'; icon = '❌'; }
            else if (phase === 'converting') { icon = '🔄'; }
            else if (phase === 'executing') { icon = '▶'; }
            else if (phase === 'validate') { icon = '🔍'; }
            else if (phase === 'start') { icon = '🚀'; }
            addLog(icon + ' ' + msg.message + elapsed, logType);
            break;
        }

        case 'plan_generated': {
            currentPlan = msg.plan;
            if (msg.task) applyTask(msg.task, false);
            // 恢复按钮状态
            var genBtn = document.getElementById('btn-generate-plan');
            genBtn.disabled = false;
            genBtn.textContent = '生成新测试计划';
            var regenBtn = document.getElementById('btn-regenerate-plan');
            regenBtn.disabled = false;
            regenBtn.textContent = '重新生成';
            // 展示计划
            enterPlanPhase(msg.plan.name || '新测试计划');
            addLog('测试计划已生成，等待审核', 'success');
            loadParamsPanel();
            break;
        }

        case 'error':
            addLog('错误: ' + msg.message, 'error');
            setTestState('idle');
            // 恢复生成按钮
            var genBtn2 = document.getElementById('btn-generate-plan');
            genBtn2.disabled = false;
            genBtn2.textContent = '生成新测试计划';
            var regenBtn2 = document.getElementById('btn-regenerate-plan');
            regenBtn2.disabled = false;
            regenBtn2.textContent = '重新生成';
            break;
    }
}

// ── UI Helpers ────────────────────────────────────────
function addLog(message, type) {
    type = type || 'info';
    const list = document.getElementById('log-list');
    const atBottom = list.scrollHeight - list.scrollTop - list.clientHeight < 30;
    const li = document.createElement('li');
    li.className = 'log-' + type;
    const time = new Date().toLocaleTimeString();
    li.textContent = '[' + time + '] ' + message;
    list.appendChild(li);
    if (atBottom) {
        list.scrollTop = list.scrollHeight;
    }
}

function updateProgressBar(percent) {
    document.getElementById('progress-bar').style.width = percent + '%';
}

function setTestState(state) {
    testState = state;
    var btnPause = document.getElementById('btn-pause-test');
    var btnResume = document.getElementById('btn-resume-test');
    var btnStop = document.getElementById('btn-stop-test');

    btnPause.style.display = state === 'running' ? '' : 'none';
    btnResume.style.display = state === 'paused' ? '' : 'none';
    btnStop.style.display = (state === 'running' || state === 'paused') ? '' : 'none';
}

function onReportButtonClick() {
    if (reportReady) {
        PhaseManager.goTo('report');
    } else if (reportGenerating) {
        // 标记用户在等，生成完自动跳转
        reportUserWaiting = true;
        syncReportButton();
    } else {
        // 异常：还没开始生成，立即触发
        generateReportInBackground();
        reportUserWaiting = true;
        syncReportButton();
    }
}

function syncReportButton() {
    var btn = document.getElementById('btn-view-report');
    if (!btn) return;
    if (currentTask && ['diagnosing', 'diagnostic_failed'].includes(currentTask.state)) {
        btn.textContent = currentTask.state === 'diagnosing' ? '诊断中...' : '诊断待继续';
        btn.disabled = true;
    } else if (reportReady) {
        btn.textContent = '查看报告';
        btn.disabled = false;
        btn.className = 'btn btn-primary btn-lg';
    } else if (reportUserWaiting) {
        btn.textContent = '报告生成中...';
        btn.disabled = true;
        btn.className = 'btn btn-ghost btn-lg';
    } else if (reportGenerating) {
        btn.textContent = '生成报告';
        btn.disabled = false;
        btn.className = 'btn btn-ghost btn-lg';
    } else {
        btn.textContent = '生成报告';
        btn.disabled = false;
        btn.className = 'btn btn-ghost btn-lg';
    }
}

// ── Phase Transitions ─────────────────────────────────
function enterPlanPhase(planName) {
    showPlanView(currentPlan);
    document.getElementById('plan-name-label').textContent = planName || '';
    updateStartBtnState();
    updateSaveButtons();
    PhaseManager.goTo('plan');
}

function updateStartBtnState() {
    var btnStart = document.getElementById('btn-start-test');
    // Start button: enabled when plan exists (YAML plan is always executable)
    refreshReviewControls();
}

function updateSaveButtons() {
    var btnSave = document.getElementById('btn-save-plan');
    var btnSaveAs = document.getElementById('btn-save-as-plan');

    // 如果有 _plan_id，显示"保存"按钮；否则只显示"另存为"
    if (currentPlan && currentPlan._plan_id) {
        btnSave.style.display = '';
        btnSaveAs.textContent = '另存为';
    } else {
        btnSave.style.display = 'none';
        btnSaveAs.textContent = '保存';
    }
}

// ── Drag & Drop ───────────────────────────────────────
function setupDragDrop() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');

    dropZone.addEventListener('click', () => {
        fileInput.click();
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });

    fileInput.addEventListener('change', (e) => {
        handleFiles(e.target.files);
        fileInput.value = '';
    });
}

function handleFiles(files) {
    for (const file of files) {
        if (file.name.match(/\.zip$/i)) {
            importPlanZip(file);
            continue;
        }
        if (!file.name.match(/\.md$/i)) {
            addLog('不支持的文件类型: ' + file.name, 'error');
            continue;
        }
        const reader = new FileReader();
        reader.onload = async (e) => {
            const content = e.target.result;
            const result = await uploadKnowledge(content, file.name);
            if (result && result.success) {
                addFileChip(file.name, true);
                addLog('已上传知识文档: ' + file.name, 'success');
                resetGenerateBtn();
                showGenerateBtn();
            }
        };
        reader.readAsText(file);
    }
}

function addFileChip(filename, removable) {
    const list = document.getElementById('file-list');
    const li = document.createElement('li');
    li.className = 'file-chip';
    li.innerHTML = '<span class="file-chip-icon">📄</span>' + escapeHTML(filename);

    if (removable) {
        var index = list.children.length;  // 当前索引（添加前）
        var btn = document.createElement('button');
        btn.className = 'file-chip-remove';
        btn.textContent = '×';
        btn.addEventListener('click', function(e) {
            e.stopPropagation();
            removeKnowledge(li);
        });
        li.appendChild(btn);
    }

    list.appendChild(li);

    // Compact the drop zone after first file
    document.getElementById('drop-zone').classList.add('compact');
}

async function removeKnowledge(chipEl) {
    var list = document.getElementById('file-list');
    var chips = Array.from(list.children);
    var index = chips.indexOf(chipEl);
    if (index < 0) return;

    var data = await apiFetch('/api/remove-knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ index: index })
    });

    if (data && data.success) {
        chipEl.remove();
        addLog('已移除知识文档', 'info');
        resetGenerateBtn();

        // 全部删完 → 恢复初始状态
        if (list.children.length === 0) {
            document.getElementById('drop-zone').classList.remove('compact');
            var actions = document.getElementById('prepare-actions');
            actions.classList.remove('visible');
            actions.style.display = 'none';
        }
    }
}

function resetGenerateBtn() {
    var btn = document.getElementById('btn-generate-plan');
    btn.disabled = false;
    btn.textContent = '生成新测试计划';
    var btn2 = document.getElementById('btn-regenerate-plan');
    btn2.disabled = false;
    btn2.textContent = '重新生成';
}

function showGenerateBtn() {
    var actions = document.getElementById('prepare-actions');
    if (actions.style.display === 'none') {
        actions.style.display = '';
        // Trigger fade-in
        void actions.offsetWidth;
        actions.classList.add('visible');
    }
}

// ── Export HTML Report ────────────────────────────────
function exportReportHTML() {
    const content = document.getElementById('report-content').textContent;
    if (!content) {
        addLog('没有可导出的报告', 'error');
        return;
    }
    const html = '<!DOCTYPE html><html><head><meta charset="UTF-8"><title>测试报告</title>'
        + '<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;line-height:1.8;}'
        + 'pre{background:#f5f5f5;padding:1rem;border-radius:6px;overflow-x:auto;}</style></head>'
        + '<body><h1>测试报告</h1><pre>' + escapeHTML(content) + '</pre></body></html>';

    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = '测试报告_' + new Date().toISOString().slice(0, 10) + '.html';
    a.click();
    URL.revokeObjectURL(url);
    addLog('报告已导出', 'success');
}

// ── Log Drawer Toggle ─────────────────────────────────
function setupLogDrawer() {
    var toggle = document.getElementById('log-drawer-toggle');
    var drawer = document.getElementById('log-drawer');
    toggle.addEventListener('click', function() {
        drawer.classList.toggle('open');
    });
}

// ── Button Bindings ───────────────────────────────────
function setupButtons() {
    // Prepare phase
    document.getElementById('btn-generate-plan').addEventListener('click', generatePlan);

    // Plan phase
    document.getElementById('btn-back-prepare').addEventListener('click', function() {
        PhaseManager.goTo('prepare');
    });
    document.getElementById('btn-save-plan').addEventListener('click', savePlan);
    document.getElementById('btn-save-as-plan').addEventListener('click', saveAsPlan);
    document.getElementById('btn-export-plan').addEventListener('click', exportPlan);
    document.getElementById('btn-regenerate-plan').addEventListener('click', regeneratePlan);
    document.getElementById('btn-start-test').addEventListener('click', startTest);

    // Execute phase
    document.getElementById('btn-pause-test').addEventListener('click', pauseTest);
    document.getElementById('btn-resume-test').addEventListener('click', resumeTest);
    document.getElementById('btn-stop-test').addEventListener('click', stopTest);
    document.getElementById('btn-view-report').addEventListener('click', function() {
        onReportButtonClick();
    });

    // Report phase
    document.getElementById('btn-export-html').addEventListener('click', exportReportHTML);
    document.getElementById('btn-new-round').addEventListener('click', resetAgent);

    // Log drawer
    setupLogDrawer();
}

// ── Initialize ────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
    PhaseManager.init();
    var config = await apiFetch('/api/config');
    if (config) WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.hostname}:${config.ws_port}`;
    await loadSkills();
    setupDragDrop();
    setupButtons();
    initDiagnosis();
    loadSavedPlans();
    updateStartBtnState();
    await initTaskReview();
    initWebSocket();
});
