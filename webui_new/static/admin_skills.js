(function () {
    'use strict';
    const token = localStorage.getItem('hommey.access_token');
    const app = document.getElementById('app');
    const error = document.getElementById('error');
    let state = { skills: [], graph: {}, runs: [] };

    document.addEventListener('DOMContentLoaded', load);

    async function api(path, options = {}) {
        const response = await fetch(path, {
            ...options,
            headers: { 'Authorization': `Bearer ${token || ''}`, 'Content-Type': 'application/json', ...(options.headers || {}) },
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error?.message || '请求失败');
        return data;
    }

    async function load() {
        if (!token) return fail('请先以管理员身份登录。');
        try {
            state = await api('/api/admin/skills');
            app.hidden = false;
            error.textContent = '';
            renderList(); renderGraph(); renderRuns();
            if (state.skills.length) selectSkill(state.skills[0].name);
        } catch (exc) { fail(exc.message); }
    }

    function fail(message) { app.hidden = true; error.textContent = message; }

    function renderList() {
        const list = document.getElementById('skillList');
        list.replaceChildren();
        document.getElementById('skillCount').textContent = `${state.skills.length} 个`;
        state.skills.forEach((skill) => {
            const card = document.createElement('article');
            card.className = 'skill-card'; card.dataset.name = skill.name;
            const top = document.createElement('div'); top.className = 'skill-top';
            const title = document.createElement('strong'); title.textContent = skill.display_name;
            const badge = document.createElement('span'); badge.className = `badge ${skill.enabled ? 'on' : ''}`; badge.textContent = skill.enabled ? '已启用' : '已停用';
            const id = document.createElement('div'); id.className = 'meta'; id.textContent = `${skill.name} · v${skill.version} · ${skill.category}`;
            top.append(title, badge); card.append(top, id); card.addEventListener('click', () => selectSkill(skill.name)); list.appendChild(card);
        });
    }

    async function selectSkill(name) {
        document.querySelectorAll('.skill-card').forEach((item) => item.classList.toggle('active', item.dataset.name === name));
        const skill = await api(`/api/admin/skills/${encodeURIComponent(name)}`);
        const detail = document.getElementById('skillDetail'); detail.replaceChildren();
        const title = document.createElement('h2'); title.textContent = skill.display_name;
        const desc = document.createElement('p'); desc.className = 'meta'; desc.textContent = skill.description;
        const grid = document.createElement('div'); grid.className = 'detail-grid';
        grid.append(metric('标识', skill.name), metric('版本', skill.version), metric('风险', skill.risk_level), metric('工具', (skill.tools || []).join('、') || '无'), metric('运行次数', skill.metrics.runs), metric('平均耗时', skill.metrics.average_duration_ms == null ? '暂无' : `${skill.metrics.average_duration_ms}ms`));
        const toggle = document.createElement('button'); toggle.className = skill.enabled ? 'off' : ''; toggle.textContent = skill.enabled ? '停用 Skill' : '启用 Skill';
        toggle.addEventListener('click', async () => { await api(`/api/admin/skills/${encodeURIComponent(name)}/enabled`, { method:'PATCH', body:JSON.stringify({ enabled: !skill.enabled }) }); await load(); });
        const heading = document.createElement('h3'); heading.textContent = '运行指令'; heading.style.marginTop = '18px';
        const pre = document.createElement('pre'); pre.textContent = skill.instructions || '无';
        detail.append(title, desc, grid, toggle, heading, pre);
    }

    function metric(label, value) { const box=document.createElement('div'); box.className='metric'; const small=document.createElement('span'); small.className='meta'; small.textContent=label; const strong=document.createElement('strong'); strong.textContent=value ?? '-'; box.append(small,strong); return box; }

    function renderGraph() {
        const graph = document.getElementById('graph'); graph.replaceChildren();
        const edges = state.graph.edges || [];
        if (!edges.length) { graph.textContent = '暂无组合依赖。'; return; }
        edges.forEach((edge) => { const row=document.createElement('div'); row.className='graph-row'; row.append(node(edge.source), text('→','arrow'), node(edge.target), text(edge.purpose || '','meta')); graph.appendChild(row); });
    }
    function node(value) { return text(value,'node'); }
    function text(value, className) { const el=document.createElement('span'); el.className=className; el.textContent=value; return el; }

    function renderRuns() {
        const root=document.getElementById('runs'); root.replaceChildren();
        if (!state.runs.length) { root.textContent='暂无执行记录；配置 PostgreSQL 并运行 Skill 后会显示。'; return; }
        state.runs.forEach((run) => { const row=document.createElement('div'); row.className='run'; row.append(text(run.skill_name,''), text(run.status,''), text(`${run.duration_ms || 0}ms`,''), text(String(run.started_at || ''),'')); root.appendChild(row); });
    }
}());
