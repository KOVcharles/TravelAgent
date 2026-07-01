/**
 * Hommey WebUI
 * Keeps the real product logic: initialization, onboarding, streaming chat,
 * preference refresh, and quick prompts.
 */
(function () {
    'use strict';

    const userId = decodeURIComponent(window.location.pathname.split('/').pop() || '');
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    const initOverlay = document.getElementById('initOverlay');
    const panelName = document.getElementById('panelName');
    const panelLevel = document.getElementById('panelLevel');
    const prefList = document.getElementById('prefList');

    const assistantImage = '/static/assets/hommey-avatar.jpg';
    const defaultPlaceholder = '告诉 Hommey 你的出行需求，例如：下周一去上海出差两天';

    let isProcessing = false;
    let isOnboarding = false;
    let onboardingIndex = 0;
    let customInputCallback = null;

    const onboardingSteps = [
        {
            question: '先告诉我，你平时从哪个城市出发比较多？',
            key: 'home_location',
            hint: '之后规划行程时，我会优先按这个城市帮你计算出发方案。',
            options: ['北京', '上海', '广州', '深圳', '成都', '杭州', '其他'],
        },
        {
            question: '出差路上，你更偏好哪种交通方式？',
            key: 'transportation_preference',
            hint: '我会在时间、舒适度和预算之间替你做更贴近偏好的取舍。',
            options: ['高铁', '飞机', '自驾', '都可以', '其他'],
        },
        {
            question: '住宿方面，有固定喜欢的酒店或风格吗？',
            key: 'hotel_brands',
            hint: '品牌、安静程度、通勤距离都可以告诉我。',
            options: ['汉庭', '如家', '全季', '亚朵', '锦江之星', '其他'],
        },
        {
            question: '最后，座位或舱位有什么偏好吗？',
            key: 'seat_preference',
            hint: '如果没有固定偏好，我会优先选择更稳妥、性价比合适的方案。',
            options: ['商务座', '一等座', '二等座', '经济舱', '不指定', '其他'],
        },
    ];

    document.addEventListener('DOMContentLoaded', initialize);

    chatInput.addEventListener('input', resizeInput);
    chatInput.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' || event.shiftKey) return;
        event.preventDefault();
        submitCurrentInput();
    });
    sendBtn.addEventListener('click', submitCurrentInput);

    document.querySelectorAll('.quick-btn').forEach((button) => {
        button.addEventListener('click', () => {
            if (isOnboarding || isProcessing) return;
            chatInput.value = button.dataset.quick || '';
            resizeInput();
            sendMessage();
        });
    });

    async function initialize() {
        try {
            const status = await fetchJson(`/api/${encodeURIComponent(userId)}/status`);
            if (!status.initialized) {
                const initData = await fetchJson(`/api/${encodeURIComponent(userId)}/init`, { method: 'POST' });
                if (!initData.success) throw new Error(initData.error || '初始化失败');
            }

            await loadUserSummary();
            hideInitOverlay();
            setInputEnabled(true);

            const newData = await fetchJson(`/api/${encodeURIComponent(userId)}/is-new`);
            if (newData.is_new) startOnboarding();
            else showWelcomeMessage();
        } catch (err) {
            showInitError(err.message || '无法连接到服务器，请检查网络后刷新页面');
        }
    }

    function submitCurrentInput() {
        if (customInputCallback) {
            const value = chatInput.value.trim();
            if (!value) return;
            const callback = customInputCallback;
            customInputCallback = null;
            chatInput.value = '';
            chatInput.placeholder = defaultPlaceholder;
            resizeInput();
            callback(value);
            return;
        }
        sendMessage();
    }

    function setInputEnabled(enabled) {
        chatInput.disabled = !enabled;
        sendBtn.disabled = !enabled;
        if (enabled) chatInput.focus();
    }

    function hideInitOverlay() {
        initOverlay.classList.add('hidden');
        setTimeout(() => {
            initOverlay.style.display = 'none';
        }, 360);
    }

    function showInitError(message) {
        const status = document.querySelector('.init-status');
        const sub = document.querySelector('.init-sub');
        if (status) status.textContent = message;
        if (sub) sub.textContent = '请刷新页面重试';
    }

    async function loadUserSummary() {
        try {
            const data = await fetchJson(`/api/${encodeURIComponent(userId)}/summary`);
            panelName.textContent = `您好，${data.name_display || userId}`;
            panelLevel.textContent = data.member_level
                ? `${data.member_level} · ${data.member_tag || '差旅常客'}`
                : '差旅常客';

            const preferences = Array.isArray(data.preferences) ? data.preferences : [];
            prefList.replaceChildren();
            if (preferences.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'empty-state';
                empty.textContent = '还没有偏好记录。完成初次引导后，Hommey 会把你的习惯收好。';
                prefList.appendChild(empty);
                return;
            }

            preferences.forEach((preference) => {
                const row = document.createElement('div');
                row.className = 'info-row';

                const label = document.createElement('span');
                label.className = 'info-label';
                label.textContent = [preference.icon, preference.label].filter(Boolean).join(' ');

                const value = document.createElement('span');
                value.className = 'info-value';
                value.textContent = preference.value || '-';

                row.append(label, value);
                prefList.appendChild(row);
            });
        } catch (err) {
            console.error('Load summary error:', err);
        }
    }

    function startOnboarding() {
        isOnboarding = true;
        addMessage('ai', '你好，我是 Hommey。第一次见面，我想先轻轻了解几项偏好，这样之后帮你规划差旅会更贴心。');
        setTimeout(() => showOnboardingQuestion(0), 420);
    }

    function showOnboardingQuestion(index) {
        if (index >= onboardingSteps.length) {
            finishOnboarding();
            return;
        }
        onboardingIndex = index;
        const step = onboardingSteps[index];
        addOptionsMessage(step.question, step.options, step.hint);
    }

    function addOptionsMessage(question, options, hint) {
        const row = createMessageShell('ai');
        const stack = row.querySelector('.msg-stack');

        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble ai';
        bubble.append(createStrong(question));
        if (hint) {
            bubble.append(document.createElement('br'), createMutedText(hint));
        }

        const optionList = document.createElement('div');
        optionList.className = 'option-list';
        options.forEach((option) => {
            const pill = document.createElement('button');
            pill.type = 'button';
            pill.className = 'option-pill';
            pill.textContent = option;
            pill.addEventListener('click', () => handleOnboardingOption(option, optionList));
            optionList.appendChild(pill);
        });

        stack.append(bubble, optionList, createTime());
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function handleOnboardingOption(option, optionList) {
        optionList.querySelectorAll('button').forEach((button) => {
            button.disabled = true;
        });

        if (option === '其他') {
            const note = document.createElement('div');
            note.className = 'msg-time';
            note.textContent = '可以直接输入你的偏好。';
            optionList.after(note);
            chatInput.placeholder = '输入你的偏好';
            chatInput.focus();
            customInputCallback = (value) => {
                addMessage('user', value);
                sendOnboardingAnswer(value);
            };
            scrollToBottom();
            return;
        }

        addMessage('user', option);
        sendOnboardingAnswer(option);
    }

    async function sendOnboardingAnswer(value) {
        const step = onboardingSteps[onboardingIndex];
        isProcessing = true;
        showProcessingIndicator([]);

        try {
            const data = await fetchJson(`/api/${encodeURIComponent(userId)}/onboarding/preference`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: step.key, value }),
            });
            removeProcessingIndicator();
            if (data.error || data.success === false) {
                addMessage('ai', data.error || '偏好保存失败，请再试一次。');
                return;
            }
            addMessage('ai', data.message || `我记住了：${value}`);
            await loadUserSummary();
            setTimeout(() => showOnboardingQuestion(onboardingIndex + 1), 420);
        } catch (err) {
            removeProcessingIndicator();
            addMessage('ai', '偏好已先记录在对话里，稍后我会继续尝试同步。');
            setTimeout(() => showOnboardingQuestion(onboardingIndex + 1), 420);
        } finally {
            isProcessing = false;
        }
    }

    function finishOnboarding() {
        isOnboarding = false;
        chatInput.placeholder = defaultPlaceholder;
        addMessage(
            'ai',
            '偏好设置完成。以后你也可以随时告诉我新的习惯，我会继续更新。现在可以把你的出行计划交给我，比如：帮我规划下周去上海的两天行程。'
        );
    }

    function showWelcomeMessage() {
        const hour = new Date().getHours();
        const greeting = hour < 6 ? '夜深了' : hour < 9 ? '早上好' : hour < 12 ? '上午好' : hour < 14 ? '中午好' : hour < 18 ? '下午好' : '晚上好';
        addMessage(
            'ai',
            `${greeting}，我是 Hommey。你可以让我规划行程、查询天气、解释差旅标准，也可以告诉我新的出行偏好。`
        );
    }

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text || isProcessing || isOnboarding) return;

        addMessage('user', text);
        chatInput.value = '';
        resizeInput();

        isProcessing = true;
        sendBtn.disabled = true;
        chatInput.placeholder = 'Hommey 正在整理回复...';
        setSendLoading(true);
        showProcessingIndicator([]);

        try {
            const res = await fetch(`/api/${encodeURIComponent(userId)}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || '请求失败，请重试');
            }
            if (!res.body) throw new Error('当前浏览器不支持流式响应');

            let streamMsg = null;
            let preferencesUpdated = false;
            const reader = res.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    const event = parseStreamLine(line);
                    if (!event) continue;
                    if (event.type === 'error') throw new Error(event.error || '处理失败，请重试');
                    if (event.type === 'agents') updateAgentTags(event.agents);
                    if (event.type === 'chunk') {
                        if (!streamMsg) {
                            removeProcessingIndicator();
                            streamMsg = createStreamingMessage();
                        }
                        streamMsg.text += event.text || '';
                        renderMessageInto(streamMsg.bubble, streamMsg.text);
                        scrollToBottom();
                    }
                    if (event.type === 'done') preferencesUpdated = !!event.preferences_updated;
                }
            }

            const tail = parseStreamLine(buffer);
            if (tail) {
                if (tail.type === 'chunk') {
                    if (!streamMsg) {
                        removeProcessingIndicator();
                        streamMsg = createStreamingMessage();
                    }
                    streamMsg.text += tail.text || '';
                    renderMessageInto(streamMsg.bubble, streamMsg.text);
                }
                if (tail.type === 'done') preferencesUpdated = !!tail.preferences_updated;
            }

            removeProcessingIndicator();
            if (streamMsg) finishStreamingMessage(streamMsg);
            else addMessage('ai', '我收到了，但这次没有返回具体内容。');

            if (preferencesUpdated) await loadUserSummary();
        } catch (err) {
            removeProcessingIndicator();
            addMessage('ai', err.message || '网络错误，请检查连接后重试。');
        } finally {
            isProcessing = false;
            sendBtn.disabled = false;
            setSendLoading(false);
            chatInput.placeholder = defaultPlaceholder;
            chatInput.focus();
        }
    }

    function createMessageShell(role) {
        const row = document.createElement('div');
        row.className = `message-row ${role}`;

        const avatar = document.createElement('div');
        avatar.className = `msg-avatar ${role}`;
        if (role === 'ai') {
            const image = document.createElement('img');
            image.src = assistantImage;
            image.alt = 'Hommey';
            avatar.appendChild(image);
        } else {
            avatar.textContent = (userId[0] || 'U').toUpperCase();
        }

        const stack = document.createElement('div');
        stack.className = 'msg-stack';

        row.append(avatar, stack);
        return row;
    }

    function addMessage(role, text) {
        const row = createMessageShell(role);
        const stack = row.querySelector('.msg-stack');
        const bubble = document.createElement('div');
        bubble.className = `msg-bubble ${role}`;
        renderMessageInto(bubble, text);
        stack.append(bubble, createTime());
        chatMessages.appendChild(row);
        scrollToBottom();
        return row;
    }

    function showProcessingIndicator(agents) {
        removeProcessingIndicator();
        const row = createMessageShell('ai');
        row.id = 'processingIndicator';
        const stack = row.querySelector('.msg-stack');
        const box = document.createElement('div');
        box.className = 'agent-indicator';
        box.innerHTML = `
            <div class="agent-tags">${renderAgentTags(agents)}</div>
            <div class="thinking-text">正在理解你的需求。</div>
            <div class="typing-dots"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>
        `;
        stack.appendChild(box);
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function removeProcessingIndicator() {
        const indicator = document.getElementById('processingIndicator');
        if (indicator) indicator.remove();
    }

    function updateAgentTags(agents) {
        const indicator = document.getElementById('processingIndicator');
        const tags = indicator && indicator.querySelector('.agent-tags');
        if (!tags || !Array.isArray(agents) || agents.length === 0) return;
        tags.innerHTML = renderAgentTags(agents);
    }

    function renderAgentTags(agents) {
        if (!Array.isArray(agents) || agents.length === 0) return '<span class="agent-tag">分析中</span>';
        return agents.map((agent) => `<span class="agent-tag">${escapeHTML(agent.display || agent.name || '处理中')}</span>`).join('');
    }

    function createStreamingMessage() {
        const row = createMessageShell('ai');
        const stack = row.querySelector('.msg-stack');
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble ai';
        const time = createTime();
        stack.appendChild(bubble);
        chatMessages.appendChild(row);
        scrollToBottom();
        return { bubble, stack, time, text: '' };
    }

    function finishStreamingMessage(streamMsg) {
        streamMsg.time.textContent = formatTime(new Date());
        streamMsg.stack.appendChild(streamMsg.time);
        scrollToBottom();
    }

    function renderMessageInto(element, text) {
        element.replaceChildren();
        const fragment = document.createDocumentFragment();
        const parts = String(text || '').split(/(\*\*[^*]+\*\*|\n|•)/g);
        parts.forEach((part) => {
            if (!part) return;
            if (part === '\n') {
                fragment.appendChild(document.createElement('br'));
            } else if (part === '•') {
                fragment.appendChild(document.createTextNode('•'));
            } else if (part.startsWith('**') && part.endsWith('**')) {
                fragment.appendChild(createStrong(part.slice(2, -2)));
            } else {
                fragment.appendChild(document.createTextNode(part));
            }
        });
        element.appendChild(fragment);
    }

    function createStrong(text) {
        const strong = document.createElement('strong');
        strong.textContent = text;
        return strong;
    }

    function createMutedText(text) {
        const span = document.createElement('span');
        span.style.color = '#71808d';
        span.style.fontSize = '13px';
        span.textContent = text;
        return span;
    }

    function createTime() {
        const time = document.createElement('div');
        time.className = 'msg-time';
        time.textContent = formatTime(new Date());
        return time;
    }

    function resizeInput() {
        chatInput.style.height = 'auto';
        chatInput.style.height = `${Math.min(chatInput.scrollHeight, 128)}px`;
    }

    function setSendLoading(loading) {
        sendBtn.innerHTML = loading
            ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><circle cx="12" cy="12" r="9" stroke-dasharray="34 18" style="animation: spin 0.8s linear infinite; transform-origin: center;"/></svg>'
            : '<svg class="send-icon" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>';
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function formatTime(date) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }

    function parseStreamLine(line) {
        const trimmed = String(line || '').trim();
        if (!trimmed) return null;
        try {
            return JSON.parse(trimmed);
        } catch (err) {
            console.warn('Bad stream event:', trimmed);
            return null;
        }
    }

    async function fetchJson(url, options) {
        const res = await fetch(url, options);
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || data.error || '请求失败');
        return data;
    }

    function escapeHTML(value) {
        return String(value || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }
})();
