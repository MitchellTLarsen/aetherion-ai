/**
 * Scribe AI - Web Interface JavaScript
 */

// State
let state = {
    messages: [],
    sources: [],
    history: [],
    provider: 'gpt',
    model: 'gpt-5.4-nano',  // Current model selection
    contextSize: 20,
    isLoading: false,
    currentStreamController: null,
    pendingMessage: null,
    costEstimate: null,
    activeModules: [],  // Active modules for context-aware prompts
    customPrompt: '',   // User's custom prompt extension
    fullVault: false,   // Use full vault context instead of RAG
    fullVaultCache: null, // Cached full vault content
    sessionCost: {
        inputTokens: 0,
        outputTokens: 0,
        totalCost: 0
    }
};

// DOM Elements - cached for performance
const elements = {};
const elementIds = [
    'welcome-screen', 'chat-container', 'messages', 'message-input', 'send-btn',
    'provider-select', 'model-select', 'deep-search', 'full-vault', 'show-sources', 'confirm-send', 'cost-estimate',
    'sources-panel', 'sources-list', 'vault-stats', 'chat-history', 'settings-modal',
    'confirm-panel', 'confirm-message', 'confirm-sources', 'source-count',
    'cost-input-tokens', 'cost-output-tokens', 'cost-total'
];

function cacheElements() {
    elementIds.forEach(id => {
        const camelCase = id.replace(/-([a-z])/g, g => g[1].toUpperCase());
        elements[camelCase] = document.getElementById(id);
    });
}

// Debounce utility
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    // Cache DOM elements first
    cacheElements();

    // Load module settings first (affects what's visible)
    loadModuleSettings();

    // Load data in parallel
    Promise.all([
        loadVaultStats(),
        loadProviders(),
        loadCharacters()
    ]);

    setupInputHandlers();
    loadHistory();
    loadTheme();
    loadFullVaultSetting();
    loadModelSetting();

    // Initialize character state
    state.character = '';

    // Configure marked
    marked.setOptions({
        highlight: function(code, lang) {
            if (lang && hljs.getLanguage(lang)) {
                return hljs.highlight(code, { language: lang }).value;
            }
            return hljs.highlightAuto(code).value;
        },
        breaks: true
    });
});

// Module Settings
const AI_MODE_DESCRIPTIONS = {
    'generic': 'Balanced assistant for any knowledge work',
    'academic': 'Focused on research, citations, and structured writing',
    'fiction': 'Focused on narrative, characters, and story development',
    'technical': 'Focused on clear documentation, code examples, and precision',
    'journaling': 'Reflective, personal, helps with self-discovery and organization',
    'custom': 'Your custom instructions'
};

function loadModuleSettings() {
    const settings = JSON.parse(localStorage.getItem('aetherion_modules') || '{}');

    // Migrate old settings: if user had worldbuilding/campaign/character enabled, enable fantasy
    if (settings.fantasy === undefined) {
        if (settings.worldbuilding || settings.campaign || settings.character) {
            settings.fantasy = true;
            // Clean up old keys
            delete settings.worldbuilding;
            delete settings.campaign;
            delete settings.character;
        }
    }

    // Set defaults
    if (settings.fantasy === undefined) settings.fantasy = false;
    if (settings.aiMode === undefined) settings.aiMode = 'generic';
    if (settings.customPrompt === undefined) settings.customPrompt = '';

    // Update UI
    const fantasyCheckbox = document.getElementById('module-fantasy');
    if (fantasyCheckbox) fantasyCheckbox.checked = settings.fantasy;

    const aiModeSelect = document.getElementById('ai-mode');
    if (aiModeSelect) {
        aiModeSelect.value = settings.aiMode;
        updateAiModeDescription(settings.aiMode);
    }

    const customPromptEl = document.getElementById('custom-prompt');
    if (customPromptEl) customPromptEl.value = settings.customPrompt;

    // Show/hide custom prompt section
    toggleCustomPromptSection(settings.aiMode === 'custom');

    // Apply visibility
    applyModuleVisibility(settings);

    // Store active modules in state for API calls
    updateActiveModules(settings);

    localStorage.setItem('aetherion_modules', JSON.stringify(settings));
    return settings;
}

function saveModuleSettings() {
    const settings = {
        fantasy: document.getElementById('module-fantasy')?.checked || false,
        aiMode: document.getElementById('ai-mode')?.value || 'generic',
        customPrompt: document.getElementById('custom-prompt')?.value || ''
    };

    localStorage.setItem('aetherion_modules', JSON.stringify(settings));
    applyModuleVisibility(settings);
    updateActiveModules(settings);
    updateAiModeDescription(settings.aiMode);
}

function onAiModeChange() {
    const mode = document.getElementById('ai-mode')?.value || 'generic';
    toggleCustomPromptSection(mode === 'custom');
    saveModuleSettings();
}

function toggleCustomPromptSection(show) {
    const section = document.getElementById('custom-prompt-section');
    if (section) {
        section.classList.toggle('hidden', !show);
    }
}

function updateActiveModules(settings) {
    // Build list of active modules for API
    state.activeModules = [];
    if (settings.fantasy) state.activeModules.push('fantasy');
    if (settings.aiMode && settings.aiMode !== 'generic') {
        state.activeModules.push(settings.aiMode);
    }
    // Store custom prompt separately in state
    state.customPrompt = settings.aiMode === 'custom' ? settings.customPrompt : '';
}

function updateAiModeDescription(mode) {
    const descEl = document.getElementById('ai-mode-description');
    if (descEl) {
        descEl.textContent = AI_MODE_DESCRIPTIONS[mode] || AI_MODE_DESCRIPTIONS['generic'];
    }
}

function applyModuleVisibility(settings) {
    // Hide/show sidebar sections based on fantasy module
    document.querySelectorAll('[data-module]').forEach(el => {
        const mod = el.getAttribute('data-module');
        if (mod === 'fantasy' && !settings.fantasy) {
            el.style.display = 'none';
        } else {
            el.style.display = '';
        }
    });

    // Show/hide fantasy quick actions
    const fantasyActions = document.getElementById('fantasy-quick-actions');
    if (fantasyActions) {
        fantasyActions.classList.toggle('hidden', !settings.fantasy);
    }
}

// Theme functions
function loadTheme() {
    const savedTheme = localStorage.getItem('aetherion_theme') || 'dark';
    setTheme(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark';
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
    localStorage.setItem('aetherion_theme', newTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);

    // Switch highlight.js theme
    const darkStyle = document.getElementById('hljs-dark');
    const lightStyle = document.getElementById('hljs-light');

    if (theme === 'light') {
        darkStyle.disabled = true;
        lightStyle.disabled = false;
    } else {
        darkStyle.disabled = false;
        lightStyle.disabled = true;
    }
}

// API Functions
async function fetchSources(query) {
    // Full vault mode: return all vault content instead of RAG search
    if (state.fullVault) {
        return await fetchFullVault();
    }

    const response = await fetch('/api/sources', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            query,
            limit: state.contextSize,
            deep: elements.deepSearch.checked
        })
    });
    const data = await response.json();
    return data.sources;
}

async function fetchFullVault() {
    // Return cached if available
    if (state.fullVaultCache) {
        return state.fullVaultCache;
    }

    const response = await fetch('/api/vault/full');
    const data = await response.json();

    if (data.truncated) {
        console.warn('Full vault content was truncated due to size limits');
    }

    // Cache the result
    state.fullVaultCache = data.sources;
    return data.sources;
}

