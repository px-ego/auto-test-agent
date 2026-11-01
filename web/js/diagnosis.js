const DIAGNOSIS_LABELS = {
    running: '诊断中', completed: '诊断完成，待人工验证', limited: '已达到诊断限制',
    unavailable: '诊断模型不可用', stopped: '诊断已停止', disabled: '自动诊断已关闭'
};

function renderDiagnosis(diagnosis, taskState) {
    if (!diagnosis && taskState === 'diagnostic_failed') {
        diagnosis = {status: 'running', rounds: 0, max_rounds: 0, tool_calls: 0,
            trace: [], evidence: [], conclusion: null};
    }
    var panel = document.getElementById('diagnosis-panel');
    panel.hidden = !diagnosis;
    document.getElementById('btn-show-diagnosis').hidden = !diagnosis;
    if (!diagnosis) return;
    var interrupted = taskState === 'diagnostic_failed';
    document.getElementById('diagnosis-status').textContent = (interrupted ? '诊断已中断' : DIAGNOSIS_LABELS[diagnosis.status] || diagnosis.status)
        + (diagnosis.max_rounds ? ' · ' + diagnosis.rounds + '/' + diagnosis.max_rounds + ' 轮 · ' + diagnosis.tool_calls + ' 次检查' : '');
    document.getElementById('btn-stop-diagnosis').hidden = taskState !== 'diagnosing';
    document.getElementById('btn-resume-diagnosis').hidden = !interrupted;
    var conclusion = diagnosis.conclusion;
    document.getElementById('diagnosis-summary').textContent = conclusion ? conclusion.summary : '';
    var findings = document.getElementById('diagnosis-findings');
    findings.replaceChildren();
    (conclusion ? conclusion.findings : []).forEach(function(finding) {
        var item = document.createElement('li');
        item.textContent = '可能原因：' + finding.cause + '（' + finding.evidence_ids.join(', ') + '）';
        findings.appendChild(item);
    });
    var recommendations = document.getElementById('diagnosis-recommendations');
    recommendations.replaceChildren();
    (conclusion ? conclusion.recommendations : []).forEach(function(text) {
        var item = document.createElement('li');
        item.textContent = text;
        recommendations.appendChild(item);
    });
    var trace = document.getElementById('diagnosis-trace');
    trace.replaceChildren();
    var labels = {requested: '准备检查', completed: '已检查', blocked: '已拦截', model_error: '模型异常', tool_error: '检查异常'};
    diagnosis.trace.forEach(function(turn) {
        var item = document.createElement('li');
        item.textContent = '第 ' + turn.round + ' 轮 · ' + (turn.tool || '决策') + ' · '
            + (labels[turn.status] || turn.status) + (turn.reason ? '：' + turn.reason : '')
            + (turn.error ? '：' + turn.error : '');
        trace.appendChild(item);
    });
    var evidence = document.getElementById('diagnosis-evidence');
    evidence.replaceChildren();
    diagnosis.evidence.forEach(function(record) {
        var details = document.createElement('details');
        var summary = document.createElement('summary');
        summary.textContent = record.id + ' · ' + record.tool + (record.success ? '' : ' · 检查失败');
        var content = document.createElement('pre');
        content.textContent = record.content;
        details.append(summary, content);
        evidence.appendChild(details);
    });
}

async function resumeDiagnosis() {
    if (!currentTask) return;
    var result = await apiFetch('/api/resume-diagnosis', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({task_id: currentTask.task_id})
    });
    if (result) await restoreTask(false);
}

function initDiagnosis() {
    document.getElementById('btn-stop-diagnosis').addEventListener('click', stopTest);
    document.getElementById('btn-resume-diagnosis').addEventListener('click', resumeDiagnosis);
    document.getElementById('btn-show-diagnosis').addEventListener('click', function() {
        PhaseManager.goTo('execute');
    });
}
