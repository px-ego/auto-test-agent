// ── PlanEditor: 计划编辑器（薄编排层）─────────────────
//
// 职责：将 StepRenderer、StepOperations、StepEditor 串起来，
//       绑定事件委托，对外暴露 show / sync 两个入口。

var PlanEditor = (function() {

    var eventsBound = false;

    /**
     * 显示计划视图并绑定事件
     */
    function show(plan) {
        var editor = document.getElementById('plan-editor');
        editor.innerHTML = StepRenderer.renderPlanView(plan);
        editor.contentEditable = 'false';
        // 恢复折叠状态（从 step 数据读取）
        restoreCollapseState(editor, plan.steps || [], '');
        if (!eventsBound) {
            bindEvents(editor);
            eventsBound = true;
        }
        if (currentTask) markPlanEdited();
    }

    /**
     * 同步编辑器中 inline input 的值回 plan 数据
     */
    function sync() {
        if (!currentPlan || !currentPlan.steps) return;
        var view = document.getElementById('plan-editor');

        var titleEl = view.querySelector('.plan-title[data-field="name"]');
        if (titleEl) currentPlan.name = titleEl.textContent.trim();

        var descEl = view.querySelector('.plan-desc[data-field="description"]');
        if (descEl) currentPlan.description = descEl.textContent.trim();

        StepOperations.syncInputs(view, currentPlan.steps);

        // 同步参数面板的值到 plan.variables
        syncParamsToVariables();
    }

    /**
     * 同步参数面板的值到 plan.variables
     */
    function syncParamsToVariables() {
        var inputs = document.querySelectorAll('#params-fields .param-input');
        if (!inputs.length) return;

        if (!currentPlan.variables) {
            currentPlan.variables = {};
        }

        for (var i = 0; i < inputs.length; i++) {
            var key = inputs[i].getAttribute('data-var');
            var raw = inputs[i].value.trim();
            if (!raw) continue;
            var num = Number(raw);
            if (!isNaN(num) && raw !== '') {
                currentPlan.variables[key] = num;
            } else {
                currentPlan.variables[key] = raw;
            }
        }
    }

    // ── 折叠逻辑 ──────────────────────────────────────

    function applyCollapse(editor, path, collapsed) {
        var container = editor.querySelector('[data-path="' + path + '"]');
        if (!container) return;
        var body = container.querySelector(':scope > .yaml-collapsible');
        var toggle = container.querySelector(':scope > .yaml-group-header > .yaml-collapse-toggle, :scope > .yaml-repeat-header > .yaml-collapse-toggle');
        if (body) body.classList.toggle('collapsed', collapsed);
        if (toggle) toggle.classList.toggle('collapsed', collapsed);
    }

    function restoreCollapseState(editor, steps, parentPath) {
        for (var i = 0; i < steps.length; i++) {
            var step = steps[i];
            var path = parentPath ? parentPath + '.' + i : String(i);
            if (step._collapsed) {
                applyCollapse(editor, path, true);
            }
            if (step.steps) {
                restoreCollapseState(editor, step.steps, path);
            }
        }
    }

    function toggleCollapseByPath(editor, path) {
        var ref = StepOperations.resolveStepPath(path);
        if (ref.index < 0 || ref.index >= ref.steps.length) return;
        var step = ref.steps[ref.index];
        step._collapsed = !step._collapsed;
        applyCollapse(editor, path, step._collapsed);
    }

    // ── 事件绑定 ──────────────────────────────────────

    function bindEvents(editor) {
        // 折叠/展开
        editor.addEventListener('click', function(e) {
            var toggle = e.target.closest('.yaml-collapse-toggle');
            if (!toggle) return;
            var path = toggle.getAttribute('data-collapse-path');
            if (!path) return;
            toggleCollapseByPath(editor, path);
        });

        // 删除
        editor.addEventListener('click', function(e) {
            var delBtn = e.target.closest('.yaml-delete-btn, .yaml-delete-module-btn');
            if (!delBtn) return;
            var path = delBtn.getAttribute('data-path');
            if (!confirm('确定要删除这个步骤吗？')) return;
            if (StepOperations.deleteStep(path)) {
                show(currentPlan);
            }
        });

        // 上移 / 下移
        editor.addEventListener('click', function(e) {
            var moveBtn = e.target.closest('.yaml-move-up, .yaml-move-down');
            if (!moveBtn || moveBtn.disabled) return;
            var path = moveBtn.getAttribute('data-path');
            var direction = moveBtn.classList.contains('yaml-move-up') ? 'up' : 'down';
            var result = StepOperations.moveStep(path, direction);
            if (result.success) {
                show(currentPlan);
            }
        });

        // 编辑
        editor.addEventListener('click', function(e) {
            var editBtn = e.target.closest('.yaml-edit-btn');
            if (!editBtn) return;
            e.preventDefault();
            e.stopPropagation();

            var path = editBtn.getAttribute('data-path');
            if (!path) return;
            var ref = StepOperations.resolveStepPath(path);
            if (ref.index < 0 || ref.index >= ref.steps.length) return;

            var step = ref.steps[ref.index];
            var stepCopy = JSON.parse(JSON.stringify(step));

            StepEditor.showEditDialog(stepCopy, function() {
                Object.keys(stepCopy).forEach(function(key) {
                    step[key] = stepCopy[key];
                });
                show(currentPlan);
            });
        });

        // 插入步骤
        editor.addEventListener('click', function(e) {
            var insertBtn = e.target.closest('.yaml-insert-btn');
            if (!insertBtn) return;

            var oldMenu = document.querySelector('.yaml-add-menu');
            if (oldMenu) {
                var oldActions = document.querySelector('.yaml-step-actions.menu-open');
                if (oldActions) oldActions.classList.remove('menu-open');
                oldMenu.remove();
            }

            var path = insertBtn.getAttribute('data-path');
            var pathParts = path.split('.');
            var parentPath = pathParts.slice(0, -1).join('.');
            var insertIndex = parseInt(pathParts[pathParts.length - 1]) + 1;

            var ref = StepOperations.resolveStepPath(parentPath);
            var targetSteps;
            if (parentPath === '') {
                targetSteps = currentPlan.steps || [];
            } else {
                if (ref.index < 0 || ref.index >= ref.steps.length) return;
                var parentStep = ref.steps[ref.index];
                targetSteps = parentStep ? (parentStep.steps || []) : [];
            }

            var actionsContainer = insertBtn.closest('.yaml-step-actions');
            if (actionsContainer) actionsContainer.classList.add('menu-open');

            StepEditor.showAddMenu(insertBtn, targetSteps, insertIndex, parentPath, actionsContainer, function() {
                show(currentPlan);
            });
        });

        // 插入模块
        editor.addEventListener('click', function(e) {
            var insertModuleBtn = e.target.closest('.yaml-insert-module-btn');
            if (!insertModuleBtn) return;

            var path = insertModuleBtn.getAttribute('data-path');
            var insertIndex = parseInt(path) + 1;

            var moduleName = prompt('请输入测试模块名称：', '新测试模块');
            if (moduleName === null) return;
            moduleName = moduleName.trim() || '新测试模块';

            StepOperations.insertModule(insertIndex, moduleName);
            show(currentPlan);
        });
    }

    // Public API
    return {
        show: show,
        sync: sync
    };
})();

// 向后兼容：旧代码中直接调用的全局函数
function showPlanView(plan) { PlanEditor.show(plan); }
function syncPlanFromView() { PlanEditor.sync(); }
