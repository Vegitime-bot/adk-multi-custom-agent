/**
 * Admin Panel JavaScript - Tailwind CSS Edition
 * 챗봇 관리자 페이지 기능 (계층 뷰, 권한 관리, 통계 대시보드 포함)
 */

// Global state
let chatbots = [];
let currentFilter = 'all';
let currentView = 'store';
let deleteTargetId = null;
let detailChatbotId = null;
let currentUser = null;  // 현재 사용자 정보
let isAdmin = false;     // 관리자 여부

// DB 목록 (mock)
const availableDBs = ['db_new', 'db_001', 'db_002', 'db_003', 'db_004', 
                      'db_hr_policy', 'db_hr_benefit', 'db_hr_overview',
                      'db_backend', 'db_frontend', 'db_devops', 'db_tech_overview',
                      'db_rtl_verilog', 'db_rtl_synthesis'];

// Initialize
document.addEventListener('DOMContentLoaded', async () => {
    await loadCurrentUser();  // 사용자 정보 먼저 로드
    loadChatbots();
    loadStats();
    setupEventListeners();
    
    // 챗봇 추가 버튼에 DB 목록 로드 연결
    const addBtn = document.getElementById('addChatbotBtn');
    if (addBtn) {
        addBtn.addEventListener('click', () => {
            openAddChatbotModal();
            loadDBSelection();
        });
    }
});

// 현재 사용자 정보 로드
async function loadCurrentUser() {
    try {
        const response = await fetch('/main/api/me');
        if (response.ok) {
            currentUser = await response.json();
            isAdmin = currentUser.is_admin || false;
            console.log('Current user:', currentUser, 'Is admin:', isAdmin);
            
            // 사용자 정보 UI 업데이트
            const userNameEl = document.getElementById('userName');
            const userRoleEl = document.getElementById('userRole');
            const userAvatarEl = document.getElementById('userAvatar');
            
            if (userNameEl) userNameEl.textContent = currentUser.knox_id || 'Unknown';
            if (userRoleEl) userRoleEl.textContent = currentUser.is_admin ? 'System Admin' : 'User';
            if (userAvatarEl) {
                const initial = (currentUser.knox_id || 'U').charAt(0).toUpperCase();
                userAvatarEl.textContent = initial;
            }
            // 관리자면 챗봇 추가 버튼 표시
            const addBtn = document.getElementById('addChatbotBtn');
            if (addBtn && isAdmin) {
                addBtn.classList.remove('hidden');
            }
        }
    } catch (error) {
        console.error('Failed to load user info:', error);
    }
}

// ===== 챗봇 추가 모달 =====
function openAddChatbotModal() {
    document.getElementById('addChatbotModal').classList.remove('hidden');
    document.getElementById('addChatbotModal').classList.add('flex');
    
    // Parent 목록 로드
    const parentSelect = document.getElementById('newChatbotParent');
    parentSelect.innerHTML = '<option value="">상위 Agent를 선택하세요</option>';
    const parents = chatbots.filter(c => c.sub_chatbots?.length > 0 || c.type === 'parent');
    parents.forEach(parent => {
        const opt = document.createElement('option');
        opt.value = parent.id;
        opt.textContent = `${parent.name} (${parent.id})`;
        parentSelect.appendChild(opt);
    });
}

function closeAddChatbotModal() {
    document.getElementById('addChatbotModal').classList.add('hidden');
    document.getElementById('addChatbotModal').classList.remove('flex');
    document.getElementById('addChatbotForm').reset();
    document.getElementById('parentSelectContainer').classList.add('hidden');
}

// DB 목록 로드 및 표시
async function loadDBSelection() {
    const container = document.getElementById('dbSelectionContainer');
    if (!container) return;
    
    container.innerHTML = '<p class="text-xs text-on-surface-variant">DB 목록을 불러오는 중...</p>';
    
    try {
        const response = await fetch('/main/api/databases');
        const dbList = await response.json();
        
        if (!Array.isArray(dbList) || dbList.length === 0) {
            container.innerHTML = '<p class="text-xs text-on-surface-variant">사용 가능한 DB가 없습니다</p>';
            return;
        }
        
        container.innerHTML = '';
        dbList.forEach(dbId => {
            const label = document.createElement('label');
            label.className = 'flex items-center gap-2 cursor-pointer py-1';
            label.innerHTML = `
                <input type="checkbox" name="dbSelection" value="${dbId}" class="w-4 h-4 text-primary rounded">
                <span class="text-sm text-on-surface">${dbId}</span>
            `;
            container.appendChild(label);
        });
    } catch (error) {
        console.error('DB 목록 로드 실패:', error);
        container.innerHTML = '<p class="text-xs text-error">DB 목록 로드 실패</p>';
    }
}

// 챗봘 유형 변경 시 상위 선택 표시
function setupAddChatbotListeners() {
    const typeInputs = document.querySelectorAll('input[name="newChatbotType"]');
    typeInputs.forEach(input => {
        input.addEventListener('change', () => {
            const parentContainer = document.getElementById('parentSelectContainer');
            if (input.value === 'child') {
                parentContainer.classList.remove('hidden');
            } else {
                parentContainer.classList.add('hidden');
            }
        });
    });
}

async function saveNewChatbot(event) {
    event.preventDefault();
    
    const id = document.getElementById('newChatbotId').value.trim();
    const name = document.getElementById('newChatbotName').value.trim();
    const description = document.getElementById('newChatbotDesc').value.trim();
    const type = document.querySelector('input[name="newChatbotType"]:checked').value;
    const parentId = document.getElementById('newChatbotParent').value;
    const systemPrompt = document.getElementById('newChatbotPrompt').value.trim();
    const keywordsInput = document.getElementById('newChatbotKeywords')?.value.trim() || '';
    
    // 키워드 파싱 (쉼표로 구분, 공백 제거)
    const keywords = keywordsInput
        .split(',')
        .map(k => k.trim())
        .filter(k => k.length > 0);
    
    // 선택된 DB 수집
    const selectedDBs = [];
    const dbCheckboxes = document.querySelectorAll('input[name="dbSelection"]:checked');
    dbCheckboxes.forEach(cb => selectedDBs.push(cb.value));
    
    if (!id || !name) {
        showToast('ID와 이름은 필수입니다', 'error');
        return;
    }
    
    const chatbotData = {
        id: id,
        name: name,
        description: description,
        active: true,
        db_ids: selectedDBs,
        keywords: keywords,
        sub_chatbots: [],
        type: type,
        system_prompt: systemPrompt,
        policy: {
            temperature: 0.3,
            max_tokens: 1024,
            stream: true,
            supported_modes: ["tool", "agent"],
            default_mode: "agent",
            max_messages: 20
        }
    };
    
    if (type === 'child' && parentId) {
        chatbotData.parent_id = parentId;
        chatbotData.parent = parentId;
    }
    
    try {
        const response = await fetch('/main/api/chatbots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(chatbotData)
        });
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || '챗봇 생성 실패');
        }
        
        showToast('챗봇이 생성되었습니다', 'success');
        closeAddChatbotModal();
        await loadChatbots();
    } catch (error) {
        showToast('챗봇 생성 실패: ' + error.message, 'error');
    }
}

// 초기화 시 리스너 설정
setTimeout(setupAddChatbotListeners, 100);

// ===== 뷰 전환 =====
function switchView(viewName) {
    currentView = viewName;
    
    // Update nav items - Tailwind 스타일
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active', 'text-primary', 'font-semibold', 'border-r-4', 'border-primary', 'bg-white/50');
        item.classList.add('text-slate-500');
        if (item.dataset.view === viewName) {
            item.classList.add('active', 'text-primary', 'font-semibold', 'border-r-4', 'border-primary', 'bg-white/50');
            item.classList.remove('text-slate-500');
        }
    });
    
    // Show/hide views
    document.querySelectorAll('.view').forEach(view => {
        view.classList.add('hidden');
        view.classList.remove('active');
    });
    const activeView = document.getElementById(`view-${viewName}`);
    if (activeView) {
        activeView.classList.remove('hidden');
        activeView.classList.add('active');
    }
    
    // Load view-specific data
    if (viewName === 'hierarchy') {
        loadHierarchy();
    } else if (viewName === 'permissions') {
        switchUserTab('restricted');  // 권한 관리 탭 기본값: restricted
    } else if (viewName === 'stats') {
        loadStatsDashboard();
    }
}

