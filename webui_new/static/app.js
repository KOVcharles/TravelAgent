/**
 * Aligo 商旅助手 - 前端交互逻辑
 * 包含新用户引导、聊天、右侧面板更新
 */
(function() {
    'use strict';

    const user_id = window.location.pathname.split('/').pop();
    const chatMessages = document.getElementById('chatMessages');
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    const initOverlay = document.getElementById('initOverlay');
    const panelName = document.getElementById('panelName');
    const panelLevel = document.getElementById('panelLevel');
    const prefList = document.getElementById('prefList');

    let isProcessing = false;

    // ── 新用户引导步骤 ──
    const onboardingSteps = [
        {
            question: '首先，请问您的常驻城市是哪里？😊',
            key: 'home_location',
            hint: '方便为您推荐从该城市出发的行程',
            options: ['北京', '上海', '广州', '深圳', '成都', '杭州', '其他 ✍️'],
        },
        {
            question: '出差时您更喜欢哪种交通工具？',
            key: 'transportation_preference',
            hint: '规划行程时会优先考虑',
            options: ['高铁 🚄', '飞机 ✈️', '自驾 🚗', '其他 ✍️'],
        },
        {
            question: '您偏好哪类酒店品牌？',
            key: 'hotel_brands',
            hint: '推荐酒店时会优先匹配',
            options: ['汉庭', '如家', '全季', '亚朵', '锦江之星', '其他 ✍️'],
        },
        {
            question: '最后，您对座位有什么偏好吗？',
            key: 'seat_preference',
            hint: '订票时会优先选择',
            options: ['商务座', '一等座', '二等座', '经济舱', '不指定', '其他 ✍️'],
        },
    ];
    let onboardingIndex = 0;
    let isOnboarding = false;
    let customInputCallback = null;

    // ── Auto-resize textarea ──
    chatInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = Math.min(this.scrollHeight, 120) + 'px';
    });

    // ── Keyboard submit ──
    chatInput.addEventListener('keydown', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (customInputCallback) {
                const val = this.value.trim();
                if (val) {
                    const cb = customInputCallback;
                    customInputCallback = null;
                    this.value = '';
                    this.style.height = 'auto';
                    cb(val);
                }
                return;
            }
            sendMessage();
        }
    });

    sendBtn.addEventListener('click', () => {
        if (customInputCallback) {
            const val = chatInput.value.trim();
            if (val) {
                const cb = customInputCallback;
                customInputCallback = null;
                chatInput.value = '';
                chatInput.style.height = 'auto';
                chatInput.placeholder = '输入您的出行需求...';
                cb(val);
            }
            return;
        }
        sendMessage();
    });

    // ── Quick action buttons ──
    document.querySelectorAll('.quick-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            if (isOnboarding) return;
            chatInput.value = this.dataset.quick;
            sendMessage();
        });
    });

    // ── Initialize on load ──
    document.addEventListener('DOMContentLoaded', initialize);

    async function initialize() {
        try {
            let statusRes = await fetch(`/api/${user_id}/status`);
            let status = await statusRes.json();

            if (!status.initialized) {
                let initRes = await fetch(`/api/${user_id}/init`, { method: 'POST' });
                let initData = await initRes.json();
                if (!initData.success) {
                    showInitError(initData.error || '初始化失败');
                    return;
                }
            }

            // Check if new user
            const newRes = await fetch(`/api/${user_id}/is-new`);
            const newData = await newRes.json();
            const isNew = newData.is_new;

            // Load summary for right panel
            await loadUserSummary();

            // Hide overlay
            initOverlay.classList.add('hidden');
            setTimeout(() => { initOverlay.style.display = 'none'; }, 500);

            chatInput.disabled = false;
            sendBtn.disabled = false;
            chatInput.focus();

            if (isNew) {
                startOnboarding();
            } else {
                showWelcomeMessage();
            }
        } catch (err) {
            console.error('Init error:', err);
            showInitError('无法连接到服务器，请检查网络后刷新页面');
        }
    }

    function showInitError(msg) {
        document.querySelector('.init-status').textContent = '❌ ' + msg;
        document.querySelector('.init-sub').textContent = '请刷新页面重试';
    }

    async function loadUserSummary() {
        try {
            const res = await fetch(`/api/${user_id}/summary`);
            const data = await res.json();
            panelName.textContent = `您好，${data.name_display || user_id}`;
            panelLevel.textContent = data.member_level
                ? `${data.member_level} · ${data.member_tag}`
                : '差旅常客';
            if (data.preferences && data.preferences.length > 0) {
                prefList.innerHTML = data.preferences.map(p =>
                    `<div class="info-row">
                        <span class="info-label">${p.icon} ${p.label}</span>
                        <span class="info-value">${p.value}</span>
                    </div>`
                ).join('');
            } else {
                prefList.innerHTML =
                    `<div style="padding:12px 0;text-align:center;color:#475569;font-size:12px;">
                        暂无偏好信息<br>
                        <span style="font-size:11px;">完成引导即可设置</span>
                    </div>`;
            }
        } catch (err) {
            console.error('Load summary error:', err);
        }
    }

    // ── Onboarding Flow ──
    function startOnboarding() {
        isOnboarding = true;
        addMessage('ai',
            '👋 **您好！** 看起来您是第一次使用 Aligo，让我先了解一下您的偏好，这样可以为您提供更好的差旅建议！'
        );
        setTimeout(() => showOnboardingQuestion(0), 600);
    }

    function showOnboardingQuestion(index) {
        if (index >= onboardingSteps.length) {
            finishOnboarding();
            return;
        }
        onboardingIndex = index;
        const step = onboardingSteps[index];
        showOptionsMessage(step.question, step.options, step.hint);
    }

    function showOptionsMessage(question, options, hint) {
        const row = document.createElement('div');
        row.className = 'message-row ai';
        row.style.animation = 'none';

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar ai';
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>`;

        const wrap = document.createElement('div');
        wrap.style.maxWidth = '100%';

        // Question text
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble ai';
        bubble.innerHTML = `<strong>${question}</strong>` + (hint ? `<br><span style="color:#94A3B8;font-size:13px;">${hint}</span>` : '');
        wrap.appendChild(bubble);

        // Options as clickable pills
        const optsDiv = document.createElement('div');
        optsDiv.style.cssText = 'display:flex;flex-wrap:wrap;gap:6px;margin-top:10px;';

        options.forEach(opt => {
            const pill = document.createElement('button');
            const isOther = opt.includes('其他');
            pill.textContent = isOther ? opt.replace(' ✍️', '') + ' ✍️' : opt;
            pill.style.cssText = `
                padding: 7px 18px; border-radius: 20px; border: 1px solid #334155;
                background: #1E293B; color: #E2E8F0; font-size: 13px; font-family: inherit;
                cursor: pointer; transition: all 0.15s ease;
            `;
            pill.onmouseover = () => {
                pill.style.background = '#334155';
                pill.style.borderColor = '#3B82F6';
                pill.style.color = '#F1F5F9';
            };
            pill.onmouseout = () => {
                pill.style.background = '#1E293B';
                pill.style.borderColor = '#334155';
                pill.style.color = '#E2E8F0';
            };
            pill.onclick = () => handleOnboardingOption(opt, pill);
            optsDiv.appendChild(pill);
        });

        wrap.appendChild(optsDiv);

        const time = document.createElement('div');
        time.className = 'msg-time';
        wrap.appendChild(time);

        row.appendChild(avatar);
        row.appendChild(wrap);
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function handleOnboardingOption(opt, pillEl) {
        // Disable all pills in this question
        const container = pillEl.parentElement;
        const pills = container.querySelectorAll('button');
        pills.forEach(p => { p.style.opacity = '0.4'; p.style.cursor = 'default'; p.onclick = null; });

        const isOther = opt.includes('其他');
        let answerText;

        if (isOther) {
            answerText = '其他';
            // Show a temporary indicator
            const indicator = document.createElement('div');
            indicator.style.cssText = 'font-size:12px;color:#94A3B8;margin-top:6px;';
            indicator.textContent = '请在输入框填写您的偏好后按 Enter ✍️';
            container.parentElement.appendChild(indicator);
            scrollToBottom();

            // Focus input & set callback
            chatInput.placeholder = '请输入您的偏好...';
            chatInput.focus();
            customInputCallback = (val) => {
                if (val) {
                    addUserMessage(val);
                    sendOnboardingAnswer(val);
                }
            };
            return;
        }

        // Non-other option: use the clean text (remove emoji)
        answerText = opt.replace(/ [\u{1F000}-\u{1FFFF}]/gu, '').trim();
        addUserMessage(answerText);
        sendOnboardingAnswer(answerText);
    }

    function sendOnboardingAnswer(text) {
        const step = onboardingSteps[onboardingIndex];

        isProcessing = true;
        showProcessingIndicator([]);

        fetch(`/api/${user_id}/onboarding/preference`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: step.key, value: text }),
        })
        .then(res => res.json())
        .then(data => {
            removeProcessingIndicator();
            if (data.error || data.success === false) {
                addMessage('ai', `❌ ${data.error || '偏好保存失败，请重试'}`);
                return;
            } else {
                addTypedMessage(data.message || `✅ 已记录「${text}」`);
            }
            // Refresh panel
            loadUserSummary();
            // Next question
            setTimeout(() => showOnboardingQuestion(onboardingIndex + 1), 500);
        })
        .catch(() => {
            removeProcessingIndicator();
            addMessage('ai', `✅ 已记录「${text}」`);
            setTimeout(() => showOnboardingQuestion(onboardingIndex + 1), 500);
        })
        .finally(() => {
            isProcessing = false;
        });
    }

    function finishOnboarding() {
        isOnboarding = false;
        addMessage('ai',
            '🎉 **偏好设置完成！** 以后您也可以随时告诉我新的偏好。\n\n现在，有什么出行计划需要帮忙的吗？比如：\n• ✈️ 帮我规划去上海的行程\n• 🌤️ 查一下北京的天气\n• 📋 出差住宿标准是多少'
        );
    }

    // ── Chat ──
    function showWelcomeMessage() {
        const hour = new Date().getHours();
        let greeting = '你好';
        if (hour < 6) greeting = '夜深了';
        else if (hour < 9) greeting = '早上好';
        else if (hour < 12) greeting = '上午好';
        else if (hour < 14) greeting = '中午好';
        else if (hour < 18) greeting = '下午好';
        else greeting = '晚上好';

        addMessage('ai',
            `**${greeting}！** 我是 Aligo，您的智能差旅助手。\n\n` +
            `我可以帮您：\n` +
            `• ✈️ **规划行程** — "帮我规划去上海的行程"\n` +
            `• 🌤️ **查询信息** — "北京的天气怎么样"\n` +
            `• 📋 **差旅标准** — "出差住宿标准是多少"\n` +
            `• 💾 **记住偏好** — "我喜欢坐高铁"\n\n` +
            `有什么可以帮您的吗？`
        );
    }

    // ── Message helpers ──
    function addMessage(role, content) {
        const row = document.createElement('div');
        row.className = `message-row ${role}`;
        row.style.animation = 'messageIn 0.3s ease';

        const avatar = document.createElement('div');
        avatar.className = `msg-avatar ${role}`;
        if (role === 'ai') {
            avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>`;
        } else {
            avatar.textContent = user_id.charAt(0).toUpperCase();
        }

        const wrap = document.createElement('div');
        wrap.style.maxWidth = '100%';

        const bubble = document.createElement('div');
        bubble.className = `msg-bubble ${role}`;
        bubble.innerHTML = content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>')
            .replace(/•/g, '&bull;');

        const time = document.createElement('div');
        time.className = 'msg-time';
        time.textContent = formatTime(new Date());

        wrap.appendChild(bubble);
        wrap.appendChild(time);
        role === 'ai' ? (row.appendChild(avatar), row.appendChild(wrap)) : (row.appendChild(wrap), row.appendChild(avatar));
        chatMessages.appendChild(row);
        scrollToBottom();
        return row;
    }

    function addUserMessage(text) {
        return addMessage('user', text);
    }

    function showProcessingIndicator(agents) {
        const row = document.createElement('div');
        row.className = 'message-row ai';
        row.id = 'processingIndicator';

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar ai';
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>`;

        const wrap = document.createElement('div');
        wrap.innerHTML = `
            <div class="agent-indicator">
                <div class="agent-tags">${agents.length ? agents.map(a => `<span class="agent-tag active">${a.display}</span>`).join('') : '<span class="agent-tag pending">分析中</span>'}</div>
                <div class="thinking-text">正在处理您的请求...</div>
                <div class="typing-dots"><div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div></div>
            </div>
        `;

        row.appendChild(avatar);
        row.appendChild(wrap);
        chatMessages.appendChild(row);
        scrollToBottom();
    }

    function removeProcessingIndicator() {
        const el = document.getElementById('processingIndicator');
        if (el) el.remove();
    }

    function addTypedMessage(text) {
        const row = document.createElement('div');
        row.className = 'message-row ai';
        row.style.animation = 'none';

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar ai';
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>`;

        const wrap = document.createElement('div');
        wrap.style.maxWidth = '100%';
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble ai';
        const time = document.createElement('div');
        time.className = 'msg-time';

        wrap.appendChild(bubble);
        row.appendChild(avatar);
        row.appendChild(wrap);
        chatMessages.appendChild(row);

        const lines = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>').replace(/•/g, '&bull;').split('\n');
        let idx = 0;
        let html = '';

        function nextLine() {
            if (idx >= lines.length) {
                time.textContent = formatTime(new Date());
                wrap.appendChild(time);
                scrollToBottom();
                return;
            }
            html += (html ? '<br>' : '') + lines[idx];
            bubble.innerHTML = html;
            scrollToBottom();
            idx++;
            const delay = lines[idx - 1]?.length > 50 ? 15 : lines[idx - 1]?.length > 20 ? 8 : 4;
            setTimeout(nextLine, delay);
        }
        nextLine();
    }

    function createStreamingMessage() {
        const row = document.createElement('div');
        row.className = 'message-row ai';
        row.style.animation = 'none';

        const avatar = document.createElement('div');
        avatar.className = 'msg-avatar ai';
        avatar.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>`;

        const wrap = document.createElement('div');
        wrap.style.maxWidth = '100%';
        const bubble = document.createElement('div');
        bubble.className = 'msg-bubble ai';
        const time = document.createElement('div');
        time.className = 'msg-time';

        wrap.appendChild(bubble);
        row.appendChild(avatar);
        row.appendChild(wrap);
        chatMessages.appendChild(row);
        scrollToBottom();

        return { bubble, wrap, time, text: '' };
    }

    function renderMessageText(text) {
        return text
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/•/g, '&bull;')
            .replace(/\n/g, '<br>');
    }

    function finishStreamingMessage(streamMsg) {
        if (!streamMsg) return;
        streamMsg.time.textContent = formatTime(new Date());
        streamMsg.wrap.appendChild(streamMsg.time);
        scrollToBottom();
    }

    function updateAgentTags(agents) {
        if (!agents || agents.length === 0) return;
        const indicator = document.getElementById('processingIndicator');
        if (!indicator) return;
        const tags = indicator.querySelector('.agent-tags');
        if (!tags) return;
        tags.innerHTML = agents.map(a =>
            `<span class="agent-tag done">${a.display}</span>`
        ).join('');
    }

    async function sendMessage() {
        const text = chatInput.value.trim();
        if (!text || isProcessing || isOnboarding) return;

        addUserMessage(text);
        chatInput.value = '';
        chatInput.style.height = 'auto';

        isProcessing = true;
        sendBtn.disabled = true;
        sendBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10" stroke-dasharray="31.4 31.4" stroke-linecap="round" style="animation:spin 0.8s linear infinite;transform-origin:center;"/></svg>`;
        chatInput.placeholder = '等待回复中...';

        showProcessingIndicator([]);

        try {
            const res = await fetch(`/api/${user_id}/chat/stream`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: text }),
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.error || '请求失败，请重试');
            }

            if (!res.body) {
                throw new Error('Streaming response is not supported');
            }

            const reader = res.body.getReader();
            const decoder = new TextDecoder('utf-8');
            let buffer = '';
            let streamMsg = null;
            let preferencesUpdated = false;

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.trim()) continue;
                    const event = JSON.parse(line);

                    if (event.type === 'error') {
                        throw new Error(event.error || '处理失败，请重试');
                    }

                    if (event.type === 'agents') {
                        updateAgentTags(event.agents);
                    }

                    if (event.type === 'chunk') {
                        if (!streamMsg) {
                            removeProcessingIndicator();
                            streamMsg = createStreamingMessage();
                        }
                        streamMsg.text += event.text || '';
                        streamMsg.bubble.innerHTML = renderMessageText(streamMsg.text);
                        scrollToBottom();
                    }

                    if (event.type === 'done') {
                        preferencesUpdated = !!event.preferences_updated;
                    }
                }
            }

            if (buffer.trim()) {
                const event = JSON.parse(buffer);
                if (event.type === 'chunk') {
                    if (!streamMsg) {
                        removeProcessingIndicator();
                        streamMsg = createStreamingMessage();
                    }
                    streamMsg.text += event.text || '';
                    streamMsg.bubble.innerHTML = renderMessageText(streamMsg.text);
                }
                if (event.type === 'done') {
                    preferencesUpdated = !!event.preferences_updated;
                }
            }

            removeProcessingIndicator();
            if (streamMsg) {
                finishStreamingMessage(streamMsg);
            } else {
                addTypedMessage('✓ 已收到您的请求。');
            }

            if (preferencesUpdated) {
                await loadUserSummary();
            }
        } catch (err) {
            removeProcessingIndicator();
            addMessage('ai', `❌ ${err.message || '网络错误，请检查连接后重试'}`);
        }

        isProcessing = false;
        sendBtn.disabled = false;
        sendBtn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>`;
        chatInput.placeholder = '输入您的出行需求，例如：下周一要去上海出差两天';
        chatInput.focus();
    }

    function scrollToBottom() {
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function formatTime(date) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }

    function sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // Inject keyframe
    const style = document.createElement('style');
    style.textContent = `@keyframes spin { to { transform: rotate(360deg); } }`;
    document.head.appendChild(style);
})();