function toggleFullVault() {
    const checkbox = document.getElementById('full-vault');
    state.fullVault = checkbox.checked;

    // Disable deep search when full vault is enabled (they're mutually exclusive)
    if (state.fullVault) {
        elements.deepSearch.checked = false;
        elements.deepSearch.disabled = true;
    } else {
        elements.deepSearch.disabled = false;
        // Clear cache when turning off
        state.fullVaultCache = null;
    }

    // Save preference
    localStorage.setItem('scribe_full_vault', state.fullVault);
}

function loadFullVaultSetting() {
    const saved = localStorage.getItem('scribe_full_vault') === 'true';
    if (elements.fullVault) {
        elements.fullVault.checked = saved;
        state.fullVault = saved;
        if (saved && elements.deepSearch) {
            elements.deepSearch.disabled = true;
        }
    }
}

function clearFullVaultCache() {
    state.fullVaultCache = null;
}

async function estimateCost(message) {
    const response = await fetch('/api/estimate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message,
            history: state.history,
            sources: state.sources,
            provider: state.provider
        })
    });
    return await response.json();
}

async function countOutputTokens(text) {
    const model = getModelForProvider(state.provider);
    const response = await fetch('/api/tokens', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            text,
            model,
            type: 'output'
        })
    });
    return await response.json();
}

function getModelForProvider(provider) {
    // For GPT, use the selected model from dropdown
    if (provider === 'gpt' || provider === 'openai') {
        return state.model || 'gpt-5.4-nano';
    }

    const models = {
        'gemini': 'gemini-2.5-flash-lite',
        'anthropic': 'claude-sonnet-4-20250514',
        'claude': 'claude-sonnet-4-20250514',
        'ollama': 'llama3',
        'groq': 'llama-3.3-70b-versatile',
        'openrouter': 'anthropic/claude-3.5-sonnet'
    };
    return models[provider] || 'gpt-5.4-nano';
}

function updateSessionCost(inputTokens, outputTokens, cost, isFree) {
    if (!isFree) {
        state.sessionCost.inputTokens += inputTokens;
        state.sessionCost.outputTokens += outputTokens;
        state.sessionCost.totalCost += cost;
    }
    updateSessionCostDisplay();
}

function updateSessionCostDisplay() {
    const el = elements.costEstimate;
    if (state.sessionCost.totalCost > 0) {
        el.textContent = `Session: $${state.sessionCost.totalCost.toFixed(4)} (${state.sessionCost.inputTokens.toLocaleString()} in / ${state.sessionCost.outputTokens.toLocaleString()} out)`;
        el.className = 'cost-estimate';
    } else if (state.sessionCost.inputTokens > 0) {
        el.textContent = `Session: FREE (${(state.sessionCost.inputTokens + state.sessionCost.outputTokens).toLocaleString()} tokens)`;
        el.className = 'cost-estimate free';
    }
}

async function streamChat(message, sources) {
    const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message,
            history: state.history,
            sources,
            provider: state.provider,
            modules: state.activeModules || [],
            customPrompt: state.customPrompt || '',
            fullVault: state.fullVault || false
        })
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    return {
        async *[Symbol.asyncIterator]() {
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value);
                const lines = text.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));
                            if (data.chunk) yield data.chunk;
                            if (data.info) {
                                // Show info message (e.g., context was compressed)
                                console.log('Info:', data.info);
                                showNotification(data.info, 'info');
                            }
                            if (data.done) return;
                            if (data.error) throw new Error(data.error);
                        } catch (e) {
                            // Ignore parse errors for incomplete chunks
                        }
                    }
                }
            }
        }
    };
}