// ===== 챗봇 목록 로드 =====
async function loadChatbots() {
    const grid = document.getElementById('chatbotGrid');
    grid.innerHTML = `
        <div class="col-span-full flex justify-center py-20">
            <div class="animate-spin w-10 h-10 border-3 border-primary/20 border-t-primary rounded-full"></div>
        </div>
    `;
    
    try {
        const response = await fetch('/main/api/chatbots');
        if (!response.ok) throw new Error('Failed to load');
        
        const data = await response.json();
        if (!Array.isArray(data)) {
            console.error('API 응답이 배열이 아님:', data);
            throw new Error('잘못된 데이터 형식');
        }
        chatbots = data;
        renderChatbots();
        populateParentSelect();
        loadStoreStats();
    } catch (error) {
        console.error('Error loading chatbots:', error);
        grid.innerHTML = `
            <div class="col-span-full text-center py-20">
                <div class="text-5xl mb-4">⚠️</div>
                <h3 class="text-lg font-semibold text-on-surface mb-2">로드 실패</h3>
                <p class="text-on-surface-variant">${error.message}</p>
            </div>
        `;
    }
}

// ===== 통계 로드 =====
async function loadStats() {
    try {
        const response = await fetch('/main/api/stats');
        if (!response.ok) return;
        
        const stats = await response.json();
        document.getElementById('statTotal').textContent = stats.total;
        document.getElementById('statParents').textContent = stats.parents;
        document.getElementById('statActive').textContent = stats.active;
    } catch (error) {
        console.error('Error loading stats:', error);
    }
}

function loadStoreStats() {
    const total = chatbots.length;
    const parents = chatbots.filter(c => c.type === 'parent').length;
    const active = chatbots.filter(c => c.active).length;
    
    document.getElementById('statTotal').textContent = total;
    document.getElementById('statParents').textContent = parents;
    document.getElementById('statActive').textContent = active;
}

// ===== 챗봇 카드 렌더링 (Tailwind 스타일) =====
function renderChatbots() {
    const grid = document.getElementById('chatbotGrid');
    if (!grid) return;
    
    const searchInput = document.getElementById('globalSearchInput');
    const searchTerm = searchInput ? searchInput.value.toLowerCase() : '';
    
    let filtered = chatbots.filter(cb => {
        if (currentFilter !== 'all' && cb.type !== currentFilter) return false;
        if (searchTerm && !cb.name.toLowerCase().includes(searchTerm) && 
            !cb.description?.toLowerCase().includes(searchTerm) &&
            !cb.id.toLowerCase().includes(searchTerm)) return false;
        return true;
    });
    
    if (filtered.length === 0) {
        grid.innerHTML = `
            <div class="col-span-full text-center py-20 border-2 border-dashed border-outline-variant rounded-3xl">
                <div class="text-6xl mb-4">🔍</div>
                <h3 class="text-lg font-semibold text-on-surface mb-2">챗봇을 찾을 수 없습니다</h3>
                <p class="text-on-surface-variant">검색어를 변경하거나 새 챗봇을 만들어보세요.</p>
            </div>
        `;
        return;
    }
    
    grid.innerHTML = filtered.map(chatbot => createCardHTML(chatbot)).join('');
}

function createCardHTML(chatbot) {
    const badgeClass = chatbot.type === 'parent' 
        ? 'bg-gradient-to-r from-tertiary-container/10 to-tertiary/10 text-tertiary-container' 
        : chatbot.type === 'child' 
            ? 'bg-gradient-to-r from-green-500/10 to-green-600/10 text-green-600' 
            : 'bg-slate-100 text-slate-600';
    const badgeText = chatbot.type === 'parent' ? '상위 Agent' : 
                      chatbot.type === 'child' ? '하위 Agent' : '단독';
    
    const icon = chatbot.type === 'parent' ? '🤖' : 
                 chatbot.type === 'child' ? '👤' : '💬';
    
    let hierarchyInfo = '';
    if (chatbot.type === 'child' && chatbot.parent) {
        const parent = chatbots.find(c => c.id === chatbot.parent);
        if (parent) {
            hierarchyInfo = `<div class="text-xs text-on-surface-variant mb-3 flex items-center gap-1"><span class="material-symbols-outlined text-sm">link</span> ${parent.name}</div>`;
        }
    } else if (chatbot.type === 'parent' && chatbot.sub_chatbots?.length > 0) {
        hierarchyInfo = `<div class="text-xs text-on-surface-variant mb-3 flex items-center gap-1"><span class="material-symbols-outlined text-sm">group</span> 하위 ${chatbot.sub_chatbots.length}개</div>`;
    }
    
    const dbTags = chatbot.db_ids?.map(db => 
        `<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-primary/5 text-primary">${db}</span>`
    ).join('') || '';
    
    return `
        <div class="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant hover:shadow-lg hover:-translate-y-1 transition-all duration-300 cursor-pointer group" data-id="${chatbot.id}">
            <div class="flex items-start justify-between mb-4">
                <div class="w-14 h-14 rounded-xl bg-gradient-to-br from-primary to-primary-container flex items-center justify-center text-3xl text-white shadow-md">
                    ${icon}
                </div>
                <span class="px-3 py-1 rounded-full text-xs font-semibold ${badgeClass}">${badgeText}</span>
            </div>
            <h3 class="text-lg font-semibold text-on-surface font-headline mb-2">${chatbot.name}</h3>
            <p class="text-sm text-on-surface-variant mb-3 line-clamp-2">${chatbot.description || '설명 없음'}</p>
            ${hierarchyInfo}
            <div class="flex flex-wrap gap-2 mb-4">${dbTags}</div>
            <div class="flex gap-2 pt-4 border-t border-outline-variant">
                <button onclick="openDetailModal('${chatbot.id}')" class="flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl bg-surface-container-low hover:bg-surface-container text-sm font-medium text-on-surface-variant hover:text-on-surface transition-colors" title="상세 보기">
                    <span class="material-symbols-outlined text-base">visibility</span> 보기
                </button>
                <button onclick="startChat('${chatbot.id}')" class="w-10 h-10 flex items-center justify-center rounded-xl bg-primary/10 text-primary hover:bg-primary hover:text-white transition-colors" title="채팅하기">
                    <span class="material-symbols-outlined text-lg">chat</span>
                </button>
                ${isAdmin ? `
                <button onclick="openDeleteModal('${chatbot.id}', '${chatbot.name}')" class="w-10 h-10 flex items-center justify-center rounded-xl bg-error/10 text-error hover:bg-error hover:text-white transition-colors" title="삭제">
                    <span class="material-symbols-outlined text-lg">delete</span>
                </button>
                ` : ''}
            </div>
        </div>
    `;
}

// ===== 필터 =====
function filterChatbots(type) {
    currentFilter = type;
    
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active', 'bg-primary', 'text-white');
        tab.classList.add('bg-white', 'text-slate-600');
        if (tab.dataset.filter === type) {
            tab.classList.add('active', 'bg-primary', 'text-white');
            tab.classList.remove('bg-white', 'text-slate-600');
        }
    });
    
    renderChatbots();
}

