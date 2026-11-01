// ── ParamsPanel: 设备参数面板 ──────────────────────────
var ParamsPanel = (function() {

    var FRIENDLY_LABELS = {
        com_port: '电源控制串口端口号',
        device_ip: '设备 IP 地址',
        ip: '设备 IP 地址',
        target_ip: '目标 IP 地址',
        host: '主机地址',
        port: '设备端口',
        baudrate: '波特率',
    };

    function friendlyLabel(key) {
        return FRIENDLY_LABELS[key] || key.replace(/_/g, ' ');
    }

    async function load() {
        var panel = document.getElementById('params-panel');
        var fields = document.getElementById('params-fields');

        var deviceParams = await apiFetch('/api/device-params');
        if (!deviceParams || !deviceParams.length) {
            panel.style.display = 'none';
            return;
        }

        fields.innerHTML = '';

        for (var i = 0; i < deviceParams.length; i++) {
            var param = deviceParams[i];
            var key = param.name;
            var value = param.value;

            var div = document.createElement('div');
            div.className = 'param-field full-width';

            var label = document.createElement('label');
            label.className = 'param-label';
            label.textContent = friendlyLabel(key);
            var badge = document.createElement('span');
            badge.className = 'param-required-badge';
            badge.textContent = '必填';
            label.appendChild(badge);

            var input = document.createElement('input');
            input.className = 'param-input';
            input.setAttribute('data-var', key);
            input.type = 'text';
            input.value = (value === null || value === undefined || value === '') ? '' : String(value);

            if (!input.value) {
                input.placeholder = '请填写...';
            }

            div.appendChild(label);
            div.appendChild(input);
            fields.appendChild(div);
        }

        if (fields.children.length) {
            panel.style.display = '';
            void panel.offsetWidth;
            panel.classList.add('visible');
        } else {
            panel.style.display = 'none';
        }
    }

    function collect() {
        var inputs = document.querySelectorAll('#params-fields .param-input');
        var vars = {};
        for (var i = 0; i < inputs.length; i++) {
            var key = inputs[i].getAttribute('data-var');
            var raw = inputs[i].value.trim();
            if (!raw) continue;
            var num = Number(raw);
            if (!isNaN(num) && raw !== '') {
                vars[key] = num;
            } else {
                vars[key] = raw;
            }
        }
        return vars;
    }

    function hide() {
        var panel = document.getElementById('params-panel');
        panel.classList.remove('visible');
        panel.style.display = 'none';
    }

    return {
        load: load,
        collect: collect,
        hide: hide
    };
})();

// 向后兼容：旧代码中直接调用的全局函数
function loadParamsPanel() { return ParamsPanel.load(); }
function collectParamsFromPanel() { return ParamsPanel.collect(); }
function hideParamsPanel() { return ParamsPanel.hide(); }