function showNotification(message, type = 'info') {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Auto-remove after 4 seconds
    setTimeout(() => {
        notification.classList.add('fade-out');
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}

// UI Functions
function setupInputHandlers() {
    const input = elements.messageInput;

    // Debounced cost estimation (wait 500ms after typing stops)
    const debouncedCostEstimate = debounce(async (value) => {
        if (value.trim().length > 10) {
            await updateCostEstimate(value);
        }
    }, 500);

    input.addEventListener('input', () => {
        // Enable/disable send button immediately
        elements.sendBtn.disabled = !input.value.trim();

        // Debounce cost estimation to reduce API calls
        debouncedCostEstimate(input.value);
    });
}

function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
}

async function prepareMessage() {
    const input = elements.messageInput;
    const message = input.value.trim();

    if (!message || state.isLoading) return;

    state.pendingMessage = message;
    state.isLoading = true;
    elements.sendBtn.disabled = true;

    // Show loading in button area
    elements.costEstimate.textContent = state.fullVault ? 'Loading full vault...' : 'Searching vault...';

    try {
        // Fetch sources
        state.sources = await fetchSources(message);

        // Get cost estimate
        state.costEstimate = await estimateCost(message);

        // Check if confirm is enabled
        if (elements.confirmSend.checked) {
            showConfirmPanel();
        } else {
            await sendMessage();
        }
    } catch (error) {
        console.error('Error:', error);
        elements.costEstimate.textContent = 'Error fetching sources';
        state.isLoading = false;
        elements.sendBtn.disabled = false;
    }
}

function showConfirmPanel() {
    const panel = elements.confirmPanel;

    // Populate message
    elements.confirmMessage.textContent = state.pendingMessage;

    // Update sources and cost display
    updateConfirmPanel();

    // Show panel
    panel.classList.remove('hidden');
    state.isLoading = false;
}

function toggleConfirmSources() {
    elements.confirmSources.classList.toggle('hidden');
}

async function fetchMoreSources() {
    state.contextSize += 10;

    // Show loading state
    elements.sourceCount.textContent = 'Loading...';
    elements.costInputTokens.textContent = '...';
    elements.costTotal.textContent = 'Calculating...';

    try {
        // Fetch more sources
        state.sources = await fetchSources(state.pendingMessage);

        // Recalculate cost with new sources
        state.costEstimate = await estimateCost(state.pendingMessage);

        // Update the confirm panel with new data
        updateConfirmPanel();
    } catch (error) {
        console.error('Error fetching more sources:', error);
        elements.sourceCount.textContent = state.sources.length;
    }
}

function updateConfirmPanel() {
    // Update source count
    elements.sourceCount.textContent = state.sources.length;

    // Update sources list using DocumentFragment for better performance
    const sourcesList = elements.confirmSources;
    const fragment = document.createDocumentFragment();

    state.sources.forEach(source => {
        const scoreClass = source.score >= 70 ? '' : source.score >= 50 ? 'medium' : 'low';
        const name = source.path.split('/').pop();

        const item = document.createElement('div');
        item.className = 'confirm-source-item';
        item.innerHTML = `
            <span class="confirm-source-path" title="${source.path}">${name}</span>
            <span class="confirm-source-score ${scoreClass}">${source.score}%</span>
        `;
        fragment.appendChild(item);
    });

    sourcesList.innerHTML = '';
    sourcesList.appendChild(fragment);

    // Update cost breakdown
    elements.costInputTokens.textContent = state.costEstimate.input_tokens.toLocaleString();
    elements.costOutputTokens.textContent = '~' + state.costEstimate.output_tokens.toLocaleString();

    if (state.costEstimate.is_free) {
        elements.costTotal.textContent = 'FREE';
        elements.costTotal.parentElement.classList.remove('not-free');
    } else {
        elements.costTotal.textContent = '$' + state.costEstimate.total_cost.toFixed(4);
        elements.costTotal.parentElement.classList.add('not-free');
    }
}

function cancelSend() {
    elements.confirmPanel.classList.add('hidden');
    state.pendingMessage = null;
    state.isLoading = false;
    elements.sendBtn.disabled = false;
    elements.costEstimate.textContent = '';
}

async function confirmAndSend() {
    elements.confirmPanel.classList.add('hidden');
    await sendMessage();
}

async function sendMessage() {
    const message = state.pendingMessage;
    const input = elements.messageInput;
    const inputTokens = state.costEstimate?.input_tokens || 0;
    const isFree = state.costEstimate?.is_free || false;

    // Clear input
    input.value = '';
    input.style.height = 'auto';
    elements.sendBtn.disabled = true;

    // Show chat container
    elements.welcomeScreen.classList.add('hidden');
    elements.chatContainer.classList.remove('hidden');

    // Add user message
    addMessage('user', message);

    // Show loading
    state.isLoading = true;
    showLoading();

    try {
        // Show sources panel if enabled
        if (elements.showSources.checked && state.sources.length > 0) {
            displaySources(state.sources);
        }

        // Stream response
        const assistantMessage = addMessage('assistant', '', true);
        const contentEl = assistantMessage.querySelector('.message-body');
        let fullResponse = '';

        const stream = await streamChat(message, state.sources);

        for await (const chunk of stream) {
            fullResponse += chunk;
            contentEl.innerHTML = marked.parse(fullResponse);
            scrollToBottom();
        }

        // Calculate actual output cost
        const outputResult = await countOutputTokens(fullResponse);
        const outputTokens = outputResult.tokens;
        const outputCost = outputResult.cost;
        const inputCost = state.costEstimate?.total_cost - (state.costEstimate?.output_tokens / 1000000 * 0.4) || 0;
        const actualTotalCost = inputCost + outputCost;

        // Update session totals
        updateSessionCost(inputTokens, outputTokens, actualTotalCost, isFree);

        // Add cost badge to message
        addCostBadge(assistantMessage, inputTokens, outputTokens, actualTotalCost, isFree);

        // Add source badges to message
        if (state.sources.length > 0) {
            addSourceBadges(assistantMessage, state.sources.slice(0, 5));
        }

        // Add action buttons (Save as TODO for full vault reviews)
        addMessageActions(assistantMessage, fullResponse, message);

        // Update history
        state.history.push({ role: 'user', content: message });
        state.history.push({ role: 'assistant', content: fullResponse });

        // Save to local storage
        saveHistory();

    } catch (error) {
        console.error('Error:', error);
        addMessage('assistant', `Error: ${error.message}`);
    } finally {
        state.isLoading = false;
        state.pendingMessage = null;
        hideLoading();
        elements.sendBtn.disabled = false;
    }
}

function sendQuickAction(query) {
    elements.messageInput.value = query;
    elements.sendBtn.disabled = false;
    prepareMessage();
}

function addMessage(role, content, isStreaming = false) {
    const container = elements.messages;
    const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    const messageEl = document.createElement('div');
    messageEl.className = `message ${role}`;

    const avatar = role === 'user' ? 'Y' : 'A';
    const author = role === 'user' ? 'You' : 'Scribe';

    messageEl.innerHTML = `
        <div class="message-avatar">${avatar}</div>
        <div class="message-content">
            <div class="message-header">
                <span class="message-author">${author}</span>
                <span class="message-time">${time}</span>
            </div>
            <div class="message-body">${isStreaming ? '' : marked.parse(content)}</div>
        </div>
    `;

    container.appendChild(messageEl);
    scrollToBottom();

    return messageEl;
}

function addCostBadge(messageEl, inputTokens, outputTokens, totalCost, isFree) {
    const contentEl = messageEl.querySelector('.message-content');
    const costEl = document.createElement('div');
    costEl.className = 'message-cost';

    if (isFree) {
        costEl.innerHTML = `<span class="cost-badge free">FREE: ${inputTokens.toLocaleString()} in / ${outputTokens.toLocaleString()} out</span>`;
    } else {
        costEl.innerHTML = `<span class="cost-badge">$${totalCost.toFixed(4)}: ${inputTokens.toLocaleString()} in / ${outputTokens.toLocaleString()} out</span>`;
    }

    contentEl.appendChild(costEl);
}

function addSourceBadges(messageEl, sources) {
    const contentEl = messageEl.querySelector('.message-content');
    const badgesEl = document.createElement('div');
    badgesEl.className = 'message-sources';

    sources.forEach(source => {
        const badge = document.createElement('span');
        badge.className = 'source-badge';
        badge.onclick = () => openSource(source.path);

        const name = source.path.split('/').pop().replace('.md', '');
        badge.innerHTML = `
            ${name}
            <span class="score">${source.score}%</span>
        `;

        badgesEl.appendChild(badge);
    });

    contentEl.appendChild(badgesEl);
}

function addMessageActions(messageEl, content, query) {
    const contentEl = messageEl.querySelector('.message-content');
    const actionsEl = document.createElement('div');
    actionsEl.className = 'message-actions';

    // Save as TODO button
    const todoBtn = document.createElement('button');
    todoBtn.className = 'action-btn';
    todoBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M9 11l3 3L22 4"/>
            <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
        </svg>
        Save as TODO
    `;
    todoBtn.onclick = () => saveTodo(content, query);
    actionsEl.appendChild(todoBtn);

    // Copy button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'action-btn';
    copyBtn.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg>
        Copy
    `;
    copyBtn.onclick = () => {
        navigator.clipboard.writeText(content);
        copyBtn.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M20 6L9 17l-5-5"/>
            </svg>
            Copied!
        `;
        setTimeout(() => {
            copyBtn.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                    <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
                </svg>
                Copy
            `;
        }, 2000);
    };
    actionsEl.appendChild(copyBtn);

    contentEl.appendChild(actionsEl);
}

async function saveTodo(content, query) {
    // Prompt for title
    const title = prompt('Enter a title for this TODO list:', 'Vault Review');
    if (title === null) return; // Cancelled

    try {
        const response = await fetch('/api/save-todo', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content,
                title,
                query
            })
        });

        const data = await response.json();

        if (data.success) {
            showNotification(`Saved to ${data.path}`, 'success');
            // Open in Obsidian if available
            if (data.obsidian_url) {
                window.open(data.obsidian_url, '_blank');
            }
        } else {
            showNotification(data.error || 'Failed to save', 'error');
        }
    } catch (error) {
        console.error('Error saving TODO:', error);
        showNotification('Failed to save TODO', 'error');
    }
}

function showLoading() {
    const container = elements.messages;
    const loadingEl = document.createElement('div');
    loadingEl.id = 'loading-message';
    loadingEl.className = 'message assistant';
    loadingEl.innerHTML = `
        <div class="message-avatar">A</div>
        <div class="message-content">
            <div class="loading-indicator">
                <div class="loading-dots">
                    <span></span>
                    <span></span>
                    <span></span>
                </div>
                <span>Searching vault and thinking...</span>
            </div>
        </div>
    `;
    container.appendChild(loadingEl);
    scrollToBottom();
}

