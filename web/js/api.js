// ── API Calls ─────────────────────────────────────────

async function loadSkills() {
    const skills = await apiFetch('/api/skills');
    if (skills && Array.isArray(skills)) {
        availableSkills = skills;
        addLog('已加载 ' + skills.length + ' 个技能', 'info');
    }
}

async function uploadKnowledge(content, filename) {
    return await apiFetch('/api/upload-knowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: content, filename: filename })
    });
}

async function generatePlan() {
    const btn = document.getElementById('btn-generate-plan');
    btn.disabled = true;
    btn.textContent = '生成中...';
    addLog('正在生成测试计划...', 'info');

    const data = await apiFetch('/api/generate-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    });

    if (!data || !data.success) {
        btn.disabled = false;
        btn.textContent = '生成新测试计划';
        if (data) addLog('生成测试计划失败: ' + (data.error || '未知错误'), 'error');
    }
    // plan 会通过 WebSocket plan_generated 事件到达
}

async function regeneratePlan() {
    var btn = document.getElementById('btn-regenerate-plan');
    btn.disabled = true;
    btn.textContent = '生成中...';
    addLog('正在重新生成测试计划...', 'info');
    hideParamsPanel();

    const data = await apiFetch('/api/generate-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
    });

    if (!data || !data.success) {
        btn.disabled = false;
        btn.textContent = '重新生成';
        if (data) addLog('重新生成失败: ' + (data.error || '未知错误'), 'error');
    }
    // plan 会通过 WebSocket plan_generated 事件到达
}

async function savePlan() {
    syncPlanFromView();
    if (!currentPlan) {
        addLog('没有可保存的测试计划', 'error');
        return;
    }

    var planId = currentPlan._plan_id;
    if (!planId) {
        addLog('无法保存：计划没有关联的 plan_id', 'error');
        return;
    }

    var name = currentPlan.name || '未命名测试计划';
    var btn = document.getElementById('btn-save-plan');
    btn.disabled = true;
    btn.textContent = '保存中...';
    addLog('正在保存测试计划...', 'info');

    const data = await apiFetch('/api/save-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            plan: cleanPlanForSend(currentPlan),
            name: name,
            plan_id: planId
        })
    });

    btn.disabled = false;
    btn.textContent = '保存';

    if (data && data.success) {
        addLog('测试计划已更新: ' + name, 'success');
        loadSavedPlans();
    }
}

async function saveAsPlan() {
    syncPlanFromView();
    if (!currentPlan) {
        addLog('没有可保存的测试计划', 'error');
        return;
    }

    var defaultName = currentPlan.name || '未命名测试计划';
    // 如果没有 _plan_id，说明是新计划，直接提示输入名称
    var promptText = currentPlan._plan_id
        ? '请输入新测试计划名称：'
        : '请输入测试计划名称：';
    var defaultValue = currentPlan._plan_id
        ? defaultName + ' (副本)'
        : defaultName;

    var name = prompt(promptText, defaultValue);
    if (name === null) return;
    name = name.trim() || defaultValue;

    var btn = document.getElementById('btn-save-as-plan');
    btn.disabled = true;
    var originalText = btn.textContent;
    btn.textContent = '保存中...';
    addLog('正在保存测试计划...', 'info');

    const data = await apiFetch('/api/save-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            plan: cleanPlanForSend(currentPlan),
            name: name,
            plan_id: undefined  // 不传 plan_id，创建新计划
        })
    });

    btn.disabled = false;
    btn.textContent = originalText;

    if (data && data.success) {
        currentPlan.name = name;
        currentPlan._plan_id = data.plan_id;
        addLog('测试计划已保存: ' + name, 'success');
        loadSavedPlans();
        // 更新界面显示保存按钮
        updateSaveButtons();
    }
}

