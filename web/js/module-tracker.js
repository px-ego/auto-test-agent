// ── Module Tracker ────────────────────────────────────
const ModuleTracker = {
    modules: {},  // keyed by module_index
    totalModules: 0,

    reset() {
        this.modules = {};
        this.totalModules = 0;
        document.getElementById('module-cards').innerHTML = '';
        document.getElementById('execute-done-actions').style.display = 'none';
        this.updateSummary();
    },

    setTotal(total) {
        this.totalModules = total;
        this.updateSummary();
    },

    startModule(moduleIndex, totalModules, name, totalSteps) {
        this.totalModules = totalModules;
        this.modules[moduleIndex] = {
            name: name,
            status: 'running',
            totalSteps: totalSteps,
            steps: {},
            loop: null,       // {name, iteration, total}
            loopFails: 0,     // 循环内失败次数
        };
        this.renderCard(moduleIndex);
        this.updateSummary();
    },

    completeModule(moduleIndex, totalModules, name, passed) {
        if (!this.modules[moduleIndex]) {
            this.modules[moduleIndex] = { name: name, totalSteps: 0, steps: {}, loop: null, loopFails: 0 };
        }
        this.modules[moduleIndex].status = passed ? 'pass' : 'fail';
        // 保留循环统计用于结束后展示
        // loop_progress 在每轮开始时发出，iteration 表示"正在执行第 N 轮"
        // 所以实际已完成的轮数 = iteration - 1（当前轮被中断，未完成）
        // 如果模块正常通过（passed=true），说明当前轮也完成了，已完成 = iteration
        var loop = this.modules[moduleIndex].loop;
        if (loop) {
            this.modules[moduleIndex].loopTotal = loop.total;
            this.modules[moduleIndex].loopCompleted = passed ? loop.iteration : Math.max(0, loop.iteration - 1);
        }
        this.modules[moduleIndex].loop = null;
        this.renderCard(moduleIndex);
        this.updateSummary();
    },

    updateLoop(moduleIndex, name, iteration, total) {
        const mod = this.findCurrentModule(moduleIndex);
        if (!mod) return;
        mod.loop = { name: name, iteration: iteration, total: total };
        this.renderCard(this.findModuleIndex(mod));
    },

    trackLoopFail(moduleIndex) {
        const mod = this.findCurrentModule(moduleIndex);
        if (!mod || !mod.loop) return;
        // 同一轮循环内只计一次失败
        var curIter = mod.loop.iteration;
        if (mod._lastFailIter === curIter) return;
        mod._lastFailIter = curIter;
        mod.loopFails = (mod.loopFails || 0) + 1;
        this.renderCard(this.findModuleIndex(mod));
    },

    startStep(moduleIndex, stepNum, totalSteps, name, depth) {
        // Only show top-level steps (step>0) on cards; sub-steps go to log only
        if (!stepNum || stepNum <= 0 || (depth && depth > 0)) return;
        const mod = this.findCurrentModule(moduleIndex);
        if (!mod) return;
        mod.steps[stepNum] = { name: name, status: 'running' };
        this.renderCard(this.findModuleIndex(mod));
    },

    completeStep(moduleIndex, stepNum, name, depth) {
        if (!stepNum || stepNum <= 0 || (depth && depth > 0)) return;
        const mod = this.findCurrentModule(moduleIndex);
        if (!mod) return;
        if (mod.steps[stepNum]) {
            mod.steps[stepNum].status = 'done';
        } else {
            mod.steps[stepNum] = { name: name, status: 'done' };
        }
        this.renderCard(this.findModuleIndex(mod));
    },

    failStep(moduleIndex, stepNum, name, depth) {
        if (!stepNum || stepNum <= 0 || (depth && depth > 0)) return;
        const mod = this.findCurrentModule(moduleIndex);
        if (!mod) return;
        if (mod.steps[stepNum]) {
            mod.steps[stepNum].status = 'fail';
        } else {
            mod.steps[stepNum] = { name: name, status: 'fail' };
        }
        this.renderCard(this.findModuleIndex(mod));
    },

    pauseAll() {
        for (const key in this.modules) {
            const mod = this.modules[key];
            if (mod.status === 'running') {
                mod.status = 'paused';
                for (const sk in mod.steps) {
                    if (mod.steps[sk].status === 'running') {
                        mod.steps[sk].status = 'paused';
                    }
                }
                this.renderCard(key);
            }
        }
        this.updateSummary();
    },

    resumeAll() {
        for (const key in this.modules) {
            const mod = this.modules[key];
            if (mod.status === 'paused') {
                mod.status = 'running';
                for (const sk in mod.steps) {
                    if (mod.steps[sk].status === 'paused') {
                        mod.steps[sk].status = 'running';
                    }
                }
                this.renderCard(key);
            }
        }
        this.updateSummary();
    },

    findCurrentModule(moduleIndex) {
        // If moduleIndex is provided and exists, use it
        if (moduleIndex !== undefined && moduleIndex !== null && this.modules[moduleIndex]) {
            return this.modules[moduleIndex];
        }
        // Otherwise find the running module
        for (const key in this.modules) {
            if (this.modules[key].status === 'running') return this.modules[key];
        }
        return null;
    },

    findModuleIndex(mod) {
        for (const key in this.modules) {
            if (this.modules[key] === mod) return key;
        }
        return null;
    },

    renderCard(moduleIndex) {
        const mod = this.modules[moduleIndex];
        if (!mod) return;

        const container = document.getElementById('module-cards');
        let card = document.getElementById('mod-card-' + moduleIndex);

        if (!card) {
            card = document.createElement('div');
            card.id = 'mod-card-' + moduleIndex;
            card.className = 'module-card';
            container.appendChild(card);
        }

        card.className = 'module-card' + (mod.status ? ' status-' + mod.status : '');

        let badgeClass = 'badge-pending';
        let badgeText = '等待';
        if (mod.status === 'running') { badgeClass = 'badge-running'; badgeText = '执行中'; }
        else if (mod.status === 'paused') { badgeClass = 'badge-paused'; badgeText = '已暂停'; }
        else if (mod.status === 'pass') { badgeClass = 'badge-pass'; badgeText = '通过'; }
        else if (mod.status === 'fail') { badgeClass = 'badge-fail'; badgeText = '失败'; }

        // 循环进度条
        let loopHTML = '';
        if (mod.loop) {
            var pct = Math.round((mod.loop.iteration / mod.loop.total) * 100);
            // 从 name 中去掉可能包含的数字后缀（如"重复测量5次"→"重复测量"）
            var loopLabel = stripTrailingCount(mod.loop.name);
            loopHTML = '<div class="module-loop-progress">'
                + '<div class="module-loop-bar"><div class="module-loop-fill" style="width:' + pct + '%"></div></div>'
                + '<span class="module-loop-text">' + escapeHTML(loopLabel) + ' ' + mod.loop.iteration + '/' + mod.loop.total + '</span>';
            if (mod.loopFails > 0) {
                loopHTML += '<span class="module-loop-fails">' + mod.loopFails + ' 失败</span>';
            }
            loopHTML += '</div>';
        } else if ((mod.status === 'pass' || mod.status === 'fail') && mod.loopTotal) {
            // 循环结束后显示完整统计
            var completed = mod.loopCompleted || 0;
            var fails = mod.loopFails || 0;
            var successes = completed > fails ? completed - fails : 0;
            loopHTML = '<div class="module-loop-stats">'
                + '<span class="module-loop-stat">完成 ' + completed + '/' + mod.loopTotal + ' 轮</span>'
                + '<span class="module-loop-stat stat-success">' + successes + ' 成功</span>'
                + '<span class="module-loop-stat stat-fail">' + fails + ' 失败</span>'
                + '</div>';
        }

        let stepsHTML = '';
        const stepKeys = Object.keys(mod.steps).sort((a, b) => a - b);
        // Merge consecutive steps with identical names
        const merged = [];
        for (const sk of stepKeys) {
            const step = mod.steps[sk];
            const prev = merged.length ? merged[merged.length - 1] : null;
            if (prev && prev.name === step.name) {
                prev.status = step.status;
            } else {
                merged.push({ name: step.name, status: step.status });
            }
        }
        for (const step of merged) {
            let iconHTML = '<span class="step-icon">○</span>';
            let stepClass = 'module-step';
            if (step.status === 'running') {
                iconHTML = '<span class="step-icon"><span class="spinner"></span></span>';
                stepClass = 'module-step step-running';
            } else if (step.status === 'paused') {
                iconHTML = '<span class="step-icon">⏸</span>';
                stepClass = 'module-step step-paused';
            } else if (step.status === 'done') {
                iconHTML = '<span class="step-icon">✓</span>';
                stepClass = 'module-step step-done';
            } else if (step.status === 'fail') {
                iconHTML = '<span class="step-icon">✗</span>';
                stepClass = 'module-step step-fail';
            }
            stepsHTML += '<li class="' + stepClass + '">' + iconHTML + '<span>' + escapeHTML(stripTrailingCount(step.name) || '步骤') + '</span></li>';
        }

        card.innerHTML =
            '<div class="module-card-header">' +
                '<span class="module-card-name">' + escapeHTML(moduleIndex + '. ' + (mod.name || '')) + '</span>' +
                '<span class="module-card-badge ' + badgeClass + '">' + badgeText + '</span>' +
            '</div>' +
            loopHTML +
            '<ul class="module-steps">' + stepsHTML + '</ul>';

        // Scroll to running card
        if (mod.status === 'running') {
            card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    },

    updateSummary() {
        const keys = Object.keys(this.modules);
        let passed = 0, failed = 0, running = 0, paused = 0;
        for (const k of keys) {
            if (this.modules[k].status === 'pass') passed++;
            else if (this.modules[k].status === 'fail') failed++;
            else if (this.modules[k].status === 'running') running++;
            else if (this.modules[k].status === 'paused') paused++;
        }
        const total = this.totalModules || keys.length;
        const el = document.getElementById('execute-summary');
        if (el) {
            let text = '共 ' + total + ' 个模块 · ' + passed + ' 通过 · ' + failed + ' 失败';
            if (running) text += ' · ' + running + ' 执行中';
            if (paused) text += ' · ' + paused + ' 已暂停';
            el.textContent = text;
        }
    },

    showDoneActions() {
        document.getElementById('execute-done-actions').style.display = 'flex';
    }
};

/**
 * 去掉 name 末尾的数字+量词（如"重复测量5次"→"重复测量"，"循环测试10次"→"循环测试"）
 * 兼容中英文：匹配末尾的 数字+可选量词(次/轮/遍/回)
 */
function stripTrailingCount(name) {
    if (!name) return name;
    return name.replace(/\s*\d+\s*(次|轮|遍|回)?$/, '');
}