function hideLoading() {
    const loading = document.getElementById('loading-message');
    if (loading) loading.remove();
}

function scrollToBottom() {
    const container = elements.chatContainer;
    container.scrollTop = container.scrollHeight;
}

async function updateCostEstimate(message) {
    try {
        const cost = await estimateCost(message);
        const el = elements.costEstimate;

        if (cost.is_free) {
            el.textContent = `FREE (${cost.input_tokens.toLocaleString()} tokens)`;
            el.className = 'cost-estimate free';
        } else {
            el.textContent = cost.formatted;
            el.className = 'cost-estimate';
        }
    } catch (e) {
        // Ignore estimation errors
    }
}

function displaySources(sources) {
    const panel = elements.sourcesPanel;
    const list = elements.sourcesList;

    panel.classList.remove('hidden');

    // Use DocumentFragment for batch DOM operations
    const fragment = document.createDocumentFragment();

    sources.forEach(source => {
        const card = document.createElement('div');
        card.className = 'source-card';
        card.onclick = () => openSource(source.path);

        const scoreClass = source.score >= 70 ? '' : source.score >= 50 ? 'medium' : 'low';
        const name = source.path.split('/').pop();

        card.innerHTML = `
            <div class="source-card-header">
                <span class="source-card-path" title="${source.path}">${name}</span>
                <span class="source-card-score ${scoreClass}">${source.score}%</span>
            </div>
            <div class="source-card-content">${source.content}</div>
        `;

        fragment.appendChild(card);
    });

    list.innerHTML = '';
    list.appendChild(fragment);
}

function toggleSourcesPanel() {
    elements.sourcesPanel.classList.toggle('hidden');
}

async function openSource(path) {
    // Try to open in Obsidian
    const vaultName = state.vaultName || 'MyVault';
    const obsidianUrl = `obsidian://open?vault=${encodeURIComponent(vaultName)}&file=${encodeURIComponent(path)}`;
    window.open(obsidianUrl, '_blank');
}

// Provider functions
function updateProvider() {
    state.provider = elements.providerSelect.value;

    // Show model selector only for GPT provider
    if (elements.modelSelect) {
        elements.modelSelect.style.display = state.provider === 'gpt' ? 'block' : 'none';
    }
}

function updateModel() {
    if (elements.modelSelect) {
        state.model = elements.modelSelect.value;
        localStorage.setItem('scribe_model', state.model);
    }
}

function loadModelSetting() {
    const saved = localStorage.getItem('scribe_model');
    if (saved && elements.modelSelect) {
        // Check if the saved model exists in options
        const options = Array.from(elements.modelSelect.options);
        if (options.some(opt => opt.value === saved)) {
            elements.modelSelect.value = saved;
            state.model = saved;
        }
    }
}

async function loadProviders() {
    try {
        const response = await fetch('/api/providers');
        const providers = await response.json();

        const select = elements.providerSelect;
        select.innerHTML = '';

        providers.forEach(p => {
            if (p.available) {
                const option = document.createElement('option');
                option.value = p.name;
                option.textContent = p.name.charAt(0).toUpperCase() + p.name.slice(1);
                select.appendChild(option);
            }
        });

        state.provider = select.value;
    } catch (e) {
        console.error('Error loading providers:', e);
    }
}

async function loadVaultStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();

        // Store vault name for obsidian:// links
        state.vaultName = stats.vault_name || 'MyVault';

        elements.vaultStats.innerHTML = `
            <span class="stat-item">${stats.total_files} files indexed</span>
            <span class="stat-item">${stats.total_chunks} chunks</span>
        `;
    } catch (e) {
        elements.vaultStats.innerHTML = '<span class="stat-item">Unable to load stats</span>';
    }
}

// History functions
function newChat() {
    state.messages = [];
    state.history = [];
    state.sources = [];

    elements.messages.innerHTML = '';
    elements.welcomeScreen.classList.remove('hidden');
    elements.chatContainer.classList.add('hidden');
    elements.sourcesPanel.classList.add('hidden');
    elements.costEstimate.textContent = '';
}

function saveHistory() {
    const saved = JSON.parse(localStorage.getItem('aetherion_chats') || '[]');

    // Only save if we have messages
    if (state.history.length === 0) return;

    const chatId = Date.now();
    const preview = state.history[0]?.content?.slice(0, 50) || 'New chat';

    saved.unshift({
        id: chatId,
        preview,
        history: state.history,
        timestamp: new Date().toISOString()
    });

    // Keep last 20 chats
    localStorage.setItem('aetherion_chats', JSON.stringify(saved.slice(0, 20)));
    loadHistory();
}

function loadHistory() {
    const saved = JSON.parse(localStorage.getItem('aetherion_chats') || '[]');
    const container = elements.chatHistory;

    container.innerHTML = '';

    saved.slice(0, 10).forEach(chat => {
        const item = document.createElement('div');
        item.className = 'history-item';
        item.textContent = chat.preview + '...';
        item.onclick = () => loadChat(chat);
        container.appendChild(item);
    });
}

function loadChat(chat) {
    state.history = chat.history;

    elements.welcomeScreen.classList.add('hidden');
    elements.chatContainer.classList.remove('hidden');
    elements.messages.innerHTML = '';

    chat.history.forEach(msg => {
        addMessage(msg.role, msg.content);
    });
}

// Settings
function openSettings() {
    elements.settingsModal.classList.remove('hidden');
}

function closeSettings() {
    elements.settingsModal.classList.add('hidden');
}

// Close modal on outside click
document.addEventListener('click', (e) => {
    const modals = [
        elements.settingsModal,
        document.getElementById('session-recap-modal'),
        document.getElementById('consistency-modal'),
        document.getElementById('save-modal')
    ];

    modals.forEach(modal => {
        if (e.target === modal) {
            modal.classList.add('hidden');
        }
    });
});

// =============================================================================
// CHARACTER VOICE MODE
// =============================================================================

// Store all characters for filtering
let allCharacters = [];

async function loadCharacters() {
    try {
        const response = await fetch('/api/characters');
        const data = await response.json();
        allCharacters = data.characters;

        renderCharacterSelect(allCharacters);
    } catch (e) {
        console.error('Error loading characters:', e);
    }
}

function renderCharacterSelect(characters) {
    const select = document.getElementById('character-select');
    select.innerHTML = '<option value="">Speak as Scribe</option>';

    // Group by kingdom
    const grouped = {};
    characters.forEach(char => {
        const group = char.kingdom || 'Other';
        if (!grouped[group]) grouped[group] = [];
        grouped[group].push(char);
    });

    // Sort kingdoms and render as optgroups
    Object.keys(grouped).sort().forEach(kingdom => {
        const optgroup = document.createElement('optgroup');
        optgroup.label = kingdom;

        // Sort characters within group, rulers first
        grouped[kingdom]
            .sort((a, b) => {
                if (a.type === 'Ruler' && b.type !== 'Ruler') return -1;
                if (b.type === 'Ruler' && a.type !== 'Ruler') return 1;
                return a.name.localeCompare(b.name);
            })
            .forEach(char => {
                const option = document.createElement('option');
                option.value = char.name;
                // Build label with type and deceased indicator
                let label = char.name;
                if (char.type === 'Ruler') label += ' (Ruler)';
                if (char.deceased) label += ' [Deceased]';
                option.textContent = label;
                option.dataset.type = char.type;
                option.dataset.deceased = char.deceased || false;
                optgroup.appendChild(option);
            });

        select.appendChild(optgroup);
    });
}