async function startTest() {
    // 同步用户在界面上的修改回 plan
    syncPlanFromView();

    // 检查是否有无法识别的 skill 操作
    var unrecognized = findUnrecognizedSkills(currentPlan.steps || []);
    if (unrecognized.length > 0) {
        var names = unrecognized.map(function(s) { return s.skill || s.name; }).join('、');
        alert('以下操作无法识别，请修改后再执行：\n\n' + names);
        return;
    }

    if (!await saveTaskDraft() || currentTask.state !== 'approved') return;

    // Collect device params
    var variables = collectParamsFromPanel();

    // Clear report state
    reportReady = false;
    reportGenerating = false;
    reportUserWaiting = false;

    const data = await apiFetch('/api/start-test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ variables: variables, task_id: currentTask.task_id, revision: currentTask.revision })
    });

    if (data && data.success) {
        setTestState('running');
        PhaseManager.goTo('execute');
        addLog('测试执行已启动...', 'info');
        // 自动展开详细日志
        var drawer = document.getElementById('log-drawer');
        if (drawer && !drawer.classList.contains('open')) {
            drawer.classList.add('open');
        }
    }
}

// 递归查找所有无法识别的 skill 步骤
function findUnrecognizedSkills(steps) {
    var result = [];
    for (var i = 0; i < steps.length; i++) {
        var step = steps[i];
        if (step.action === 'skill' && step.skill) {
            var found = availableSkills.some(function(s) { return s.action === step.skill; });
            if (!found) result.push(step);
        }
        if (step.steps) {
            result = result.concat(findUnrecognizedSkills(step.steps));
        }
    }
    return result;
}

async function stopTest() {
    await apiFetch('/api/stop-test', { method: 'POST' });
    addLog('正在停止测试...', 'warning');
}

async function pauseTest() {
    await apiFetch('/api/pause-test', { method: 'POST' });
}

async function resumeTest() {
    await apiFetch('/api/resume-test', { method: 'POST' });
}

async function generateReportInBackground() {
    if (reportGenerating || reportReady) return;
    if (!currentTask) return;
    if (currentTask.state !== 'report_failed') {
        await restoreTask(false);
        return;
    }
    reportGenerating = true;
    syncReportButton();

    const data = await apiFetch('/api/retry-report', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({task_id: currentTask.task_id})
    });
    if (data && data.success) {
        currentTask.state = 'reporting';
        return;
    }

    reportGenerating = false;
    if (data && data.success) {
        document.getElementById('report-content').textContent = data.report;
        reportReady = true;
        addLog('测试报告已生成', 'success');
        syncReportButton();
        // 用户之前点过按钮在等 → 直接跳转
        if (reportUserWaiting) {
            reportUserWaiting = false;
            PhaseManager.goTo('report');
        }
    } else if (data) {
        addLog('报告生成失败: ' + (data.error || '未知错误'), 'error');
        syncReportButton();
    }
}

async function resetAgent() {
    if (!await apiFetch('/api/reset', { method: 'POST' })) return;
    currentPlan = null;
    currentTask = null;
    renderDiagnosis(null);
    reviewDirty = false;
    reportReady = false;
    reportGenerating = false;
    reportUserWaiting = false;
    document.getElementById('plan-editor').innerHTML = '';
    document.getElementById('module-cards').innerHTML = '';
    document.getElementById('log-list').innerHTML = '';
    document.getElementById('report-content').textContent = '';
    document.getElementById('file-list').innerHTML = '';
    // Hide generate button and restore drop zone
    var actions = document.getElementById('prepare-actions');
    actions.style.display = 'none';
    actions.classList.remove('visible');
    document.getElementById('drop-zone').classList.remove('compact');
    hideParamsPanel();
    updateProgressBar(0);
    setTestState('idle');
    updateStartBtnState();
    PhaseManager.reset();
    loadSavedPlans();
    loadTasks();
    addLog('已重置', 'info');
}

// ── Plan Library ──────────────────────────────────────
async function loadSavedPlans() {
    const plans = await apiFetch('/api/plans');
    if (plans) {
        renderPlanList(plans);
    }
}

