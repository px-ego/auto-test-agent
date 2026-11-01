// ── StepEditor: 编辑弹窗 & 添加菜单 ───────────────────
var StepEditor = (function() {

    // ── 表单辅助 ──────────────────────────────────────

    function addFormField(container, label, id, value, type) {
        var field = document.createElement('div');
        field.className = 'yaml-edit-field';
        var lbl = document.createElement('label');
        lbl.className = 'yaml-edit-label';
        lbl.textContent = label;
        var input = document.createElement('input');
        input.className = 'yaml-edit-input';
        input.id = id;
        input.type = type || 'text';
        input.value = value;
        if (type === 'number') { input.min = '0'; input.step = 'any'; }
        field.appendChild(lbl);
        field.appendChild(input);
        container.appendChild(field);
    }

    function renderSkillParams(container, skillAction, currentParams) {
        container.innerHTML = '';
        var skillMeta = availableSkills.find(function(s) { return s.action === skillAction; });
        if (!skillMeta || !skillMeta.params) return;

        var params = skillMeta.params;
        var required = params.required || [];
        var optional = params.optional || {};
        if (required.length === 0 && Object.keys(optional).length === 0) return;

        var header = document.createElement('div');
        header.className = 'yaml-edit-label';
        header.style.marginTop = '0.5rem';
        header.style.marginBottom = '0.25rem';
        header.textContent = '技能参数';
        container.appendChild(header);

        for (var i = 0; i < required.length; i++) {
            var pName = required[i];
            var val = currentParams[pName] != null ? currentParams[pName] : '';
            var field = document.createElement('div');
            field.className = 'yaml-edit-field';
            var lbl = document.createElement('label');
            lbl.className = 'yaml-edit-label';
            lbl.innerHTML = escapeHTML(pName) + ' <span style="color:var(--red);font-size:0.7rem;">必填</span>';
            var input = document.createElement('input');
            input.className = 'yaml-edit-input';
            input.setAttribute('data-skill-param', pName);
            input.type = 'text';
            input.value = val;
            input.placeholder = pName;
            field.appendChild(lbl);
            field.appendChild(input);
            container.appendChild(field);
        }

        var optKeys = Object.keys(optional);
        for (var i = 0; i < optKeys.length; i++) {
            var pName = optKeys[i];
            var meta = optional[pName];
            var val = currentParams[pName] != null ? currentParams[pName] : (meta.default != null ? meta.default : '');
            var field = document.createElement('div');
            field.className = 'yaml-edit-field';
            var lbl = document.createElement('label');
            lbl.className = 'yaml-edit-label';
            var hint = meta.type ? ' (' + meta.type + ')' : '';
            if (meta.range) hint += ' [' + meta.range[0] + '~' + meta.range[1] + ']';
            lbl.innerHTML = escapeHTML(pName) + '<span style="color:var(--gray-400);font-size:0.7rem;margin-left:0.3rem;">' + escapeHTML(hint) + '</span>';
            var input = document.createElement('input');
            input.className = 'yaml-edit-input';
            input.setAttribute('data-skill-param', pName);
            input.type = (meta.type === 'int' || meta.type === 'float') ? 'number' : 'text';
            input.value = val;
            if (meta.default != null) input.placeholder = '默认: ' + meta.default;
            if (meta.type === 'number' || meta.type === 'int' || meta.type === 'float') {
                input.step = meta.type === 'int' ? '1' : 'any';
            }
            field.appendChild(lbl);
            field.appendChild(input);
            container.appendChild(field);
        }
    }

    function collectSkillParams(container) {
        var params = {};
        var inputs = container.querySelectorAll('[data-skill-param]');
        for (var i = 0; i < inputs.length; i++) {
            var key = inputs[i].getAttribute('data-skill-param');
            var raw = inputs[i].value.trim();
            if (!raw) continue;
            var num = Number(raw);
            if (!isNaN(num) && raw !== '') {
                params[key] = num;
            } else {
                params[key] = raw;
            }
        }
        return params;
    }

    // ── 编辑弹窗 ──────────────────────────────────────

    /**
     * 显示步骤编辑弹窗
     * @param {object} step - 步骤数据（深拷贝）
     * @param {function} onSave - 保存回调
     */
    function showEditDialog(step, onSave) {
        var old = document.querySelector('.yaml-edit-overlay');
        if (old) old.remove();

        var overlay = document.createElement('div');
        overlay.className = 'yaml-edit-overlay';

        var dialog = document.createElement('div');
        dialog.className = 'yaml-edit-dialog';

        var action = step.action || '';
        var title = action === 'group' ? '编辑测试模块' : '编辑步骤';
        dialog.innerHTML = '<div class="yaml-edit-dialog-title">' + escapeHTML(title) + '</div>';

        var form = document.createElement('div');
        form.className = 'yaml-edit-form';

        addFormField(form, '名称', 'edit-name', step.name || '', 'text');

        var skillParamsContainer = document.createElement('div');

        if (action === 'skill') {
            buildSkillForm(form, step, skillParamsContainer);
        } else if (action === 'wait') {
            var curMin = step.seconds_min != null ? step.seconds_min : (step.seconds || 0);
            var curMax = step.seconds_max != null ? step.seconds_max : curMin;
            addFormField(form, '最小秒数', 'edit-seconds-min', curMin, 'number');
            addFormField(form, '最大秒数', 'edit-seconds-max', curMax, 'number');
        } else if (action === 'repeat') {
            addFormField(form, '重复次数', 'edit-count', step.count || 1, 'number');
        } else if (action === 'timer_start' || action === 'timer_stop') {
            addFormField(form, '计时器名称', 'edit-timer', step.timer || '', 'text');
            if (action === 'timer_stop') {
                buildAccumulateField(form, step);
            }
        } else if (action === 'summary' || action === 'log') {
            var msg = (step.params && step.params.message) || '';
            addFormField(form, '消息内容', 'edit-message', msg, 'text');
        }

        form.appendChild(skillParamsContainer);
        dialog.appendChild(form);

        // 按钮行
        var btnRow = document.createElement('div');
        btnRow.className = 'yaml-edit-btn-row';

        var cancelBtn = document.createElement('button');
        cancelBtn.className = 'btn btn-ghost';
        cancelBtn.textContent = '取消';
        cancelBtn.addEventListener('click', function() { overlay.remove(); });

        var saveBtn = document.createElement('button');
        saveBtn.className = 'btn btn-primary';
        saveBtn.textContent = '保存';
        saveBtn.addEventListener('click', function() {
            applyFormToStep(step, action, skillParamsContainer);
            overlay.remove();
            if (onSave) onSave();
        });

        btnRow.appendChild(cancelBtn);
        btnRow.appendChild(saveBtn);
        dialog.appendChild(btnRow);

        overlay.appendChild(dialog);
        document.body.appendChild(overlay);

        overlay.addEventListener('click', function(e) {
            if (e.target === overlay) overlay.remove();
        });

        setTimeout(function() {
            var ni = document.getElementById('edit-name');
            if (ni) { ni.focus(); ni.select(); }
        }, 50);
    }

    function buildSkillForm(form, step, skillParamsContainer) {
        var skillField = document.createElement('div');
        skillField.className = 'yaml-edit-field';
        var skillLabel = document.createElement('label');
        skillLabel.className = 'yaml-edit-label';
        skillLabel.textContent = '技能';
        var skillSelect = document.createElement('select');
        skillSelect.className = 'yaml-edit-input';
        skillSelect.id = 'edit-skill';

        var currentSkill = step.skill || '';
        var hasMatch = false;
        for (var i = 0; i < availableSkills.length; i++) {
            var opt = document.createElement('option');
            opt.value = availableSkills[i].action;
            opt.textContent = (availableSkills[i].description || availableSkills[i].action) + ' (' + availableSkills[i].action + ')';
            if (availableSkills[i].action === currentSkill) {
                opt.selected = true;
                hasMatch = true;
            }
            skillSelect.appendChild(opt);
        }
        if (!hasMatch && currentSkill) {
            var opt = document.createElement('option');
            opt.value = currentSkill;
            opt.textContent = currentSkill + ' (未知)';
            opt.selected = true;
            skillSelect.insertBefore(opt, skillSelect.firstChild);
        }

        skillField.appendChild(skillLabel);
        skillField.appendChild(skillSelect);
        form.appendChild(skillField);

        renderSkillParams(skillParamsContainer, currentSkill, step.params || {});
        skillSelect.addEventListener('change', function() {
            renderSkillParams(skillParamsContainer, skillSelect.value, {});
        });

        // on_fail
        var failField = document.createElement('div');
        failField.className = 'yaml-edit-field';
        var failLabel = document.createElement('label');
        failLabel.className = 'yaml-edit-label';
        failLabel.textContent = '失败时';
        var failSelect = document.createElement('select');
        failSelect.className = 'yaml-edit-input';
        failSelect.id = 'edit-on-fail';
        var failOpts = [
            { value: 'abort', text: '中止模块 (abort)' },
            { value: 'continue', text: '继续执行 (continue)' },
        ];
        for (var i = 0; i < failOpts.length; i++) {
            var o = document.createElement('option');
            o.value = failOpts[i].value;
            o.textContent = failOpts[i].text;
            if ((step.on_fail || 'abort') === failOpts[i].value) o.selected = true;
            failSelect.appendChild(o);
        }
        failField.appendChild(failLabel);
        failField.appendChild(failSelect);
        form.appendChild(failField);
    }

    function buildAccumulateField(form, step) {
        var accField = document.createElement('div');
        accField.className = 'yaml-edit-field';
        var accLabel = document.createElement('label');
        accLabel.className = 'yaml-edit-label';
        accLabel.textContent = '累加模式';
        var accSelect = document.createElement('select');
        accSelect.className = 'yaml-edit-input';
        accSelect.id = 'edit-accumulate';
        var accOpts = [
            { value: 'false', text: '否 — 仅记录本次' },
            { value: 'true', text: '是 — 累加到 _total' },
        ];
        for (var i = 0; i < accOpts.length; i++) {
            var o = document.createElement('option');
            o.value = accOpts[i].value;
            o.textContent = accOpts[i].text;
            if (String(!!step.accumulate) === accOpts[i].value) o.selected = true;
            accSelect.appendChild(o);
        }
        accField.appendChild(accLabel);
        accField.appendChild(accSelect);
        form.appendChild(accField);
    }

    function applyFormToStep(step, action, skillParamsContainer) {
        var nameInput = document.getElementById('edit-name');
        if (nameInput) step.name = nameInput.value.trim() || step.name;

        if (action === 'skill') {
            var skillSelect = document.getElementById('edit-skill');
            if (skillSelect) step.skill = skillSelect.value;
            step.params = collectSkillParams(skillParamsContainer);
            var failSelect = document.getElementById('edit-on-fail');
            if (failSelect) {
                if (failSelect.value === 'abort') {
                    delete step.on_fail;
                } else {
                    step.on_fail = failSelect.value;
                }
            }
        } else if (action === 'wait') {
            var minInput = document.getElementById('edit-seconds-min');
            var maxInput = document.getElementById('edit-seconds-max');
            if (minInput) { var v = parseFloat(minInput.value); if (!isNaN(v) && v >= 0) step.seconds_min = v; }
            if (maxInput) { var v = parseFloat(maxInput.value); if (!isNaN(v) && v >= 0) step.seconds_max = v; }
            delete step.seconds;
        } else if (action === 'repeat') {
            var cntInput = document.getElementById('edit-count');
            if (cntInput) { var v = parseInt(cntInput.value); if (!isNaN(v) && v > 0) step.count = v; }
        } else if (action === 'timer_start' || action === 'timer_stop') {
            var timerInput = document.getElementById('edit-timer');
            if (timerInput) step.timer = timerInput.value.trim() || step.timer;
            if (action === 'timer_stop') {
                var accSelect = document.getElementById('edit-accumulate');
                if (accSelect) step.accumulate = accSelect.value === 'true';
            }
        } else if (action === 'summary' || action === 'log') {
            var msgInput = document.getElementById('edit-message');
            if (msgInput) {
                if (!step.params) step.params = {};
                step.params.message = msgInput.value;
            }
        }
    }

    // ── 添加步骤菜单 ─────────────────────────────────

    /**
     * 显示添加步骤的下拉菜单
     */
    function showAddMenu(anchorEl, targetSteps, insertIndex, parentPath, actionsContainer, onInserted) {
        var old = document.querySelector('.yaml-add-menu');
        if (old) old.remove();

        var menu = document.createElement('div');
        menu.className = 'yaml-add-menu';

        if (insertIndex === undefined) insertIndex = targetSteps.length;

        // 设备技能组
        if (availableSkills.length) {
            var skillLabel = document.createElement('div');
            skillLabel.className = 'yaml-add-menu-group-label';
            skillLabel.textContent = '设备技能';
            menu.appendChild(skillLabel);

            for (var i = 0; i < availableSkills.length; i++) {
                (function(sk) {
                    var item = document.createElement('button');
                    item.className = 'yaml-add-menu-item';
                    item.innerHTML = '<span class="menu-item-badge badge-skill">操作</span> '
                        + escapeHTML(sk.description || sk.action)
                        + '<span class="menu-skill-hint">' + escapeHTML(sk.action) + '</span>';
                    item.addEventListener('click', function() {
                        var newStep = { name: sk.description || sk.action, action: 'skill', skill: sk.action, params: {} };
                        targetSteps.splice(insertIndex, 0, newStep);
                        menu.remove();
                        if (actionsContainer) actionsContainer.classList.remove('menu-open');
                        if (onInserted) onInserted(newStep, insertIndex, parentPath);
                    });
                    menu.appendChild(item);
                })(availableSkills[i]);
            }
        }

        // 分隔线
        var divider = document.createElement('div');
        divider.className = 'yaml-add-menu-divider';
        menu.appendChild(divider);

        // 内置操作组
        var builtinLabel = document.createElement('div');
        builtinLabel.className = 'yaml-add-menu-group-label';
        builtinLabel.textContent = '内置操作';
        menu.appendChild(builtinLabel);

        var builtins = [
            { label: '等待', badge: 'badge-wait', badgeText: '等待', template: { name: '等待', action: 'wait', seconds_min: 3, seconds_max: 3 } },
            { label: '循环', badge: 'badge-repeat', badgeText: '循环', template: { name: '循环', action: 'repeat', count: 5, steps: [] } },
            { label: '开始计时', badge: 'badge-timer', badgeText: '计时', template: { name: '开始计时', action: 'timer_start', timer: 'timer1' } },
            { label: '结束计时', badge: 'badge-timer', badgeText: '计时', template: { name: '结束计时', action: 'timer_stop', timer: 'timer1', accumulate: false } },
            { label: '统计输出', badge: 'badge-summary', badgeText: '统计', template: { name: '统计', action: 'summary', params: { message: '' } } },
            { label: '日志提示', badge: 'badge-log', badgeText: '提示', template: { name: '提示', action: 'log', params: { message: '' } } },
        ];

        for (var i = 0; i < builtins.length; i++) {
            (function(b) {
                var item = document.createElement('button');
                item.className = 'yaml-add-menu-item';
                item.innerHTML = '<span class="menu-item-badge ' + b.badge + '">' + escapeHTML(b.badgeText) + '</span> ' + escapeHTML(b.label);
                item.addEventListener('click', function() {
                    var newStep = JSON.parse(JSON.stringify(b.template));
                    targetSteps.splice(insertIndex, 0, newStep);
                    menu.remove();
                    if (actionsContainer) actionsContainer.classList.remove('menu-open');
                    if (onInserted) onInserted(newStep, insertIndex, parentPath);
                });
                menu.appendChild(item);
            })(builtins[i]);
        }

        // 定位
        document.body.appendChild(menu);
        var rect = anchorEl.getBoundingClientRect();
        menu.style.position = 'fixed';
        menu.style.left = rect.left + 'px';
        menu.style.top = (rect.bottom + 4) + 'px';

        // 关闭逻辑
        var menuActive = true;
        var closeMenu = function(e) {
            if (menu.contains(e.target)) return;
            if (anchorEl.contains(e.target)) return;
            if (menuActive && document.body.contains(menu)) {
                menu.remove();
                if (actionsContainer) actionsContainer.classList.remove('menu-open');
                menuActive = false;
                document.removeEventListener('click', closeMenu);
            }
        };
        setTimeout(function() {
            if (menuActive) document.addEventListener('click', closeMenu);
        }, 100);
    }

    // Public API
    return {
        showEditDialog: showEditDialog,
        showAddMenu: showAddMenu
    };
})();