function filterCharacters() {
    const searchInput = document.getElementById('character-search');
    const query = searchInput.value.toLowerCase().trim();

    if (!query) {
        renderCharacterSelect(allCharacters);
        return;
    }

    const filtered = allCharacters.filter(char =>
        char.name.toLowerCase().includes(query) ||
        char.kingdom.toLowerCase().includes(query) ||
        char.type.toLowerCase().includes(query) ||
        (char.deceased && 'deceased'.includes(query))
    );

    renderCharacterSelect(filtered);
}

function updateCharacter() {
    const select = document.getElementById('character-select');
    state.character = select.value;

    // Update UI to show character mode
    if (state.character) {
        elements.messageInput.placeholder = `Speak to ${state.character}...`;
    } else {
        elements.messageInput.placeholder = 'Ask anything...';
    }
}

// Override sendMessage to use character mode when active
const originalSendMessage = sendMessage;
sendMessage = async function() {
    if (state.character) {
        await sendCharacterMessage();
    } else {
        await originalSendMessage();
    }
};

async function sendCharacterMessage() {
    const message = state.pendingMessage;
    const input = elements.messageInput;
    const inputTokens = state.costEstimate?.input_tokens || 0;
    const isFree = state.costEstimate?.is_free || false;

    // Clear input
    input.value = '';
    input.style.height = 'auto';
    elements.sendBtn.disabled = true;

    // Show chat container
    elements.welcomeScreen.classList.add('hidden');
    elements.chatContainer.classList.remove('hidden');

    // Add user message
    addMessage('user', message);

    // Show loading
    state.isLoading = true;
    showLoading();

    try {
        // Show character indicator
        const characterMsg = addMessage('assistant', '', true);
        const contentEl = characterMsg.querySelector('.message-body');

        // Add character badge
        contentEl.innerHTML = `<div class="character-indicator">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 10-16 0"/>
            </svg>
            Speaking as ${state.character}
        </div>`;

        let fullResponse = '';

        // Use character streaming endpoint
        const response = await fetch('/api/chat/character', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                character: state.character,
                history: state.history,
                sources: state.sources,
                provider: state.provider
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.chunk) {
                            fullResponse += data.chunk;
                            contentEl.innerHTML = `<div class="character-indicator">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <circle cx="12" cy="8" r="5"/><path d="M20 21a8 8 0 10-16 0"/>
                                </svg>
                                Speaking as ${state.character}
                            </div>` + marked.parse(fullResponse);
                            scrollToBottom();
                        }
                        if (data.done) break;
                    } catch (e) {}
                }
            }
        }

        // Add save button
        addMessageActions(characterMsg, fullResponse);

        // Update history
        state.history.push({ role: 'user', content: message });
        state.history.push({ role: 'assistant', content: fullResponse });

        saveHistory();

    } catch (error) {
        console.error('Error:', error);
        addMessage('assistant', `Error: ${error.message}`);
    } finally {
        state.isLoading = false;
        state.pendingMessage = null;
        hideLoading();
        elements.sendBtn.disabled = false;
    }
}

// =============================================================================
// SAVE TO VAULT
// =============================================================================

let pendingSaveContent = '';

function addMessageActions(messageEl, content) {
    const contentEl = messageEl.querySelector('.message-content');

    const actionsEl = document.createElement('div');
    actionsEl.className = 'message-actions';
    actionsEl.innerHTML = `
        <button class="action-btn" onclick="openSaveModal(this)" data-content="${encodeURIComponent(content)}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"/>
                <polyline points="17,21 17,13 7,13 7,21"/>
                <polyline points="7,3 7,8 15,8"/>
            </svg>
            Save to Vault
        </button>
        <button class="action-btn" onclick="copyMessage(this)" data-content="${encodeURIComponent(content)}">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
            </svg>
            Copy
        </button>
    `;

    contentEl.appendChild(actionsEl);
}

function openSaveModal(button) {
    pendingSaveContent = decodeURIComponent(button.dataset.content);

    // Load folders
    loadVaultFolders();

    // Set preview
    document.getElementById('save-preview').textContent = pendingSaveContent.substring(0, 500) + (pendingSaveContent.length > 500 ? '...' : '');

    // Clear filename
    document.getElementById('save-filename').value = '';

    document.getElementById('save-modal').classList.remove('hidden');
}

function closeSaveModal() {
    document.getElementById('save-modal').classList.add('hidden');
    pendingSaveContent = '';
}

async function loadVaultFolders() {
    try {
        const response = await fetch('/api/vault/folders');
        const data = await response.json();

        const select = document.getElementById('save-folder');
        select.innerHTML = '';

        data.folders.forEach(folder => {
            const option = document.createElement('option');
            option.value = folder;
            option.textContent = folder;
            select.appendChild(option);
        });
    } catch (e) {
        console.error('Error loading folders:', e);
    }
}

async function confirmSaveToVault() {
    const filename = document.getElementById('save-filename').value.trim();
    const folder = document.getElementById('save-folder').value;
    const addLinks = document.getElementById('save-auto-link').checked;

    if (!filename) {
        alert('Please enter a filename');
        return;
    }

    try {
        const response = await fetch('/api/vault/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                content: pendingSaveContent,
                filename,
                folder,
                add_links: addLinks
            })
        });

        const result = await response.json();

        if (result.success) {
            alert(`Saved: ${result.path}`);
            closeSaveModal();
        } else {
            alert(`Error: ${result.message}`);
        }
    } catch (e) {
        alert('Error saving file: ' + e.message);
    }
}

function copyMessage(button) {
    const content = decodeURIComponent(button.dataset.content);
    navigator.clipboard.writeText(content);

    // Visual feedback
    const originalText = button.innerHTML;
    button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20,6 9,17 4,12"/></svg> Copied!';
    setTimeout(() => {
        button.innerHTML = originalText;
    }, 2000);
}

// =============================================================================
// SESSION RECAP
// =============================================================================

let recapContent = '';

function openSessionRecap() {
    document.getElementById('session-recap-modal').classList.remove('hidden');
    document.getElementById('session-notes').value = '';
    document.getElementById('session-number').value = '';
    document.getElementById('recap-output').classList.add('hidden');
}

function closeSessionRecap() {
    document.getElementById('session-recap-modal').classList.add('hidden');
}