function renderPlanList(plans) {
    var library = document.getElementById('plan-library');
    library.innerHTML = '';

    if (!plans.length) {
        library.innerHTML = '<div class="plan-library-empty">暂无已保存的测试计划</div>';
        return;
    }

    for (var i = 0; i < plans.length; i++) {
        var p = plans[i];
        var item = document.createElement('div');
        item.className = 'plan-grid-item';
        item.setAttribute('data-plan-id', p.plan_id);

        var info = document.createElement('div');
        info.className = 'plan-grid-item-info';

        var name = document.createElement('div');
        name.className = 'plan-grid-item-name';
        name.textContent = p.name || '未命名测试计划';

        var date = document.createElement('div');
        date.className = 'plan-grid-item-date';
        date.textContent = new Date(p.created_at * 1000).toLocaleString();

        info.appendChild(name);
        info.appendChild(date);

        var del = document.createElement('button');
        del.className = 'plan-grid-item-delete';
        del.textContent = '删除';
        del.setAttribute('data-plan-id', p.plan_id);
        del.addEventListener('click', (function(planId) {
            return function(e) {
                e.stopPropagation();
                deleteSavedPlan(planId);
            };
        })(p.plan_id));

        item.appendChild(info);
        item.appendChild(del);

        item.addEventListener('click', (function(planId, planName) {
            return function() {
                loadSavedPlan(planId, planName);
            };
        })(p.plan_id, p.name));

        library.appendChild(item);
    }
}

async function loadSavedPlan(planId, name) {
    addLog('正在加载测试计划...', 'info');
    var data = await apiFetch('/api/load-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: planId })
    });

    if (data && data.success) {
        currentPlan = data.plan;
        applyTask(data.task, false);
        // 记录 plan_id，保存时可以覆盖更新
        currentPlan._plan_id = planId;
        enterPlanPhase(name || data.plan.name || '已保存测试计划');
        addLog('测试计划已加载，可直接执行', 'success');
        loadParamsPanel();
    }
}

async function deleteSavedPlan(planId) {
    var data = await apiFetch('/api/delete-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_id: planId })
    });

    if (data && data.success) {
        addLog('测试计划已删除', 'info');
        loadSavedPlans();
    }
}

// ── Plan Export / Import ──────────────────────────────

async function exportPlan() {
    syncPlanFromView();
    if (!currentPlan) {
        addLog('没有可导出的测试计划', 'error');
        return;
    }

    try {
        const resp = await fetch(API_BASE + '/api/export-plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ plan: cleanPlanForSend(currentPlan) })
        });
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error('HTTP ' + resp.status + ': ' + text);
        }
        const blob = await resp.blob();
        // 从 Content-Disposition 提取文件名，fallback 用计划名
        var filename = (currentPlan.name || '测试计划') + '.zip';
        var disposition = resp.headers.get('Content-Disposition');
        if (disposition) {
            var match = disposition.match(/filename="?([^"]+)"?/);
            if (match) filename = decodeURIComponent(match[1]);
        }
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
        addLog('测试计划已导出: ' + filename, 'success');
    } catch (e) {
        alert('导出失败: ' + e.message);
        addLog('导出失败: ' + e.message, 'error');
    }
}

async function importPlanZip(file) {
    addLog('正在导入测试计划: ' + file.name + ' (' + file.size + ' bytes)', 'info');
    addFileChip('导入中: ' + file.name);

    try {
        const resp = await fetch(API_BASE + '/api/import-plan', {
            method: 'POST',
            body: file
        });
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error('HTTP ' + resp.status + ': ' + text);
        }
        const data = await resp.json();
        if (data && data.success) {
            currentPlan = data.plan;
            applyTask(data.task, false);
            // 导入的计划没有 plan_id，不设置 _plan_id（这样保存时会创建新计划）
            // 刷新技能列表
            await loadSkills();
            // 跳到计划页面
            enterPlanPhase(data.plan.name || '导入的测试计划');
            addLog('测试计划导入成功', 'success');
            loadParamsPanel();
        } else {
            alert('导入失败: ' + (data.error || '未知错误'));
            addLog('导入失败: ' + (data.error || '未知错误'), 'error');
        }
    } catch (e) {
        alert('导入失败: ' + e.message);
        addLog('导入失败: ' + e.message, 'error');
    }
}
