/**
 * Aetherion AI - Web Interface JavaScript
 */

// State
let state = {
    messages: [],
    sources: [],
    history: [],
    provider: 'gpt',
    contextSize: 20,
    isLoading: false,
    currentStreamController: null,
    pendingMessage: null,
    costEstimate: null,
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
    'provider-select', 'deep-search', 'show-sources', 'confirm-send', 'cost-estimate',
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
function loadModuleSettings() {
    const modules = JSON.parse(localStorage.getItem('aetherion_modules') || '{}');

    // Set defaults if not set
    const defaults = {
        worldbuilding: false,
        campaign: false,
        character: true
    };

    Object.keys(defaults).forEach(mod => {
        if (modules[mod] === undefined) modules[mod] = defaults[mod];
    });

    // Update checkboxes if they exist
    Object.keys(modules).forEach(mod => {
        const checkbox = document.getElementById(`module-${mod}`);
        if (checkbox) checkbox.checked = modules[mod];
    });

    // Apply visibility
    applyModuleVisibility(modules);

    return modules;
}

function saveModuleSettings() {
    const modules = {};
    ['worldbuilding', 'campaign', 'character'].forEach(mod => {
        const checkbox = document.getElementById(`module-${mod}`);
        if (checkbox) modules[mod] = checkbox.checked;
    });

    localStorage.setItem('aetherion_modules', JSON.stringify(modules));
    applyModuleVisibility(modules);
}

function applyModuleVisibility(modules) {
    document.querySelectorAll('[data-module]').forEach(el => {
        const mod = el.getAttribute('data-module');
        if (modules[mod] === false) {
            el.style.display = 'none';
        } else {
            el.style.display = '';
        }
    });
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
    const models = {
        'gpt': 'gpt-5-nano',
        'openai': 'gpt-5-nano',
        'gemini': 'gemini-2.5-flash-lite',
        'anthropic': 'claude-sonnet-4-20250514',
        'claude': 'claude-sonnet-4-20250514',
        'ollama': 'llama3',
        'groq': 'llama-3.3-70b-versatile',
        'openrouter': 'anthropic/claude-3.5-sonnet'
    };
    return models[provider] || 'gpt-5-nano';
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
            provider: state.provider
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
    elements.costEstimate.textContent = 'Searching vault...';

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
    const author = role === 'user' ? 'You' : 'Aetherion';

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
    const obsidianUrl = `obsidian://open?vault=Aetherion&file=${encodeURIComponent(path)}`;
    window.open(obsidianUrl, '_blank');
}

// Provider functions
function updateProvider() {
    state.provider = elements.providerSelect.value;
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
    select.innerHTML = '<option value="">Speak as Aetherion</option>';

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
        elements.messageInput.placeholder = 'Ask about your world...';
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