async function generateRecap() {
    const notes = document.getElementById('session-notes').value.trim();
    const sessionNumber = document.getElementById('session-number').value;

    if (!notes) {
        alert('Please paste your session notes');
        return;
    }

    const outputEl = document.getElementById('recap-output');
    const contentEl = document.getElementById('recap-content');

    outputEl.classList.remove('hidden');
    contentEl.innerHTML = '<div class="loading-indicator">Generating recap...</div>';
    recapContent = '';

    try {
        const response = await fetch('/api/session-recap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                notes,
                session_number: sessionNumber ? parseInt(sessionNumber) : null,
                provider: state.provider
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.chunk) {
                            recapContent += data.chunk;
                            contentEl.innerHTML = marked.parse(recapContent);
                        }
                        if (data.done && data.linked) {
                            recapContent = data.linked;
                            contentEl.innerHTML = marked.parse(recapContent);
                        }
                    } catch (e) {}
                }
            }
        }
    } catch (error) {
        contentEl.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

function saveRecapToVault() {
    pendingSaveContent = recapContent;
    document.getElementById('save-preview').textContent = recapContent.substring(0, 500);
    document.getElementById('save-filename').value = 'Session Recap';
    loadVaultFolders();
    document.getElementById('save-modal').classList.remove('hidden');
}

// =============================================================================
// CONSISTENCY CHECKER
// =============================================================================

function openConsistencyChecker() {
    document.getElementById('consistency-modal').classList.remove('hidden');
    document.getElementById('consistency-output').classList.add('hidden');
    loadEntities();
}

function closeConsistencyChecker() {
    document.getElementById('consistency-modal').classList.add('hidden');
}

async function loadEntities() {
    try {
        const response = await fetch('/api/consistency/entities');
        const data = await response.json();

        const select = document.getElementById('entity-select');
        select.innerHTML = '<option value="">Select an entity...</option>';

        data.entities.forEach(entity => {
            const option = document.createElement('option');
            option.value = entity.name;
            option.textContent = `${entity.name} (${entity.files} files, ${entity.mentions} mentions)`;
            select.appendChild(option);
        });
    } catch (e) {
        console.error('Error loading entities:', e);
    }
}

async function runConsistencyCheck() {
    const entity = document.getElementById('entity-select').value;

    if (!entity) {
        alert('Please select an entity');
        return;
    }

    const outputEl = document.getElementById('consistency-output');
    const contentEl = document.getElementById('consistency-content');

    outputEl.classList.remove('hidden');
    contentEl.innerHTML = '<div class="loading-indicator">Analyzing consistency...</div>';

    try {
        const response = await fetch('/api/consistency/check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                entity,
                provider: state.provider
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullContent = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const text = decoder.decode(value);
            const lines = text.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.chunk) {
                            fullContent += data.chunk;
                            contentEl.innerHTML = marked.parse(fullContent);
                        }
                    } catch (e) {}
                }
            }
        }
    } catch (error) {
        contentEl.innerHTML = `<div class="error">Error: ${error.message}</div>`;
    }
}

// =============================================================================
// UPDATE MESSAGE DISPLAY TO INCLUDE SAVE BUTTON
// =============================================================================

// Wrap addMessage to include action buttons for assistant messages
const originalAddMessage = addMessage;
addMessage = function(role, content, isStreaming = false) {
    const messageEl = originalAddMessage(role, content, isStreaming);

    // Add action buttons to completed assistant messages
    if (role === 'assistant' && !isStreaming && content) {
        addMessageActions(messageEl, content);
    }

    return messageEl;
};

// Load characters function is called in main init

// =============================================================================
// MANUAL SOURCE SELECTION
// =============================================================================

// Pinned sources state
let pinnedSources = [];
let allVaultNotes = [];
let pendingUrlSource = null;
let pendingFileSource = null;

function openSourcePicker() {
    document.getElementById('source-picker-modal').classList.remove('hidden');
    loadVaultNotes();
}

function closeSourcePicker() {
    document.getElementById('source-picker-modal').classList.add('hidden');
}

function switchSourceTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.source-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tab);
    });

    // Update tab content
    document.querySelectorAll('.source-tab-content').forEach(content => {
        content.classList.toggle('active', content.id === `source-tab-${tab}`);
    });
}

// Vault Notes
async function loadVaultNotes() {
    try {
        const response = await fetch('/api/vault/notes');
        const data = await response.json();
        allVaultNotes = data.notes;
        renderVaultNotes(allVaultNotes);
    } catch (e) {
        console.error('Error loading vault notes:', e);
        document.getElementById('vault-notes-list').innerHTML = '<div class="error">Failed to load notes</div>';
    }
}

function renderVaultNotes(notes) {
    const container = document.getElementById('vault-notes-list');

    if (notes.length === 0) {
        container.innerHTML = '<div class="empty-state">No notes found</div>';
        return;
    }

    // Group by folder
    const grouped = {};
    notes.forEach(note => {
        const folder = note.folder || 'Root';
        if (!grouped[folder]) grouped[folder] = [];
        grouped[folder].push(note);
    });

    const fragment = document.createDocumentFragment();

    Object.keys(grouped).sort().forEach(folder => {
        const folderEl = document.createElement('div');
        folderEl.className = 'vault-folder';

        const headerEl = document.createElement('div');
        headerEl.className = 'vault-folder-header';
        headerEl.innerHTML = `
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/>
            </svg>
            ${folder}
        `;
        headerEl.onclick = () => folderEl.classList.toggle('collapsed');
        folderEl.appendChild(headerEl);

        const notesEl = document.createElement('div');
        notesEl.className = 'vault-folder-notes';

        grouped[folder].forEach(note => {
            const isPinned = pinnedSources.some(s => s.path === note.path && s.type === 'vault');

            const noteEl = document.createElement('div');
            noteEl.className = `vault-note-item ${isPinned ? 'pinned' : ''}`;
            noteEl.innerHTML = `
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                    <path d="M14 2v6h6"/>
                </svg>
                <span class="vault-note-name">${note.name}</span>
                ${isPinned ? '<span class="pinned-badge">Pinned</span>' : ''}
            `;
            noteEl.onclick = () => toggleVaultNote(note);
            notesEl.appendChild(noteEl);
        });

        folderEl.appendChild(notesEl);
        fragment.appendChild(folderEl);
    });

    container.innerHTML = '';
    container.appendChild(fragment);
}

function filterVaultNotes() {
    const query = document.getElementById('vault-note-search').value.toLowerCase().trim();

    if (!query) {
        renderVaultNotes(allVaultNotes);
        return;
    }

    const filtered = allVaultNotes.filter(note =>
        note.name.toLowerCase().includes(query) ||
        note.folder.toLowerCase().includes(query)
    );

    renderVaultNotes(filtered);
}

async function toggleVaultNote(note) {
    const existingIndex = pinnedSources.findIndex(s => s.path === note.path && s.type === 'vault');

    if (existingIndex >= 0) {
        // Remove from pinned
        pinnedSources.splice(existingIndex, 1);
    } else {
        // Fetch full content and add to pinned
        try {
            const response = await fetch('/api/vault/note', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: note.path })
            });
            const data = await response.json();

            if (data.error) {
                alert(data.error);
                return;
            }

            pinnedSources.push({
                path: note.path,
                name: note.name,
                content: data.content,
                type: 'vault',
                score: 100
            });
        } catch (e) {
            alert('Failed to load note: ' + e.message);
            return;
        }
    }

    renderVaultNotes(allVaultNotes.filter(n => {
        const query = document.getElementById('vault-note-search').value.toLowerCase().trim();
        if (!query) return true;
        return n.name.toLowerCase().includes(query) || n.folder.toLowerCase().includes(query);
    }));
    updatePinnedSourcesDisplay();
}