// ===== 계층 뷰 (3-tier 지원) - Tailwind 스타일 =====
async function loadHierarchy() {
    const container = document.getElementById('hierarchyContainer');
    container.innerHTML = `
        <div class="flex justify-center py-20">
            <div class="animate-spin w-10 h-10 border-3 border-primary/20 border-t-primary rounded-full"></div>
        </div>
    `;
    
    try {
        const response = await fetch('/main/api/chatbots');
        const bots = await response.json();
        
        // API 응답 체크
        if (!Array.isArray(bots)) {
            console.error('API 응답이 배열이 아님:', bots);
            container.innerHTML = '<p class="text-center py-10 text-error">챗봇 데이터 로드 실패 (형식 오류)</p>';
            return;
        }
        
        // Build 3-tier hierarchy tree
        const roots = bots.filter(b => !b.parent_id || b.level === 0);
        
        const html = roots.map(root => renderHierarchyTree(root, bots, 0)).join('');
        
        const standalone = bots.filter(b => b.level === undefined || (b.level === 0 && !b.parent_id && !roots.includes(b)));
        const standaloneHtml = standalone.map(s => `
            <div class="flex items-center gap-3 px-4 py-3 rounded-xl bg-slate-50 border border-outline-variant">
                <span class="material-symbols-outlined text-slate-400">chat</span>
                <span class="flex-1 font-medium text-sm">${s.name}</span>
                <span class="text-xs text-on-surface-variant font-mono">${s.id}</span>
                <span class="px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500">단독</span>
            </div>
        `).join('');
        
        container.innerHTML = `
            <div class="flex items-center justify-between mb-6">
                <h3 class="text-lg font-bold text-on-surface font-headline">🌳 3-Tier Agent 계층 구조</h3>
                <div class="flex gap-2">
                    <button onclick="expandAllNodes()" class="px-4 py-2 rounded-xl text-sm font-medium bg-white border border-outline-variant hover:bg-surface-container-low transition-colors flex items-center gap-1.5">
                        <span class="material-symbols-outlined text-base">expand_more</span> 펼치기
                    </button>
                    <button onclick="collapseAllNodes()" class="px-4 py-2 rounded-xl text-sm font-medium bg-white border border-outline-variant hover:bg-surface-container-low transition-colors flex items-center gap-1.5">
                        <span class="material-symbols-outlined text-base">chevron_right</span> 접기
                    </button>
                </div>
            </div>
            <div class="space-y-1 mb-8">
                ${html || '<div class="text-center py-10 text-on-surface-variant">Root Agent가 없습니다</div>'}
            </div>
            
            <h3 class="text-lg font-bold text-on-surface font-headline mb-4">💬 단독 챗봇</h3>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
                ${standaloneHtml || '<div class="col-span-full text-center py-10 text-on-surface-variant">단독 챗봇 없음</div>'}
            </div>
            
            <div class="mt-8 flex flex-wrap gap-4 p-4 bg-surface-container-low rounded-xl">
                <div class="flex items-center gap-2 text-sm">
                    <div class="w-4 h-4 rounded bg-amber-400"></div>
                    <span class="text-on-surface-variant">Root (Level 0)</span>
                </div>
                <div class="flex items-center gap-2 text-sm">
                    <div class="w-4 h-4 rounded bg-tertiary-container"></div>
                    <span class="text-on-surface-variant">Parent (Level 1)</span>
                </div>
                <div class="flex items-center gap-2 text-sm">
                    <div class="w-4 h-4 rounded bg-primary"></div>
                    <span class="text-on-surface-variant">Child (Level 2+)</span>
                </div>
                <div class="flex items-center gap-2 text-sm">
                    <div class="w-4 h-4 rounded bg-green-500"></div>
                    <span class="text-on-surface-variant">Leaf (하위 없음)</span>
                </div>
            </div>
        `;
        
        initHierarchyInteractions();
    } catch (error) {
        container.innerHTML = `<div class="text-error py-10 text-center">로드 실패: ${error.message}</div>`;
    }
}

function renderHierarchyTree(node, allBots, depth = 0) {
    const children = allBots.filter(b => b.parent_id === node.id);
    const isLeaf = children.length === 0;
    
    let bgClass = 'bg-white border-l-4 border-primary';
    let icon = 'person';
    if (node.level === 0) {
        bgClass = 'bg-gradient-to-r from-amber-100 to-amber-50 border-l-4 border-amber-400';
        icon = 'account_balance';
    } else if (node.level === 1) {
        bgClass = 'bg-gradient-to-r from-tertiary-container/10 to-tertiary/5 border-l-4 border-tertiary-container';
        icon = 'smart_toy';
    }
    
    if (isLeaf) {
        icon = 'person';
        bgClass = bgClass.replace('border-l-4', 'border-l-4 border-green-500');
    }
    
    const hasChildren = children.length > 0;
    const expandIcon = hasChildren ? 'expand_more' : '';
    
    const childrenHtml = hasChildren ? `
        <div class="hierarchy-children pl-6 border-l-2 border-dashed border-outline-variant ml-3 space-y-1" data-depth="${depth + 1}">
            ${children.map(child => renderHierarchyTree(child, allBots, depth + 1)).join('')}
        </div>
    ` : '';
    
    return `
        <div class="hierarchy-branch" data-level="${node.level || 0}" data-id="${node.id}">
            <div class="flex items-center gap-3 px-4 py-3 rounded-xl ${bgClass} cursor-pointer hover:shadow-sm transition-shadow" onclick="toggleNode('${node.id}')">
                ${hasChildren ? `<span class="material-symbols-outlined text-on-surface-variant transform transition-transform" id="expand-${node.id}">expand_more</span>` : '<span class="w-6"></span>'}
                <span class="material-symbols-outlined ${node.level === 0 ? 'text-amber-600' : node.level === 1 ? 'text-tertiary-container' : 'text-green-600'}">${icon}</span>
                <span class="flex-1 font-semibold text-sm text-on-surface">${node.name}</span>
                <span class="text-xs text-on-surface-variant font-mono">${node.id}</span>
                <span class="px-2 py-0.5 rounded-full text-xs font-medium bg-white/80">Lv.${node.level !== undefined ? node.level : '?'}</span>
                ${isLeaf ? '<span class="px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-600">Leaf</span>' : `<span class="px-2 py-0.5 rounded-full text-xs bg-primary/10 text-primary">하위 ${children.length}개</span>`}
            </div>
            ${childrenHtml}
        </div>
    `;
}

function initHierarchyInteractions() {
    document.querySelectorAll('.hierarchy-children').forEach(el => {
        el.style.display = 'block';
    });
}

function toggleNode(nodeId) {
    const branch = document.querySelector(`.hierarchy-branch[data-id="${nodeId}"]`);
    if (!branch) return;
    
    const children = branch.querySelector(':scope > .hierarchy-children');
    const expandIcon = document.getElementById(`expand-${nodeId}`);
    
    if (children) {
        const isVisible = children.style.display !== 'none';
        children.style.display = isVisible ? 'none' : 'block';
        if (expandIcon) {
            expandIcon.style.transform = isVisible ? 'rotate(-90deg)' : 'rotate(0deg)';
        }
    }
}

function expandAllNodes() {
    document.querySelectorAll('.hierarchy-children').forEach(el => {
        el.style.display = 'block';
    });
    document.querySelectorAll('[id^="expand-"]').forEach(el => {
        el.style.transform = 'rotate(0deg)';
    });
}

function collapseAllNodes() {
    document.querySelectorAll('.hierarchy-children').forEach(el => {
        if (parseInt(el.dataset.depth) > 0) {
            el.style.display = 'none';
        }
    });
    document.querySelectorAll('[id^="expand-"]').forEach(el => {
        el.style.transform = 'rotate(-90deg)';
    });
}

// ===== 사용자 권한 뷰 =====
let currentUserPermissions = [];
let currentDBPermissions = [];
let currentUserTab = 'restricted';

