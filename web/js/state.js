// Configuration
const API_BASE = '';  // same origin
let WS_URL = `ws://${location.hostname}:8081`;

// State
let ws = null;
let currentPlan = null;
let currentTask = null;
let reviewDirty = false;
// (planConfirmed removed — YAML plan is always executable)
let testState = 'idle';  // 'idle' | 'running' | 'paused'
let availableSkills = [];  // [{action, description, params}, ...]
let reportReady = false;   // 报告是否已生成
let reportGenerating = false; // 报告是否正在生成中
let reportUserWaiting = false; // 用户是否在等待报告生成完跳转

// ── Utilities ─────────────────────────────────────────
function escapeHTML(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// 序列化 plan 时过滤掉 _ 开头的内部字段（如 _collapsed）
function cleanPlanForSend(plan) {
    return JSON.parse(JSON.stringify(plan, function(key, value) {
        return key.startsWith('_') ? undefined : value;
    }));
}

async function apiFetch(url, options) {
    try {
        const resp = await fetch(API_BASE + url, options);
        if (!resp.ok) {
            const payload = await resp.json();
            var detail = (payload.details || []).map(function(item) {
                return item.loc.join('.') + ': ' + item.msg;
            }).join('; ');
            throw new Error((payload.error || ('HTTP ' + resp.status)) + (detail ? ': ' + detail : ''));
        }
        document.getElementById('api-error').hidden = true;
        return await resp.json();
    } catch (e) {
        addLog('请求失败 (' + url + '): ' + e.message, 'error');
        var error = document.getElementById('api-error');
        error.textContent = e.message;
        error.hidden = false;
        return null;
    }
}