// URL Fetching
async function fetchUrlSource() {
    const urlInput = document.getElementById('source-url-input');
    const url = urlInput.value.trim();

    if (!url) {
        alert('Please enter a URL');
        return;
    }

    const preview = document.getElementById('url-preview');
    const titleEl = document.getElementById('url-preview-title');
    const contentEl = document.getElementById('url-preview-content');

    preview.classList.remove('hidden');
    titleEl.textContent = 'Fetching...';
    contentEl.innerHTML = '<div class="loading-indicator">Loading page content...</div>';

    try {
        const response = await fetch('/api/fetch-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await response.json();

        if (data.error) {
            titleEl.textContent = 'Error';
            contentEl.innerHTML = `<div class="error">${data.error}</div>`;
            return;
        }

        pendingUrlSource = data;
        titleEl.textContent = data.title;
        contentEl.textContent = data.content.substring(0, 1000) + (data.content.length > 1000 ? '...' : '');
    } catch (e) {
        titleEl.textContent = 'Error';
        contentEl.innerHTML = `<div class="error">Failed to fetch URL: ${e.message}</div>`;
    }
}

function addUrlToPinned() {
    if (!pendingUrlSource) return;

    // Check if already pinned
    if (pinnedSources.some(s => s.path === pendingUrlSource.url && s.type === 'url')) {
        alert('This URL is already pinned');
        return;
    }

    pinnedSources.push({
        path: pendingUrlSource.url,
        name: pendingUrlSource.title,
        content: pendingUrlSource.content,
        type: 'url',
        score: 100
    });

    updatePinnedSourcesDisplay();
    document.getElementById('source-url-input').value = '';
    document.getElementById('url-preview').classList.add('hidden');
    pendingUrlSource = null;

    // Show success
    alert('URL added to sources!');
}

// File Upload
function handleFileUpload(event) {
    const file = event.target.files[0];
    if (!file) return;

    const preview = document.getElementById('file-preview');
    const nameEl = document.getElementById('file-preview-name');
    const contentEl = document.getElementById('file-preview-content');

    preview.classList.remove('hidden');
    nameEl.textContent = file.name;
    contentEl.innerHTML = '<div class="loading-indicator">Processing file...</div>';

    const formData = new FormData();
    formData.append('file', file);

    fetch('/api/upload-source', {
        method: 'POST',
        body: formData
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            contentEl.innerHTML = `<div class="error">${data.error}</div>`;
            return;
        }

        pendingFileSource = data;

        if (data.type === 'image') {
            contentEl.innerHTML = `<img src="data:${data.mime_type};base64,${data.content}" alt="${data.name}" style="max-width: 100%; max-height: 200px;">`;
        } else {
            contentEl.textContent = data.content.substring(0, 1000) + (data.content.length > 1000 ? '...' : '');
        }
    })
    .catch(e => {
        contentEl.innerHTML = `<div class="error">Failed to process file: ${e.message}</div>`;
    });
}

function addFileToPinned() {
    if (!pendingFileSource) return;

    // Check if already pinned
    if (pinnedSources.some(s => s.name === pendingFileSource.name && s.type === 'file')) {
        alert('This file is already pinned');
        return;
    }

    pinnedSources.push({
        path: pendingFileSource.name,
        name: pendingFileSource.name,
        content: pendingFileSource.content,
        type: pendingFileSource.type,
        mime_type: pendingFileSource.mime_type,
        score: 100
    });

    updatePinnedSourcesDisplay();
    document.getElementById('file-preview').classList.add('hidden');
    document.getElementById('file-upload-input').value = '';
    pendingFileSource = null;

    alert('File added to sources!');
}

// Drag and drop for file upload (in modal)
document.addEventListener('DOMContentLoaded', () => {
    const dropZone = document.getElementById('file-drop-zone');
    if (dropZone) {
        dropZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            dropZone.classList.add('dragover');
        });

        dropZone.addEventListener('dragleave', () => {
            dropZone.classList.remove('dragover');
        });

        dropZone.addEventListener('drop', (e) => {
            e.preventDefault();
            dropZone.classList.remove('dragover');
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                document.getElementById('file-upload-input').files = files;
                handleFileUpload({ target: { files } });
            }
        });
    }

    // Global drag and drop into chat area
    setupChatDragDrop();
});

// Global drag and drop into chat
function setupChatDragDrop() {
    const mainContent = document.querySelector('.main-content');
    if (!mainContent) return;

    let dropIndicator = null;

    mainContent.addEventListener('dragenter', (e) => {
        e.preventDefault();
        if (!dropIndicator) {
            dropIndicator = document.createElement('div');
            dropIndicator.className = 'drop-indicator';
            dropIndicator.innerHTML = `
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                    <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"/>
                </svg>
                <p>Drop files or URLs to add as sources</p>
            `;
            document.body.appendChild(dropIndicator);
        }
        mainContent.classList.add('drag-over');
    });

    mainContent.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    mainContent.addEventListener('dragleave', (e) => {
        // Only hide if leaving main content entirely
        if (!mainContent.contains(e.relatedTarget)) {
            mainContent.classList.remove('drag-over');
            if (dropIndicator) {
                dropIndicator.remove();
                dropIndicator = null;
            }
        }
    });

    mainContent.addEventListener('drop', async (e) => {
        e.preventDefault();
        mainContent.classList.remove('drag-over');
        if (dropIndicator) {
            dropIndicator.remove();
            dropIndicator = null;
        }

        // Handle dropped files
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            for (const file of files) {
                await processDroppedFile(file);
            }
            return;
        }

        // Handle dropped URLs/text
        const text = e.dataTransfer.getData('text');
        if (text) {
            // Check if it's a URL
            if (text.match(/^https?:\/\//i) || text.match(/^www\./i)) {
                await processDroppedUrl(text);
            } else {
                // Treat as text content
                pinnedSources.push({
                    path: 'Dropped Text',
                    name: 'Dropped Text',
                    content: text,
                    type: 'text',
                    score: 100
                });
                updatePinnedSourcesDisplay();
            }
        }
    });
}

async function processDroppedFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch('/api/upload-source', {
            method: 'POST',
            body: formData
        });
        const data = await response.json();

        if (data.error) {
            console.error('Error processing file:', data.error);
            return;
        }

        pinnedSources.push({
            path: data.name,
            name: data.name,
            content: data.content,
            type: data.type,
            mime_type: data.mime_type,
            score: 100
        });
        updatePinnedSourcesDisplay();
    } catch (e) {
        console.error('Failed to process dropped file:', e);
    }
}

