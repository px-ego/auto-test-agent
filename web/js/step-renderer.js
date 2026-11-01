// ── StepRenderer: 步骤渲染 ─────────────────────────────
var StepRenderer = (function() {

    /**
     * 渲染整个计划视图
     */
    function renderPlanView(plan) {
        if (plan.steps) {
            return renderYamlPlanView(plan);
        }
        return '<p class="plan-desc">（无法识别的计划格式）</p>';
    }

    function renderYamlPlanView(plan) {
        var html = '';
        if (plan.name) {
            html += '<h2 class="plan-title" data-field="name">' + escapeHTML(plan.name) + '</h2>';
        }
        if (plan.description) {
            html += '<p class="plan-desc" data-field="description">' + escapeHTML(plan.description) + '</p>';
        }

        var steps = plan.steps || [];
        for (var i = 0; i < steps.length; i++) {
            html += renderStep(steps[i], i, 0, '');
        }

        if (!steps.length) {
            html += '<p class="plan-desc">（测试计划中暂无步骤）</p>';
        }
        return html;
    }

    // ── 按钮生成 ──────────────────────────────────────

    function buildStepActions(path, visibleIndex, siblingCount) {
        return '<span class="yaml-step-actions" data-path="' + path + '">'
            + '<button class="yaml-insert-btn" data-path="' + path + '" title="在此之后插入操作">+</button>'
            + '<button class="yaml-move-btn yaml-move-up" data-path="' + path + '" title="上移"' + (visibleIndex === 0 ? ' disabled' : '') + '>↑</button>'
            + '<button class="yaml-move-btn yaml-move-down" data-path="' + path + '" title="下移"' + (visibleIndex >= siblingCount - 1 ? ' disabled' : '') + '>↓</button>'
            + '<button class="yaml-edit-btn" data-path="' + path + '" title="编辑">✎</button>'
            + '<button class="yaml-delete-btn" data-path="' + path + '" title="删除">×</button>'
            + '</span>';
    }

    function buildModuleActions(path, visibleIndex, siblingCount) {
        return '<span class="yaml-step-actions" data-path="' + path + '">'
            + '<button class="yaml-insert-module-btn" data-path="' + path + '" title="在此之后插入测试模块">+</button>'
            + '<button class="yaml-move-btn yaml-move-up" data-path="' + path + '" title="上移"' + (visibleIndex === 0 ? ' disabled' : '') + '>↑</button>'
            + '<button class="yaml-move-btn yaml-move-down" data-path="' + path + '" title="下移"' + (visibleIndex >= siblingCount - 1 ? ' disabled' : '') + '>↓</button>'
            + '<button class="yaml-edit-btn" data-path="' + path + '" title="编辑模块名">✎</button>'
            + '<button class="yaml-delete-module-btn" data-path="' + path + '" title="删除模块">×</button>'
            + '</span>';
    }

    // ── 各 action 类型的渲染方法 ──────────────────────

    function renderGroup(step, index, depth, path, info) {
        var name = step.name || '';
        var subSteps = step.steps || [];
        var moduleActions = buildModuleActions(path, info.visibleIndex, info.siblingCount);
        var html = '<div class="test-group yaml-group" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<div class="yaml-group-header">';
        html += '<span class="yaml-collapse-toggle" data-collapse-path="' + path + '">&#9660;</span>';
        html += '<h3>' + escapeHTML((index + 1) + '. ' + name) + '</h3>';
        html += moduleActions;
        html += '</div>';
        html += '<div class="yaml-group-steps yaml-collapsible">';
        for (var i = 0; i < subSteps.length; i++) {
            html += renderStep(subSteps[i], i, depth + 1, path);
        }
        html += '</div>';
        html += '</div>';
        return html;
    }

    function renderRepeat(step, index, depth, path, stepActions) {
        var name = step.name || '';
        var count = step.count || 0;
        var subSteps = step.steps || [];
        var html = '<div class="yaml-repeat" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<div class="yaml-repeat-header">';
        html += '<span class="yaml-collapse-toggle" data-collapse-path="' + path + '">&#9660;</span>';
        html += '<span class="yaml-action-badge badge-repeat">循环</span> ';
        html += '<span>' + escapeHTML(name) + ' — 重复 </span>';
        html += '<input type="number" class="yaml-inline-input" data-field="count" value="' + escapeHTML(String(count)) + '" min="1">';
        html += '<span> 次</span>';
        html += stepActions;
        html += '</div>';
        html += '<div class="yaml-substeps yaml-collapsible">';
        for (var i = 0; i < subSteps.length; i++) {
            html += renderStep(subSteps[i], i, depth + 1, path);
        }
        html += '</div>';
        html += '</div>';
        return html;
    }

    function renderSkill(step, index, depth, path, stepActions) {
        var name = step.name || '';
        var skillName = step.skill || '';
        var isRecognized = !skillName || availableSkills.some(function(s) { return s.action === skillName; });
        var unrecClass = isRecognized ? '' : ' yaml-unrecognized';
        var html = '<div class="yaml-step yaml-skill' + unrecClass + '" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-skill">操作</span> ';
        html += '<span class="yaml-step-name">' + escapeHTML(name) + '</span>';
        if (skillName) {
            html += '<span class="yaml-skill-tag">(' + escapeHTML(skillName) + ')</span>';
        }
        if (!isRecognized) {
            html += '<span class="yaml-unrecognized-hint">无法识别</span>';
        }
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderWait(step, index, depth, path, stepActions) {
        var secMin = step.seconds_min != null ? step.seconds_min : (step.seconds || 0);
        var secMax = step.seconds_max != null ? step.seconds_max : secMin;
        var html = '<div class="yaml-step yaml-wait" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-wait">等待</span> ';
        html += '<span>等待 </span>';
        html += '<input type="number" class="yaml-inline-input" data-field="seconds_min" value="' + escapeHTML(String(secMin)) + '" min="0" step="0.5">';
        html += '<span> — </span>';
        html += '<input type="number" class="yaml-inline-input" data-field="seconds_max" value="' + escapeHTML(String(secMax)) + '" min="0" step="0.5">';
        html += '<span> 秒</span>';
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderTimerStart(step, index, depth, path, stepActions) {
        var timerName = step.timer || '';
        var html = '<div class="yaml-step yaml-timer" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-timer">计时</span> ';
        html += '<span class="yaml-step-name">开始计时: ' + escapeHTML(timerName) + '</span>';
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderTimerStop(step, index, depth, path, stepActions) {
        var timerName = step.timer || '';
        var label = step.accumulate ? '结束计时，累加: ' : '结束计时: ';
        var html = '<div class="yaml-step yaml-timer" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-timer">计时</span> ';
        html += '<span class="yaml-step-name">' + escapeHTML(label + timerName) + '</span>';
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderSummary(step, index, depth, path, stepActions) {
        var msg = (step.params && step.params.message) || '';
        var name = step.name || '';
        var html = '<div class="yaml-step yaml-summary" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-summary">统计</span> ';
        html += '<span class="yaml-step-name">' + escapeHTML(msg || name) + '</span>';
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderLog(step, index, depth, path, stepActions) {
        var msg = (step.params && step.params.message) || '';
        var name = step.name || '';
        var html = '<div class="yaml-step yaml-log" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-log">提示</span> ';
        html += '<span class="yaml-step-name">' + escapeHTML(msg || name) + '</span>';
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderAssert(step, index, depth, path, stepActions) {
        var assertMsg = step.message || '';
        var name = step.name || '';
        var html = '<div class="yaml-step yaml-assert" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-assert">验证</span> ';
        html += '<span class="yaml-step-name">' + escapeHTML(name) + '</span>';
        if (assertMsg) {
            html += '<span class="yaml-assert-msg">— ' + escapeHTML(assertMsg) + '</span>';
        }
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderLlmAnalyze(step, index, depth, path, stepActions) {
        var name = step.name || '';
        var html = '<div class="yaml-step yaml-llm" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-action-badge badge-llm">AI 分析</span> ';
        html += '<span class="yaml-step-name">' + escapeHTML(name) + '</span>';
        html += stepActions;
        html += '</div>';
        return html;
    }

    function renderDefault(step, index, depth, path, stepActions) {
        var name = step.name || step.action || '';
        var html = '<div class="yaml-step" data-step-path="' + index + '" data-path="' + path + '">';
        html += '<span class="yaml-step-name">' + escapeHTML(name) + '</span>';
        html += stepActions;
        html += '</div>';
        return html;
    }

    // ── 渲染分发 ──────────────────────────────────────

    var renderers = {
        'group':        renderGroup,
        'repeat':       renderRepeat,
        'skill':        renderSkill,
        'wait':         renderWait,
        'timer_start':  renderTimerStart,
        'timer_stop':   renderTimerStop,
        'summary':      renderSummary,
        'log':          renderLog,
        'assert':       renderAssert,
        'llm_analyze':  renderLlmAnalyze
    };

    /**
     * 渲染单个步骤（递归入口）
     */
    function renderStep(step, index, depth, parentPath) {
        var action = step.action || '';
        var path = parentPath ? parentPath + '.' + index : String(index);

        // 隐藏的内部步骤
        if (StepOperations.HIDDEN_ACTIONS.indexOf(action) >= 0) {
            return '';
        }

        var info = StepOperations.getVisibleInfo(parentPath, index);
        var stepActions = buildStepActions(path, info.visibleIndex, info.siblingCount);

        // group 有自己的按钮，单独处理
        if (action === 'group') {
            return renderGroup(step, index, depth, path, info);
        }

        var renderer = renderers[action];
        if (renderer) {
            return renderer(step, index, depth, path, stepActions);
        }
        return renderDefault(step, index, depth, path, stepActions);
    }

    // Public API
    return {
        renderPlanView: renderPlanView,
        renderStep: renderStep
    };
})();