// 사용자 권한 탭 전환
function switchUserTab(tab) {
    currentUserTab = tab;
    
    document.querySelectorAll('.user-tab').forEach(t => {
        t.classList.remove('active', 'bg-primary', 'text-white');
        t.classList.add('bg-white', 'text-slate-600');
        if (t.dataset.userTab === tab) {
            t.classList.add('active', 'bg-primary', 'text-white');
            t.classList.remove('bg-white', 'text-slate-600');
        }
    });
    
    document.querySelectorAll('.user-tab-content').forEach(content => {
        content.classList.add('hidden');
    });
    
    // 버튼 텍스트 및 이벤트 변경
    const addBtn = document.getElementById('addPermissionBtn');
    const addBtnText = document.getElementById('addPermissionBtnText');
    
    if (tab === 'restricted') {
        document.getElementById('restrictedChatbotsContainer').classList.remove('hidden');
        loadRestrictedChatbots();
        loadRestrictedChatbotOptions(); // 드롭다운 옵션도 로드
        if (addBtn) addBtn.style.display = 'none'; // 기존 버튼 숨김
        if (addBtnText) addBtnText.textContent = '';
    } else if (tab === 'chatbot') {
        document.getElementById('chatbotPermissionsContainer').classList.remove('hidden');
        loadUsers();
        if (addBtn) addBtn.onclick = openAddPermissionModal;
        if (addBtnText) addBtnText.textContent = '권한 추가';
    } else {
        document.getElementById('dbPermissionsContainer').classList.remove('hidden');
        loadDBPermissions();
        if (addBtn) addBtn.onclick = openAddDBPermissionModal;
        if (addBtnText) addBtnText.textContent = 'DB 권한 추가';
    }
}

// Restricted Chatbots 로드
async function loadRestrictedChatbots() {
    const container = document.getElementById('restrictedChatbotsList');
    if (!container) return;
    
    container.innerHTML = `
        <div class="flex justify-center py-20">
            <div class="animate-spin w-10 h-10 border-3 border-primary/20 border-t-primary rounded-full"></div>
        </div>
    `;
    
    try {
        const response = await fetch('/main/api/restricted-chatbots');
        const data = await response.json();
        const chatbots = data.chatbots || [];
        
        if (chatbots.length === 0) {
            container.innerHTML = `
                <div class="text-center py-10 border-2 border-dashed border-outline-variant rounded-3xl">
                    <div class="text-5xl mb-4">🔓</div>
                    <h3 class="text-lg font-semibold text-on-surface mb-2">제한된 챗봇 없음</h3>
                    <p class="text-on-surface-variant mb-4">모든 챗봇이 공개되어 있습니다.</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = `
            <div class="space-y-2">
                ${chatbots.map(id => `
                    <div class="flex items-center justify-between p-4 bg-surface-container-low rounded-xl border border-outline-variant">
                        <div class="flex items-center gap-3">
                            <span class="material-symbols-outlined text-error">lock</span>
                            <span class="font-medium text-on-surface">${id}</span>
                        </div>
                        <button onclick="removeRestrictedChatbot('${id}')" 
                            class="px-4 py-2 rounded-lg text-sm font-medium text-error hover:bg-error/10 transition-colors">
                            제거
                        </button>
                    </div>
                `).join('')}
            </div>
        `;
    } catch (error) {
        console.error('Restricted chatbots 로드 실패:', error);
        container.innerHTML = `<div class="text-error py-10 text-center">로드 실패: ${error.message}</div>`;
    }
}

// Restricted Chatbot 제거
async function removeRestrictedChatbot(chatbotId) {
    if (!confirm(`정말로 ${chatbotId}를 Restricted 목록에서 제거하시겠습니까?`)) return;
    
    try {
        const response = await fetch(`/main/api/restricted-chatbots/${encodeURIComponent(chatbotId)}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('제거 실패');
        
        showToast(`${chatbotId}가 Restricted 목록에서 제거되었습니다`, 'success');
        loadRestrictedChatbots();
    } catch (error) {
        showToast('제거 실패: ' + error.message, 'error');
    }
}

// Restricted Chatbot 드롭다운 옵션 로드
async function loadRestrictedChatbotOptions() {
    const select = document.getElementById('restrictedChatbotSelect');
    if (!select) return;
    
    // 기존 옵션 유지 ("챗봇 선택...")
    select.innerHTML = '<option value="">챗봇 선택...</option>';
    
    try {
        // 전체 챗봇 목록 로드
        const response = await fetch('/api/chatbots');
        const chatbots = await response.json();
        
        // 현재 restricted 목록 확인
        const restrictedResp = await fetch('/main/api/restricted-chatbots');
        const restrictedData = await restrictedResp.json();
        const restrictedIds = new Set(restrictedData.chatbots || []);
        
        // Restricted가 아닌 챗봇만 표시
        chatbots.forEach(cb => {
            if (!restrictedIds.has(cb.id)) {
                const option = document.createElement('option');
                option.value = cb.id;
                option.textContent = `${cb.name} (${cb.id})`;
                select.appendChild(option);
            }
        });
    } catch (error) {
        console.error('챗봇 옵션 로드 실패:', error);
    }
}

// Restricted Chatbot 추가 (드롭다운에서)
async function addRestrictedChatbotFromSelect() {
    const select = document.getElementById('restrictedChatbotSelect');
    const chatbotId = select?.value;
    
    if (!chatbotId) {
        showToast('챗봇을 선택해주세요', 'error');
        return;
    }
    
    try {
        const response = await fetch('/main/api/restricted-chatbots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chatbot_id: chatbotId })
        });
        
        if (!response.ok) throw new Error('추가 실패');
        
        showToast(`${chatbotId}가 Restricted 목록에 추가되었습니다`, 'success');
        select.value = ''; // 드롭다운 초기화
        loadRestrictedChatbots(); // 목록 새로고침
        loadRestrictedChatbotOptions(); // 옵션 새로고침
    } catch (error) {
        showToast('추가 실패: ' + error.message, 'error');
    }
}

// 전역으로 노출 (HTML onclick에서 접근 가능하도록)
window.addRestrictedChatbotFromSelect = addRestrictedChatbotFromSelect;

// Restricted Chatbot 추가 모달 열기 (deprecated, but kept for compatibility)
function openAddRestrictedModal() {
    addRestrictedChatbotFromInput();
}

// Restricted Chatbot 추가
async function addRestrictedChatbot(chatbotId) {
    try {
        const response = await fetch('/main/api/restricted-chatbots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chatbot_id: chatbotId })
        });
        
        if (!response.ok) throw new Error('추가 실패');
        
        showToast(`${chatbotId}가 Restricted 목록에 추가되었습니다`, 'success');
        loadRestrictedChatbots();
    } catch (error) {
        showToast('추가 실패: ' + error.message, 'error');
    }
}

async function loadUsers() {
    const container = document.getElementById('permissionsContainer');
    if (!container) return;
    
    container.innerHTML = `
        <div class="flex justify-center py-20">
            <div class="animate-spin w-10 h-10 border-3 border-primary/20 border-t-primary rounded-full"></div>
        </div>
    `;
    
    try {
        const response = await fetch('/api/permissions/admin/stats');
        const stats = await response.json();
        
        window.userPermissionsData = stats.user_stats;
        renderUsersList(stats.user_stats);
    } catch (error) {
        container.innerHTML = `<div class="text-error py-10 text-center">로드 실패: ${error.message}</div>`;
    }
}

// ===== DB 권한 관리 =====
async function loadDBPermissions() {
    const container = document.getElementById('dbPermissionsList');
    if (!container) return;
    
    container.innerHTML = `
        <div class="flex justify-center py-20">
            <div class="animate-spin w-10 h-10 border-3 border-primary/20 border-t-primary rounded-full"></div>
        </div>
    `;
    
    try {
        const response = await fetch('/main/api/db-permissions/admin/stats');
        if (!response.ok) throw new Error('DB 권한 API 응답 오류');
        
        const stats = await response.json();
        renderDBUsersList(stats.user_stats || {});
    } catch (error) {
        console.error('Error loading DB permissions:', error);
        container.innerHTML = `
            <div class="text-center py-20 border-2 border-dashed border-outline-variant rounded-3xl">
                <div class="text-5xl mb-4">🗄️</div>
                <h3 class="text-lg font-semibold text-on-surface mb-2">DB 권한 정보 로드 실패</h3>
                <p class="text-on-surface-variant mb-4">${error.message}</p>
                <button onclick="loadDBPermissions()" class="px-4 py-2 rounded-xl bg-primary text-white text-sm font-medium hover:opacity-90">
                    다시 시도
                </button>
            </div>
        `;
    }
}