async function processDroppedUrl(url) {
    try {
        const response = await fetch('/api/fetch-url', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await response.json();

        if (data.error) {
            console.error('Error fetching URL:', data.error);
            return;
        }

        pinnedSources.push({
            path: data.url,
            name: data.title,
            content: data.content,
            type: 'url',
            score: 100
        });
        updatePinnedSourcesDisplay();
    } catch (e) {
        console.error('Failed to fetch dropped URL:', e);
    }
}

// Pinned Sources Display
function updatePinnedSourcesDisplay() {
    const container = document.getElementById('pinned-sources');
    const list = document.getElementById('pinned-sources-list');

    if (pinnedSources.length === 0) {
        container.classList.add('hidden');
        return;
    }

    container.classList.remove('hidden');
    list.innerHTML = '';

    pinnedSources.forEach((source, index) => {
        const badge = document.createElement('div');
        badge.className = `pinned-source-badge ${source.type}`;

        const icon = source.type === 'vault' ?
            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><path d="M14 2v6h6"/></svg>' :
            source.type === 'url' ?
            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M2 12h20"/></svg>' :
            source.type === 'image' ?
            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><path d="M21 15l-5-5L5 21"/></svg>' :
            '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><path d="M13 2v7h7"/></svg>';

        badge.innerHTML = `
            ${icon}
            <span class="pinned-source-name" title="${source.path}">${source.name}</span>
            <button class="remove-pinned-btn" onclick="removePinnedSource(${index})" title="Remove">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M18 6L6 18M6 6l12 12"/>
                </svg>
            </button>
        `;
        list.appendChild(badge);
    });
}

function removePinnedSource(index) {
    pinnedSources.splice(index, 1);
    updatePinnedSourcesDisplay();
}

function clearPinnedSources() {
    pinnedSources = [];
    updatePinnedSourcesDisplay();
}

// Override fetchSources to combine with pinned sources
const originalFetchSources = fetchSources;
fetchSources = async function(query) {
    // Get auto-found sources
    const autoSources = await originalFetchSources(query);

    // Combine with pinned sources (pinned first, avoiding duplicates)
    const combined = [...pinnedSources];
    autoSources.forEach(source => {
        // Skip if already in pinned
        if (!pinnedSources.some(p => p.path === source.path)) {
            combined.push(source);
        }
    });

    return combined;
};

// Reset pinned sources on new chat
const originalNewChat = newChat;
newChat = function() {
    originalNewChat();
    pinnedSources = [];
    updatePinnedSourcesDisplay();
};

// =============================================================================
// MCP (MODEL CONTEXT PROTOCOL) INTEGRATION
// =============================================================================

let mcpServers = [];

async function loadMCPServers() {
    try {
        const response = await fetch('/api/mcp/servers');
        const data = await response.json();
        mcpServers = data.servers || [];
        renderMCPServers();
    } catch (e) {
        console.error('Error loading MCP servers:', e);
        document.getElementById('mcp-servers-list').innerHTML = '<div class="empty-state">No MCP servers configured</div>';
    }
}

function renderMCPServers() {
    const container = document.getElementById('mcp-servers-list');

    if (mcpServers.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <p>No MCP servers configured</p>
                <p class="help-text">Add an MCP server to access external tools and data sources</p>
            </div>
        `;
        return;
    }

    const fragment = document.createDocumentFragment();

    mcpServers.forEach(server => {
        const serverEl = document.createElement('div');
        serverEl.className = `mcp-server-item ${server.connected ? 'connected' : ''}`;
        serverEl.innerHTML = `
            <div class="mcp-server-info">
                <div class="mcp-server-name">
                    <span class="mcp-status-dot ${server.connected ? 'connected' : ''}"></span>
                    ${server.name}
                </div>
                <div class="mcp-server-details">
                    ${server.connected ? `${server.tools.length} tools, ${server.resources} resources` : server.command}
                </div>
            </div>
            <div class="mcp-server-actions">
                ${server.connected ?
                    `<button class="btn-sm btn-secondary" onclick="disconnectMCPServer('${server.name}')">Disconnect</button>` :
                    `<button class="btn-sm btn-primary" onclick="connectMCPServer('${server.name}')">Connect</button>`
                }
                <button class="btn-sm btn-danger" onclick="removeMCPServer('${server.name}')" title="Remove">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/>
                    </svg>
                </button>
            </div>
        `;
        fragment.appendChild(serverEl);
    });

    container.innerHTML = '';
    container.appendChild(fragment);

    // Load resources if any server is connected
    if (mcpServers.some(s => s.connected)) {
        loadMCPResources();
    }
}

async function connectMCPServer(name) {
    const serverEl = document.querySelector(`.mcp-server-item .mcp-server-name:has-text("${name}")`);
    const btn = event.target;
    btn.textContent = 'Connecting...';
    btn.disabled = true;

    try {
        const response = await fetch(`/api/mcp/servers/${name}/connect`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            await loadMCPServers();
        } else {
            alert(`Failed to connect: ${data.error}`);
            btn.textContent = 'Connect';
            btn.disabled = false;
        }
    } catch (e) {
        alert(`Connection error: ${e.message}`);
        btn.textContent = 'Connect';
        btn.disabled = false;
    }
}

async function disconnectMCPServer(name) {
    try {
        await fetch(`/api/mcp/servers/${name}/disconnect`, { method: 'POST' });
        await loadMCPServers();
    } catch (e) {
        console.error('Error disconnecting:', e);
    }
}

async function removeMCPServer(name) {
    if (!confirm(`Remove MCP server "${name}"?`)) return;

    try {
        await fetch(`/api/mcp/servers/${name}`, { method: 'DELETE' });
        await loadMCPServers();
    } catch (e) {
        alert(`Failed to remove server: ${e.message}`);
    }
}

async function loadMCPResources() {
    const section = document.getElementById('mcp-resources-section');
    const container = document.getElementById('mcp-resources-list');

    try {
        const response = await fetch('/api/mcp/resources');
        const data = await response.json();

        if (!data.resources || data.resources.length === 0) {
            section.classList.add('hidden');
            return;
        }

        section.classList.remove('hidden');
        container.innerHTML = '';

        data.resources.forEach(resource => {
            const resourceEl = document.createElement('div');
            resourceEl.className = 'mcp-resource-item';
            resourceEl.innerHTML = `
                <div class="mcp-resource-info">
                    <span class="mcp-resource-name">${resource.name || resource.uri}</span>
                    <span class="mcp-resource-server">${resource.server}</span>
                </div>
                <button class="btn-sm btn-primary" onclick="addMCPResourceToPinned('${resource.server}', '${resource.uri}', '${resource.name || resource.uri}')">
                    Add
                </button>
            `;
            container.appendChild(resourceEl);
        });
    } catch (e) {
        console.error('Error loading MCP resources:', e);
        section.classList.add('hidden');
    }
}

async function addMCPResourceToPinned(server, uri, name) {
    try {
        const response = await fetch('/api/mcp/resources/read', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server, uri })
        });
        const data = await response.json();

        if (data.error) {
            alert(`Failed to read resource: ${data.error}`);
            return;
        }

        pinnedSources.push({
            path: uri,
            name: name,
            content: data.content,
            type: 'mcp',
            score: 100
        });
        updatePinnedSourcesDisplay();
        alert('MCP resource added to sources!');
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

function openMCPServerConfig() {
    document.getElementById('mcp-config-modal').classList.remove('hidden');
    document.getElementById('mcp-server-name').value = '';
    document.getElementById('mcp-server-command').value = '';
    document.getElementById('mcp-server-args').value = '';
}

function closeMCPConfig() {
    document.getElementById('mcp-config-modal').classList.add('hidden');
}

async function addMCPServer() {
    const name = document.getElementById('mcp-server-name').value.trim();
    const command = document.getElementById('mcp-server-command').value.trim();
    const argsStr = document.getElementById('mcp-server-args').value.trim();

    if (!name || !command) {
        alert('Please enter a name and command');
        return;
    }

    const args = argsStr ? argsStr.split(/\s+/) : [];

    try {
        const response = await fetch('/api/mcp/servers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, command, args })
        });
        const data = await response.json();

        if (data.success) {
            closeMCPConfig();
            await loadMCPServers();
        } else {
            alert(`Failed to add server: ${data.error}`);
        }
    } catch (e) {
        alert(`Error: ${e.message}`);
    }
}

// Load MCP servers when MCP tab is opened
const originalSwitchSourceTab = switchSourceTab;
switchSourceTab = function(tab) {
    originalSwitchSourceTab(tab);
    if (tab === 'mcp') {
        loadMCPServers();
    }
};
