// ── StepOperations: plan 树的数据操作 ──────────────────
var StepOperations = (function() {

    // 不在编辑器中显示的 action 类型
    var HIDDEN_ACTIONS = ['set_variable', 'if', 'assert'];

    /**
     * 根据 path（如 "0.2.1"）找到 plan 中对应的 steps 数组和 index
     * 返回 { steps: 父级steps数组, index: 当前索引 }
     */
    function resolveStepPath(path) {
        if (!path || path === '') {
            return { steps: currentPlan.steps || [], index: -1 };
        }
        var parts = path.split('.').map(Number);
        var steps = currentPlan.steps || [];
        for (var i = 0; i < parts.length - 1; i++) {
            var step = steps[parts[i]];
            if (!step) return { steps: [], index: -1 };
            steps = step.steps || [];
        }
        return { steps: steps, index: parts[parts.length - 1] };
    }

    /**
     * 删除指定 path 的步骤，返回是否成功
     */
    function deleteStep(path) {
        var ref = resolveStepPath(path);
        if (ref.index < 0 || ref.index >= ref.steps.length) return false;
        ref.steps.splice(ref.index, 1);
        return true;
    }

    /**
     * 移动步骤（上移或下移），跳过隐藏步骤
     * 返回 { success, swapIdx } 或 { success: false }
     */
    function moveStep(path, direction) {
        var ref = resolveStepPath(path);
        var idx = ref.index;
        var arr = ref.steps;
        if (idx < 0 || idx >= arr.length) return { success: false };

        var swapIdx = idx;
        if (direction === 'up') {
            for (var i = idx - 1; i >= 0; i--) {
                if (HIDDEN_ACTIONS.indexOf(arr[i].action) < 0) {
                    swapIdx = i;
                    break;
                }
            }
        } else {
            for (var i = idx + 1; i < arr.length; i++) {
                if (HIDDEN_ACTIONS.indexOf(arr[i].action) < 0) {
                    swapIdx = i;
                    break;
                }
            }
        }

        if (swapIdx === idx) return { success: false };

        var tmp = arr[idx];
        arr[idx] = arr[swapIdx];
        arr[swapIdx] = tmp;

        return { success: true, swapIdx: swapIdx };
    }

    /**
     * 在指定位置插入步骤
     */
    function insertStep(parentPath, insertIndex, newStep) {
        var targetSteps;
        if (!parentPath || parentPath === '') {
            if (!currentPlan.steps) currentPlan.steps = [];
            targetSteps = currentPlan.steps;
        } else {
            var ref = resolveStepPath(parentPath);
            if (ref.index < 0 || ref.index >= ref.steps.length) return null;
            var parentStep = ref.steps[ref.index];
            if (!parentStep.steps) parentStep.steps = [];
            targetSteps = parentStep.steps;
        }
        targetSteps.splice(insertIndex, 0, newStep);
        return targetSteps;
    }

    /**
     * 在指定位置插入新模块（group）
     */
    function insertModule(insertIndex, moduleName) {
        if (!currentPlan.steps) currentPlan.steps = [];
        var newModule = {
            name: moduleName,
            action: 'group',
            steps: []
        };
        currentPlan.steps.splice(insertIndex, 0, newModule);
        return newModule;
    }

    /**
     * 计算可见步骤信息（排除隐藏步骤后的索引和总数）
     * parentPath: 父步骤的 path（如 "0.1"），空字符串表示顶层
     * index: 当前步骤在父步骤 steps 数组中的真实索引
     */
    function getVisibleInfo(parentPath, index) {
        var siblingSteps;
        if (!parentPath || parentPath === '') {
            // 顶层步骤，兄弟就是 currentPlan.steps
            siblingSteps = currentPlan.steps || [];
        } else {
            // parentPath 指向一个父步骤（group/repeat 等），取它的 .steps
            var parentRef = resolveStepPath(parentPath);
            var parentStep = parentRef.steps[parentRef.index];
            siblingSteps = (parentStep && parentStep.steps) || [];
        }

        var siblingCount = siblingSteps.filter(function(s) {
            return HIDDEN_ACTIONS.indexOf(s.action) < 0;
        }).length;

        var visibleIndex = 0;
        for (var i = 0; i < index; i++) {
            if (siblingSteps[i] && HIDDEN_ACTIONS.indexOf(siblingSteps[i].action) < 0) {
                visibleIndex++;
            }
        }

        return {
            visibleIndex: visibleIndex,
            siblingCount: siblingCount,
            isFirst: visibleIndex === 0,
            isLast: visibleIndex >= siblingCount - 1
        };
    }

    /**
     * 同步 inline input 的值回 plan 数据
     */
    function syncInputs(container, steps) {
        for (var i = 0; i < steps.length; i++) {
            var step = steps[i];
            // 只查找直接子元素，避免匹配到嵌套的子步骤
            var stepEl = findDirectChild(container, i);
            if (!stepEl) continue;

            if (step.action === 'repeat') {
                var countInput = stepEl.querySelector(':scope > .yaml-repeat-header > input[data-field="count"]');
                if (countInput) {
                    var val = parseInt(countInput.value);
                    if (!isNaN(val) && val > 0) step.count = val;
                }
            }

            if (step.action === 'wait') {
                var minInput = stepEl.querySelector('input[data-field="seconds_min"]');
                var maxInput = stepEl.querySelector('input[data-field="seconds_max"]');
                if (minInput) {
                    var v = parseFloat(minInput.value);
                    if (!isNaN(v) && v >= 0) step.seconds_min = v;
                }
                if (maxInput) {
                    var v = parseFloat(maxInput.value);
                    if (!isNaN(v) && v >= 0) step.seconds_max = v;
                }
                delete step.seconds;
            }

            // 递归同步子步骤
            if (step.steps && step.steps.length > 0) {
                var subContainer = null;
                if (step.action === 'group') {
                    subContainer = stepEl.querySelector(':scope > .yaml-group-steps');
                } else if (step.action === 'repeat') {
                    subContainer = stepEl.querySelector(':scope > .yaml-substeps');
                }
                if (subContainer) {
                    syncInputs(subContainer, step.steps);
                }
            }
        }
    }

    /**
     * 查找容器的直接子元素中 data-step-path 为指定值的元素
     */
    function findDirectChild(container, stepPath) {
        var children = container.children;
        for (var i = 0; i < children.length; i++) {
            if (children[i].getAttribute('data-step-path') === String(stepPath)) {
                return children[i];
            }
        }
        return null;
    }

    // Public API
    return {
        HIDDEN_ACTIONS: HIDDEN_ACTIONS,
        resolveStepPath: resolveStepPath,
        deleteStep: deleteStep,
        moveStep: moveStep,
        insertStep: insertStep,
        insertModule: insertModule,
        getVisibleInfo: getVisibleInfo,
        syncInputs: syncInputs
    };
})();