function renderDBUsersList(userStats) {
    const container = document.getElementById('dbPermissionsList');
    
    if (!userStats || Object.keys(userStats).length === 0) {
        container.innerHTML = `
            <div class="text-center py-20 border-2 border-dashed border-outline-variant rounded-3xl">
                <div class="text-6xl mb-4">🗄️</div>
                <h3 class="text-lg font-semibold text-on-surface mb-2">DB 권한 정보 없음</h3>
                <p class="text-on-surface-variant mb-4">DB 권한을 추가하여 사용자를 관리하세요.</p>
                <button onclick="openAddDBPermissionModal()" class="px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-gradient-to-r from-primary to-primary-container hover:opacity-90 transition-opacity flex items-center gap-2">
                    <span class="material-symbols-outlined text-base">add</span> DB 권한 추가
                </button>
            </div>
        `;
        return;
    }
    
    const userListHtml = Object.entries(userStats).map(([knoxId, data]) => `
        <div class="db-permission-card bg-white rounded-2xl p-5 shadow-sm border border-outline-variant flex items-center justify-between hover:shadow-md transition-shadow" data-knox-id="${knoxId}">
            <div class="flex items-center gap-4">
                <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500/10 to-amber-600/10 flex items-center justify-center">
                    <span class="material-symbols-outlined text-amber-600">database</span>
                </div>
                <div>
                    <h4 class="font-semibold text-on-surface mb-1">${knoxId}</h4>
                    <div class="flex gap-2">
                        <span class="px-2.5 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-600">접근 가능 ${data.accessible || 0}개</span>
                        <span class="px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600">전체 ${data.total || 0}개</span>
                    </div>
                </div>
            </div>
            <button onclick="viewUserDBPermissions('${knoxId}')" class="px-4 py-2 rounded-xl text-sm font-medium bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface transition-colors flex items-center gap-1.5">
                <span class="material-symbols-outlined text-base">visibility</span> 상세 보기
            </button>
        </div>
    `).join('');
    
    container.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${userListHtml}
        </div>
    `;
}

async function viewUserDBPermissions(knoxId) {
    try {
        const response = await fetch(`/main/main/api/db-permissions/users/${knoxId}`);
        if (!response.ok) throw new Error('DB 권한 조회 실패');
        
        const data = await response.json();
        currentDBPermissions = data.permissions || [];
        
        const permsHtml = data.permissions?.map(p => `
            <div class="flex items-center justify-between p-4 rounded-xl ${p.can_access ? 'bg-amber-50 border-l-4 border-amber-500' : 'bg-red-50 border-l-4 border-red-500 opacity-70'}">
                <div class="flex items-center gap-3">
                    <span class="material-symbols-outlined text-amber-600">database</span>
                    <div>
                        <span class="font-medium text-on-surface text-sm">${p.db_id}</span>
                        <p class="text-xs text-on-surface-variant mt-1">${p.created_at ? new Date(p.created_at).toLocaleDateString() : '-'}</p>
                    </div>
                </div>
                <div class="flex items-center gap-3">
                    <label class="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" ${p.can_access ? 'checked' : ''} onchange="updateUserDBPermission('${knoxId}', '${p.db_id}', this.checked)" class="sr-only peer">
                        <div class="w-11 h-6 bg-slate-200 peer-focus:ring-2 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                    <button onclick="deleteUserDBPermission('${knoxId}', '${p.db_id}')" class="w-8 h-8 flex items-center justify-center rounded-lg bg-red-100 text-error hover:bg-error hover:text-white transition-colors">
                        <span class="material-symbols-outlined text-base">delete</span>
                    </button>
                </div>
            </div>
        `).join('') || '<p class="text-center py-10 text-on-surface-variant">설정된 DB 권한이 없습니다.</p>';
        
        const content = `
            <div class="flex items-center gap-4 p-4 bg-surface-container-low rounded-2xl mb-6">
                <div class="w-14 h-14 rounded-full bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center text-white text-xl font-bold">
                    <span class="material-symbols-outlined">database</span>
                </div>
                <div>
                    <h4 class="font-semibold text-on-surface">${knoxId}</h4>
                    <p class="text-sm text-on-surface-variant">DB 접근 가능: <strong class="text-amber-600">${data.accessible_count || 0}</strong> / ${data.total || 0}개</p>
                </div>
            </div>
            <div class="space-y-3 max-h-80 overflow-y-auto custom-scrollbar">
                ${permsHtml}
            </div>
            <div class="mt-6 pt-4 border-t border-outline-variant">
                <button onclick="openAddDBPermissionModalForUser('${knoxId}')" class="w-full py-3 rounded-xl text-sm font-semibold bg-amber-100 text-amber-700 hover:bg-amber-200 transition-colors flex items-center justify-center gap-2">
                    <span class="material-symbols-outlined">add</span> DB 권한 추가
                </button>
            </div>
        `;
        
        document.getElementById('userDetailTitle').textContent = `${knoxId} - DB 권한 상세`;
        document.getElementById('userDetailContent').innerHTML = content;
        document.getElementById('userDetailModal').classList.remove('hidden');
        document.getElementById('userDetailModal').classList.add('flex');
        
    } catch (error) {
        console.error('Error loading user DB permissions:', error);
        showToast('DB 권한 조회 실패: ' + error.message, 'error');
    }
}

async function updateUserDBPermission(knoxId, dbId, canAccess) {
    try {
        const response = await fetch(`/main/api/db-permissions/${knoxId}/${dbId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ can_access: canAccess })
        });
        
        if (!response.ok) throw new Error('DB 권한 수정 실패');
        
        showToast('DB 권한이 수정되었습니다', 'success');
        viewUserDBPermissions(knoxId);
        loadDBPermissions();
    } catch (error) {
        showToast('DB 권한 수정 실패: ' + error.message, 'error');
    }
}

async function deleteUserDBPermission(knoxId, dbId) {
    if (!confirm(`정말로 ${dbId}에 대한 DB 권한을 삭제하시겠습니까?`)) return;
    
    try {
        const response = await fetch(`/main/api/db-permissions/${knoxId}/${dbId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('DB 권한 삭제 실패');
        
        showToast('DB 권한이 삭제되었습니다', 'success');
        viewUserDBPermissions(knoxId);
        loadDBPermissions();
    } catch (error) {
        showToast('DB 권한 삭제 실패: ' + error.message, 'error');
    }
}

function renderUsersList(userStats) {
    const container = document.getElementById('permissionsContainer');
    
    if (!userStats || Object.keys(userStats).length === 0) {
        container.innerHTML = `
            <div class="text-center py-20 border-2 border-dashed border-outline-variant rounded-3xl">
                <div class="text-6xl mb-4">👥</div>
                <h3 class="text-lg font-semibold text-on-surface mb-2">사용자 권한 정보 없음</h3>
                <p class="text-on-surface-variant">권한을 추가하여 사용자를 관리하세요.</p>
            </div>
        `;
        return;
    }
    
    const userListHtml = Object.entries(userStats).map(([knoxId, data]) => `
        <div class="user-permission-card bg-white rounded-2xl p-5 shadow-sm border border-outline-variant flex items-center justify-between hover:shadow-md transition-shadow" data-knox-id="${knoxId}">
            <div>
                <h4 class="font-semibold text-on-surface mb-1">${knoxId}</h4>
                <div class="flex gap-2">
                    <span class="px-2.5 py-1 rounded-full text-xs font-medium bg-green-100 text-green-600">접근 가능 ${data.accessible}개</span>
                    <span class="px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-600">전체 ${data.total}개</span>
                </div>
            </div>
            <button onclick="viewUserPermissions('${knoxId}')" class="px-4 py-2 rounded-xl text-sm font-medium bg-surface-container-low hover:bg-surface-container text-on-surface-variant hover:text-on-surface transition-colors">
                상세 보기
            </button>
        </div>
    `).join('');
    
    container.innerHTML = `
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${userListHtml}
        </div>
    `;
}

function filterUsers() {
    const searchTerm = document.getElementById('userSearchInput')?.value.toLowerCase() || '';
    const userCards = document.querySelectorAll('.user-permission-card');
    
    userCards.forEach(card => {
        const knoxId = card.getAttribute('data-knox-id') || '';
        card.style.display = knoxId.toLowerCase().includes(searchTerm) ? 'flex' : 'none';
    });
}

async function viewUserPermissions(knoxId) {
    try {
        const response = await fetch(`/api/permissions/users/${knoxId}`);
        if (!response.ok) throw new Error('조회 실패');
        
        const data = await response.json();
        currentUserPermissions = data.permissions;
        
        const permsHtml = data.permissions.map(p => `
            <div class="flex items-center justify-between p-4 rounded-xl ${p.can_access ? 'bg-green-50 border-l-4 border-green-500' : 'bg-red-50 border-l-4 border-red-500 opacity-70'}">
                <div>
                    <span class="font-medium text-on-surface text-sm">${p.chatbot_id}</span>
                    <p class="text-xs text-on-surface-variant mt-1">${p.created_at ? new Date(p.created_at).toLocaleDateString() : '-'}</p>
                </div>
                <div class="flex items-center gap-3">
                    <label class="relative inline-flex items-center cursor-pointer">
                        <input type="checkbox" ${p.can_access ? 'checked' : ''} onchange="updateUserPermission('${knoxId}', '${p.chatbot_id}', this.checked)" class="sr-only peer">
                        <div class="w-11 h-6 bg-slate-200 peer-focus:ring-2 peer-focus:ring-primary/20 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-primary"></div>
                    </label>
                    <button onclick="deleteUserPermission('${knoxId}', '${p.chatbot_id}')" class="w-8 h-8 flex items-center justify-center rounded-lg bg-red-100 text-error hover:bg-error hover:text-white transition-colors">
                        <span class="material-symbols-outlined text-base">delete</span>
                    </button>
                </div>
            </div>
        `).join('');
        
        const content = `
            <div class="flex items-center gap-4 p-4 bg-surface-container-low rounded-2xl mb-6">
                <div class="w-14 h-14 rounded-full bg-gradient-to-br from-primary to-primary-container flex items-center justify-center text-white text-xl font-bold">
                    ${knoxId.charAt(0).toUpperCase()}
                </div>
                <div>
                    <h4 class="font-semibold text-on-surface">${knoxId}</h4>
                    <p class="text-sm text-on-surface-variant">접근 가능: <strong class="text-primary">${data.accessible_count}</strong> / ${data.total}개 챗봇</p>
                </div>
            </div>
            <div class="space-y-3 max-h-80 overflow-y-auto custom-scrollbar">
                ${permsHtml || '<p class="text-center py-10 text-on-surface-variant">설정된 권한이 없습니다.</p>'}
            </div>
        `;
        
        document.getElementById('userDetailTitle').textContent = `${knoxId} - 권한 상세`;
        document.getElementById('userDetailContent').innerHTML = content;
        document.getElementById('userDetailModal').classList.remove('hidden');
        document.getElementById('userDetailModal').classList.add('flex');
        
    } catch (error) {
        console.error('Error loading user permissions:', error);
        showToast('권한 조회 실패: ' + error.message, 'error');
    }
}

async function updateUserPermission(knoxId, chatbotId, canAccess) {
    try {
        const response = await fetch(`/api/permissions/${knoxId}/${chatbotId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ can_access: canAccess })
        });
        
        if (!response.ok) throw new Error('수정 실패');
        
        showToast('권한이 수정되었습니다', 'success');
        viewUserPermissions(knoxId);
        loadUsers();
    } catch (error) {
        showToast('권한 수정 실패: ' + error.message, 'error');
    }
}

async function deleteUserPermission(knoxId, chatbotId) {
    if (!confirm(`정말로 ${chatbotId}에 대한 권한을 삭제하시겠습니까?`)) return;
    
    try {
        const response = await fetch(`/api/permissions/${knoxId}/${chatbotId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('삭제 실패');
        
        showToast('권한이 삭제되었습니다', 'success');
        viewUserPermissions(knoxId);
        loadUsers();
    } catch (error) {
        showToast('권한 삭제 실패: ' + error.message, 'error');
    }
}

function closeUserDetailModal() {
    document.getElementById('userDetailModal').classList.add('hidden');
    document.getElementById('userDetailModal').classList.remove('flex');
}

// ===== 통계 대시보드 =====
async function loadStatsDashboard() {
    const container = document.getElementById('statsDashboard');
    container.innerHTML = `
        <div class="flex justify-center py-20">
            <div class="animate-spin w-10 h-10 border-3 border-primary/20 border-t-primary rounded-full"></div>
        </div>
    `;
    
    try {
        const chatbotRes = await fetch('/main/api/stats');
        const chatbotStats = await chatbotRes.json();
        
        const permRes = await fetch('/api/permissions/admin/stats');
        const permStats = await permRes.json();
        
        const totalUsers = Object.keys(permStats.user_stats || {}).length;
        
        container.innerHTML = `
            <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <div class="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant text-center">
                    <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-primary/10 to-primary-container/10 flex items-center justify-center mx-auto mb-3">
                        <span class="material-symbols-outlined text-2xl text-primary">smart_toy</span>
                    </div>
                    <div class="text-3xl font-bold text-on-surface font-headline">${chatbotStats.total}</div>
                    <div class="text-sm text-on-surface-variant mt-1">전체 챗봇</div>
                </div>
                <div class="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant text-center">
                    <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-tertiary-container/10 to-tertiary/10 flex items-center justify-center mx-auto mb-3">
                        <span class="material-symbols-outlined text-2xl text-tertiary-container">account_tree</span>
                    </div>
                    <div class="text-3xl font-bold text-on-surface font-headline">${chatbotStats.parents}</div>
                    <div class="text-sm text-on-surface-variant mt-1">상위 Agent</div>
                </div>
                <div class="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant text-center">
                    <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-green-500/10 to-green-600/10 flex items-center justify-center mx-auto mb-3">
                        <span class="material-symbols-outlined text-2xl text-green-600">person</span>
                    </div>
                    <div class="text-3xl font-bold text-on-surface font-headline">${totalUsers}</div>
                    <div class="text-sm text-on-surface-variant mt-1">사용자</div>
                </div>
                <div class="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant text-center">
                    <div class="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-500/10 to-amber-600/10 flex items-center justify-center mx-auto mb-3">
                        <span class="material-symbols-outlined text-2xl text-amber-600">key</span>
                    </div>
                    <div class="text-3xl font-bold text-on-surface font-headline">${permStats.total_permissions || 0}</div>
                    <div class="text-sm text-on-surface-variant mt-1">권한 설정</div>
                </div>
            </div>
            
            <div class="bg-white rounded-2xl p-6 shadow-sm border border-outline-variant">
                <h3 class="text-lg font-bold text-on-surface font-headline mb-6">사용자별 챗봇 접근</h3>
                <div class="space-y-4">
                    ${(() => {
                        const userEntries = Object.entries(permStats.user_stats || {});
                        const maxTotal = Math.max(...userEntries.map(([_, d]) => d.total || 0), 1);
                        return userEntries.map(([user, data]) => {
                            const fillPercentage = data.total > 0 ? (data.accessible / data.total * 100) : 0;
                            const relativeWidth = (data.accessible / maxTotal * 100);
                            return `
                                <div class="flex items-center gap-4">
                                    <span class="w-32 text-sm font-medium text-on-surface truncate">${user}</span>
                                    <div class="flex-1">
                                        <div class="h-8 bg-surface-container-low rounded-full overflow-hidden">
                                            <div class="h-full bg-gradient-to-r from-primary to-primary-container rounded-full flex items-center justify-end pr-3 text-white text-xs font-medium transition-all duration-500" style="width: ${relativeWidth}%">
                                                ${relativeWidth > 15 ? `${data.accessible}/${data.total}` : ''}
                                            </div>
                                        </div>
                                    </div>
                                    <span class="w-16 text-right text-sm text-on-surface-variant">${data.accessible}/${data.total}</span>
                                </div>
                            `;
                        }).join('') || '<p class="text-center py-10 text-on-surface-variant">사용자 데이터가 없습니다.</p>';
                    })()}
                </div>
            </div>
        `;
    } catch (error) {
        container.innerHTML = `<div class="text-error py-10 text-center">로드 실패: ${error.message}</div>`;
    }
}

// ===== 모달 관리 =====
function openCreateModal() {
    const modal = document.getElementById('chatbotModal');
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.getElementById('modalTitle').textContent = '새 챗봇 만들기';
    document.getElementById('chatbotForm').reset();
    document.getElementById('chatbotId').disabled = false;
    document.getElementById('dbTags').innerHTML = '';
}

function closeModal() {
    const modal = document.getElementById('chatbotModal');
    modal.classList.add('hidden');
    modal.classList.remove('flex');
}

function openDetailModal(chatbotId) {
    detailChatbotId = chatbotId;
    const chatbot = chatbots.find(c => c.id === chatbotId);
    if (!chatbot) return;
    
    const badgeClass = chatbot.type === 'parent' 
        ? 'bg-tertiary-container/10 text-tertiary-container' 
        : chatbot.type === 'child' 
            ? 'bg-green-100 text-green-600' 
            : 'bg-slate-100 text-slate-600';
    const badgeText = chatbot.type === 'parent' ? '상위 Agent' : 
                      chatbot.type === 'child' ? '하위 Agent' : '단독';
    
    const content = `
        <div class="space-y-4">
            <div class="flex items-center gap-3 mb-6">
                <span class="px-3 py-1 rounded-full text-xs font-semibold ${badgeClass}">${badgeText}</span>
            </div>
            <div class="flex py-4 border-b border-outline-variant">
                <label class="w-28 text-sm font-medium text-on-surface-variant">ID</label>
                <code class="flex-1 text-sm font-mono bg-surface-container-low px-3 py-1.5 rounded-lg">${chatbot.id}</code>
            </div>
            <div class="flex py-4 border-b border-outline-variant">
                <label class="w-28 text-sm font-medium text-on-surface-variant">이름</label>
                <span class="flex-1 text-sm text-on-surface">${chatbot.name}</span>
            </div>
            <div class="flex py-4 border-b border-outline-variant">
                <label class="w-28 text-sm font-medium text-on-surface-variant">설명</label>
                <span class="flex-1 text-sm text-on-surface">${chatbot.description || '없음'}</span>
            </div>
            ${chatbot.parent ? `
            <div class="flex py-4 border-b border-outline-variant">
                <label class="w-28 text-sm font-medium text-on-surface-variant">상위 Agent</label>
                <span class="flex-1 text-sm text-on-surface">${chatbot.parent}</span>
            </div>` : ''}
            ${chatbot.sub_chatbots?.length ? `
            <div class="flex py-4 border-b border-outline-variant">
                <label class="w-28 text-sm font-medium text-on-surface-variant">하위 Agent</label>
                <span class="flex-1 text-sm text-on-surface">${chatbot.sub_chatbots.map(sub => typeof sub === 'object' ? sub.id : sub).join(', ')}</span>
            </div>` : ''}
            <div class="flex py-4 border-b border-outline-variant items-start">
                <label class="w-28 text-sm font-medium text-on-surface-variant pt-1">검색 키워드</label>
                <div class="flex-1">
                    ${chatbot.keywords?.length ? chatbot.keywords.map(kw => `<span class="inline-block px-2.5 py-1 rounded-full text-xs font-medium bg-tertiary-container/10 text-tertiary-container mr-1 mb-1">${kw}</span>`).join('') : '<span class="text-sm text-slate-400">없음</span>'}
                </div>
            </div>
            <div class="flex py-4 items-start">
                <label class="w-28 text-sm font-medium text-on-surface-variant pt-1">연결된 DB</label>
                <div class="flex-1">
                    <div class="flex flex-wrap gap-2 mb-3" id="detailDbList">${chatbot.db_ids?.map(db => `<span class="px-2.5 py-1 rounded-full text-xs font-medium bg-primary/5 text-primary">${db}</span>`).join(' ') || '<span class="text-sm text-slate-400">없음</span>'}</div>
                    ${isAdmin ? `
                    <button onclick="loadDBSelector('${chatbot.id}')" class="px-4 py-2 rounded-xl text-sm font-medium bg-surface-container-low hover:bg-surface-container text-primary transition-colors flex items-center gap-2">
                        <span class="material-symbols-outlined text-sm">edit</span> DB 관리
                    </button>
                    <div id="dbSelectorContainer" class="mt-4 hidden">
                        <div class="bg-surface-container-low rounded-xl p-4">
                            <p class="text-sm font-medium text-on-surface mb-3">연결할 DB 선택</p>
                            <div id="dbCheckboxList" class="space-y-2 max-h-40 overflow-y-auto custom-scrollbar">
                                <!-- DB 체크박스 목록 -->
                            </div>
                            <div class="flex gap-2 mt-4">
                                <button onclick="saveChatbotDBs('${chatbot.id}')" class="flex-1 py-2 rounded-lg text-sm font-medium bg-primary text-white hover:opacity-90 transition-opacity">저장</button>
                                <button onclick="closeDBSelector()" class="px-4 py-2 rounded-lg text-sm font-medium text-slate-600 hover:bg-slate-100 transition-colors">취소</button>
                            </div>
                        </div>
                    </div>` : ''}
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('detailTitle').textContent = chatbot.name;
    document.getElementById('detailContent').innerHTML = content;
    document.getElementById('detailModal').classList.remove('hidden');
    document.getElementById('detailModal').classList.add('flex');
}

function closeDetailModal() {
    document.getElementById('detailModal').classList.add('hidden');
    document.getElementById('detailModal').classList.remove('flex');
    detailChatbotId = null;
}

// DB 관리 함수들
async function loadDBSelector(chatbotId) {
    try {
        const chatbot = chatbots.find(c => c.id === chatbotId);
        const currentDBs = new Set(chatbot?.db_ids || []);
        
        // DB 목록 가져오기
        const response = await fetch('/main/api/databases');
        const dbList = await response.json();
        
        const container = document.getElementById('dbCheckboxList');
        const selectorContainer = document.getElementById('dbSelectorContainer');
        
        if (dbList.length === 0) {
            container.innerHTML = '<p class="text-sm text-slate-400">사용 가능한 DB가 없습니다</p>';
        } else {
            container.innerHTML = dbList.map(db => `
                <label class="flex items-center gap-3 cursor-pointer p-2 rounded-lg hover:bg-white/50 transition-colors">
                    <input type="checkbox" value="${db}" ${currentDBs.has(db) ? 'checked' : ''} 
                           class="w-4 h-4 text-primary rounded border-slate-300 focus:ring-primary">
                    <span class="text-sm font-medium text-on-surface">${db}</span>
                </label>
            `).join('');
        }
        
        selectorContainer.classList.remove('hidden');
    } catch (error) {
        console.error('DB 목록 로드 실패:', error);
        showToast('DB 목록을 불러오지 못했습니다', 'error');
    }
}

function closeDBSelector() {
    document.getElementById('dbSelectorContainer').classList.add('hidden');
}

async function saveChatbotDBs(chatbotId) {
    const checkboxes = document.querySelectorAll('#dbCheckboxList input[type="checkbox"]:checked');
    const selectedDBs = Array.from(checkboxes).map(cb => cb.value);
    
    try {
        // 챗봇 정보 가져오기
        const chatbot = chatbots.find(c => c.id === chatbotId);
        if (!chatbot) throw new Error('챗봇을 찾을 수 없습니다');
        
        // 수정된 챗봇 데이터 준비
        const updateData = {
            id: chatbotId,
            name: chatbot.name,
            description: chatbot.description,
            active: chatbot.active,
            capabilities: {
                ...chatbot.capabilities,
                db_ids: selectedDBs
            },
            system_prompt: chatbot.system_prompt,
            parent_id: chatbot.parent_id,
            policy: chatbot.policy
        };
        
        const response = await fetch(`/main/api/chatbots/${chatbotId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(updateData)
        });
        
        if (!response.ok) throw new Error('DB 연결 저장 실패');
        
        showToast('DB 연결이 저장되었습니다', 'success');
        closeDBSelector();
        
        // 상세 모달 새로고침
        openDetailModal(chatbotId);
        
        // 챗봇 목록 새로고침
        await loadChatbots();
    } catch (error) {
        console.error('DB 저장 실패:', error);
        showToast('DB 저장 실패: ' + error.message, 'error');
    }
}

function startChatFromDetail() {
    if (detailChatbotId) {
        startChat(detailChatbotId);
        closeDetailModal();
    }
}

function openDeleteModal(chatbotId, name) {
    deleteTargetId = chatbotId;
    document.getElementById('deleteChatbotName').textContent = name;
    document.getElementById('deleteModal').classList.remove('hidden');
    document.getElementById('deleteModal').classList.add('flex');
}

function closeDeleteModal() {
    document.getElementById('deleteModal').classList.add('hidden');
    document.getElementById('deleteModal').classList.remove('flex');
    deleteTargetId = null;
}

async function confirmDelete() {
    if (!deleteTargetId) return;
    
    try {
        const response = await fetch(`/main/api/chatbots/${deleteTargetId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Delete failed');
        
        closeDeleteModal();
        loadChatbots();
        loadStats();
        showToast('챗봇이 삭제되었습니다', 'success');
    } catch (error) {
        showToast('삭제 실패: ' + error.message, 'error');
    }
}

// ===== DB 권한 모달 =====
async function openAddDBPermissionModal() {
    document.getElementById('addPermissionModal').classList.remove('hidden');
    document.getElementById('addPermissionModal').classList.add('flex');
    document.getElementById('addPermissionForm').reset();
    
    const select = document.getElementById('addChatbotId');
    select.innerHTML = '<option value="">DB를 선택하세요</option>';
    
    // DB 목록 가져오기
    const dbList = ['db_new', 'db_001', 'db_002', 'db_003', 'db_004', 
                    'db_hr_policy', 'db_hr_benefit', 'db_hr_overview',
                    'db_backend', 'db_frontend', 'db_devops', 'db_tech_overview'];
    
    dbList.forEach(db => {
        const option = document.createElement('option');
        option.value = db;
        option.textContent = db;
        select.appendChild(option);
    });
    
    // 폼을 DB 권한 모드로 변경
    document.getElementById('addPermissionForm').dataset.mode = 'db';
    document.querySelector('#addPermissionModal h3').textContent = 'DB 권한 추가';
    document.querySelector('label[for="addChatbotId"]').textContent = 'DB 선택 *';
}

async function openAddDBPermissionModalForUser(knoxId) {
    await openAddDBPermissionModal();
    document.getElementById('addUserId').value = knoxId;
}

// ===== 권한 추가 모달 =====
async function openAddPermissionModal() {
    document.getElementById('addPermissionModal').classList.remove('hidden');
    document.getElementById('addPermissionModal').classList.add('flex');
    document.getElementById('addPermissionForm').reset();
    
    const select = document.getElementById('addChatbotId');
    select.innerHTML = '<option value="">챗봇을 선택하세요</option>';
    
    try {
        const response = await fetch('/main/api/chatbots');
        const bots = await response.json();
        
        bots.forEach(bot => {
            const option = document.createElement('option');
            option.value = bot.id;
            option.textContent = `${bot.name} (${bot.id})`;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Error loading chatbots:', error);
        select.innerHTML = '<option value="">챗봇 목록 로드 실패</option>';
    }
}

function closeAddPermissionModal() {
    document.getElementById('addPermissionModal').classList.add('hidden');
    document.getElementById('addPermissionModal').classList.remove('flex');
}

async function saveAddPermission(event) {
    event.preventDefault();
    
    const knoxId = document.getElementById('addUserId').value.trim();
    const chatbotId = document.getElementById('addChatbotId').value;
    const canAccessRadio = document.querySelector('input[name="addCanAccess"]:checked');
    const canAccess = canAccessRadio ? canAccessRadio.value === 'true' : true;
    
    if (!knoxId || !chatbotId) {
        showToast('사용자 ID와 챗봇을 모두 선택하세요', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/permissions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                knox_id: knoxId,
                chatbot_id: chatbotId,
                can_access: canAccess
            })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || '저장 실패');
        }
        
        closeAddPermissionModal();
        showToast('권한이 추가되었습니다', 'success');
        loadUsers();
    } catch (error) {
        showToast('권한 추가 실패: ' + error.message, 'error');
    }
}

// ===== 챗봇 저장 =====
async function saveChatbot(event) {
    event.preventDefault();
    
    const data = {
        id: document.getElementById('chatbotId').value,
        name: document.getElementById('chatbotName').value,
        description: document.getElementById('chatbotDesc').value,
        type: document.getElementById('chatbotType').value,
        system_prompt: document.getElementById('systemPrompt').value,
        db_ids: Array.from(document.querySelectorAll('#dbTags .db-tag')).map(tag => tag.textContent.replace('×', '').trim()),
        active: true
    };
    
    if (data.type === 'child') {
        data.parent = document.getElementById('parentAgent').value;
    }
    
    try {
        const response = await fetch('/main/api/chatbots', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Failed');
        }
        
        closeModal();
        loadChatbots();
        loadStats();
        showToast('챗봇이 생성되었습니다', 'success');
    } catch (error) {
        showToast('저장 실패: ' + error.message, 'error');
    }
}

// ===== 유틸리티 =====
function populateParentSelect() {
    const select = document.getElementById('parentAgent');
    select.innerHTML = '<option value="">선택하세요</option>';
    
    const parents = chatbots.filter(c => c.type === 'parent');
    parents.forEach(p => {
        const option = document.createElement('option');
        option.value = p.id;
        option.textContent = p.name;
        select.appendChild(option);
    });
}

function onTypeChange() {
    const type = document.getElementById('chatbotType').value;
    const parentGroup = document.getElementById('parentSelectGroup');
    
    if (type === 'child') {
        parentGroup.classList.remove('hidden');
    } else {
        parentGroup.classList.add('hidden');
    }
}

function startChat(chatbotId) {
    window.open(`/?chatbot=${chatbotId}`, '_blank');
}

function setupEventListeners() {
    // Search input
    document.getElementById('globalSearchInput')?.addEventListener('input', renderChatbots);
    
    // Close modals on outside click
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) {
                modal.classList.add('hidden');
                modal.classList.remove('flex');
            }
        });
    });
    
    // DB tag input
    const dbInput = document.getElementById('dbInput');
    if (dbInput) {
        dbInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ',') {
                e.preventDefault();
                const value = dbInput.value.trim().replace(',', '');
                if (value) {
                    addDbTag(value);
                    dbInput.value = '';
                }
            }
        });
    }
}

function addDbTag(dbId) {
    const container = document.getElementById('dbTags');
    const tag = document.createElement('span');
    tag.className = 'db-tag inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium bg-primary/10 text-primary';
    tag.innerHTML = `${dbId} <button onclick="this.parentElement.remove()" class="hover:text-primary-container"><span class="material-symbols-outlined text-base">close</span></button>`;
    container.appendChild(tag);
}

// ===== 토스트 알림 =====
function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = 'fixed bottom-6 right-6 px-6 py-4 rounded-2xl text-white font-semibold shadow-2xl transform transition-all duration-300 z-[2000]';
    
    if (type === 'success') {
        toast.classList.add('bg-gradient-to-r', 'from-green-500', 'to-green-600');
    } else if (type === 'error') {
        toast.classList.add('bg-gradient-to-r', 'from-error', 'to-red-600');
    } else {
        toast.classList.add('bg-gradient-to-r', 'from-primary', 'to-primary-container');
    }
    
    // Show
    requestAnimationFrame(() => {
        toast.style.transform = 'translateY(0)';
        toast.style.opacity = '1';
    });
    
    setTimeout(() => {
        toast.style.transform = 'translateY(20px)';
        toast.style.opacity = '0';
    }, 3000);
}
