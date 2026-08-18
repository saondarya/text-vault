/**
 * Text Vault - Client Application Logic
 */

const TOKEN_KEY = 'text_vault_jwt_token';
const $ = (id) => document.getElementById(id);

// Application Global State
const state = {
  user: null,
  folders: [],
  files: [],
  selectedFolderId: null,
  selectedFileId: null,
  activeFile: null,
  isRegister: false,
  dirty: false,
  saveTimer: null,
  searchTimer: null,
  expandedFolders: new Set(),
  folderFilter: '',
  fileFilter: '',
  stagedImportItems: [],
};

// --- Utilities ---

function formatBytes(bytes) {
  if (bytes === 0 || !bytes) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const icons = {
    js: '🟨', jsx: '⚛️', ts: '🔷', tsx: '⚛️',
    py: '🐍', json: '📋', md: '📝', html: '🌐',
    css: '🎨', sql: '🗄️', txt: '📄', sh: '🐚',
    env: '⚙️', yml: '⚙️', yaml: '⚙️',
  };
  return icons[ext] || '📄';
}

function showToast(message, type = 'info') {
  const container = $('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success' ? '✓' : type === 'error' ? '⚠️' : 'ℹ️';
  toast.innerHTML = `<span>${icon}</span><span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.2s ease';
    setTimeout(() => toast.remove(), 200);
  }, 3200);
}

// --- API Client ---

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  try {
    const res = await fetch(path, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.error || `HTTP Error ${res.status}`);
    }
    return data;
  } catch (err) {
    if (err.message.includes('Authentication required') || err.message.includes('Invalid or expired')) {
      clearToken();
      showLogin();
    }
    throw err;
  }
}

// --- Authentication ---

async function checkAuth() {
  if (!getToken()) return showLogin();
  try {
    const { user } = await api('/api/auth/me');
    state.user = user;
    showVault();
    await loadFolders();
  } catch {
    clearToken();
    showLogin();
  }
}

function showLogin() {
  $('login-screen').classList.remove('hidden');
  $('vault-screen').classList.add('hidden');
}

function showVault() {
  $('login-screen').classList.add('hidden');
  $('vault-screen').classList.remove('hidden');
  $('user-label').textContent = state.user.username;
  $('user-avatar').textContent = state.user.username.charAt(0).toUpperCase();
}

$('toggle-mode').onclick = () => {
  state.isRegister = !state.isRegister;
  $('toggle-label').textContent = state.isRegister ? 'Already have an account?' : "Don't have an account?";
  $('toggle-mode').textContent = state.isRegister ? 'Sign in' : 'Create one';
  $('auth-btn').textContent = state.isRegister ? 'Create Account' : 'Sign In';
  $('auth-error').classList.add('hidden');
};

$('login-form').onsubmit = async (e) => {
  e.preventDefault();
  const username = $('username').value.trim();
  const password = $('password').value;
  $('auth-error').classList.add('hidden');
  $('auth-btn').disabled = true;

  try {
    const endpoint = state.isRegister ? '/api/auth/register' : '/api/auth/login';
    const { token, user } = await api(endpoint, {
      method: 'POST',
      body: JSON.stringify({ username, password }),
    });
    setToken(token);
    state.user = user;
    showToast(state.isRegister ? 'Account created successfully!' : `Welcome back, ${user.username}!`, 'success');
    showVault();
    await loadFolders();
  } catch (err) {
    $('auth-error').textContent = err.message;
    $('auth-error').classList.remove('hidden');
  } finally {
    $('auth-btn').disabled = false;
  }
};

$('logout-btn').onclick = () => {
  clearToken();
  state.user = null;
  state.folders = [];
  state.files = [];
  state.selectedFolderId = null;
  state.selectedFileId = null;
  state.activeFile = null;
  showToast('Logged out successfully');
  showLogin();
};

// --- Modal System ---

function openModal(id) {
  const el = $(id);
  if (el) el.classList.remove('hidden');
}

function closeModal(id) {
  const el = $(id);
  if (el) el.classList.add('hidden');
}

document.querySelectorAll('[data-close]').forEach((btn) => {
  btn.onclick = () => closeModal(btn.getAttribute('data-close'));
});

// Close modal when clicking on overlay background
document.querySelectorAll('.modal-overlay').forEach((overlay) => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.classList.add('hidden');
  });
});

let dialogCallback = null;

function showDialog({ title, message, inputLabel = null, inputValue = '', confirmText = 'Confirm', onConfirm }) {
  $('dialog-title').textContent = title;
  $('dialog-message').textContent = message;
  $('dialog-confirm-btn').textContent = confirmText;

  const inputGroup = $('dialog-input-group');
  const inputEl = $('dialog-input');
  if (inputLabel) {
    $('dialog-input-label').textContent = inputLabel;
    inputEl.value = inputValue;
    inputGroup.classList.remove('hidden');
    setTimeout(() => inputEl.focus(), 50);
  } else {
    inputGroup.classList.add('hidden');
  }

  dialogCallback = onConfirm;
  openModal('dialog-modal');
}

$('dialog-confirm-btn').onclick = async () => {
  const inputEl = $('dialog-input');
  const value = inputEl.value.trim();
  closeModal('dialog-modal');
  if (dialogCallback) {
    await dialogCallback(value);
    dialogCallback = null;
  }
};

$('dialog-input').onkeydown = (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    $('dialog-confirm-btn').click();
  }
};

// --- Folder Hierarchy & Tree ---

function buildTree(folders) {
  const map = new Map();
  const roots = [];
  folders.forEach((f) => map.set(f.id, { ...f, children: [] }));
  folders.forEach((f) => {
    const node = map.get(f.id);
    if (f.parent_folder_id == null) {
      roots.push(node);
    } else {
      const parent = map.get(f.parent_folder_id);
      if (parent) parent.children.push(node);
      else roots.push(node);
    }
  });

  const sort = (nodes) => {
    nodes.sort((a, b) => a.name.localeCompare(b.name, undefined, { sensitivity: 'base' }));
    nodes.forEach((n) => sort(n.children));
  };
  sort(roots);
  return roots;
}

function getBreadcrumbs(folderId) {
  const crumbs = [];
  let currentId = folderId;
  const folderMap = new Map(state.folders.map((f) => [f.id, f]));

  while (currentId) {
    const folder = folderMap.get(currentId);
    if (!folder) break;
    crumbs.unshift(folder);
    currentId = folder.parent_folder_id;
  }
  return crumbs;
}

function renderBreadcrumbs() {
  const container = $('folder-breadcrumbs');
  container.innerHTML = '';

  const crumbs = getBreadcrumbs(state.selectedFolderId);
  if (crumbs.length === 0) {
    container.innerHTML = '<span class="breadcrumb-item">Root</span>';
    return;
  }

  crumbs.forEach((folder, idx) => {
    if (idx > 0) {
      const sep = document.createElement('span');
      sep.className = 'breadcrumb-sep';
      sep.textContent = '>';
      container.appendChild(sep);
    }
    const span = document.createElement('span');
    span.className = `breadcrumb-item ${idx === crumbs.length - 1 ? 'current' : ''}`;
    span.textContent = folder.name;
    span.style.cursor = 'pointer';
    span.onclick = () => selectFolder(folder.id);
    container.appendChild(span);
  });
}

function renderFolderNode(node, depth = 0) {
  const hasChildren = node.children && node.children.length > 0;
  const isExpanded = state.expandedFolders.has(node.id);

  // If filter applied, check match
  if (state.folderFilter) {
    const term = state.folderFilter.toLowerCase();
    const matchesSelf = node.name.toLowerCase().includes(term);
    const matchesChild = (function checkDesc(n) {
      return n.children && n.children.some((c) => c.name.toLowerCase().includes(term) || checkDesc(c));
    })(node);
    if (!matchesSelf && !matchesChild) return document.createDocumentFragment();
  }

  const container = document.createElement('div');
  container.className = 'tree-node';

  const row = document.createElement('div');
  row.className = `folder-row ${state.selectedFolderId === node.id ? 'active' : ''}`;
  row.style.paddingLeft = `${depth * 14 + 6}px`;

  // Expand / collapse arrow
  const expandBtn = document.createElement('span');
  expandBtn.className = `folder-expand-icon ${!isExpanded ? 'collapsed' : ''}`;
  expandBtn.textContent = hasChildren ? '▼' : '';
  expandBtn.onclick = (e) => {
    e.stopPropagation();
    if (hasChildren) {
      if (isExpanded) state.expandedFolders.delete(node.id);
      else state.expandedFolders.add(node.id);
      renderFolders();
    }
  };

  // Folder Icon & Name
  const icon = document.createElement('span');
  icon.className = 'folder-icon';
  icon.textContent = isExpanded && hasChildren ? '📂' : '📁';

  const name = document.createElement('span');
  name.className = 'folder-name';
  name.textContent = node.name;

  // File Count
  const count = document.createElement('span');
  count.className = 'folder-file-badge';
  count.textContent = node.file_count > 0 ? node.file_count : '';

  // Quick Action Buttons
  const actions = document.createElement('span');
  actions.className = 'folder-actions';
  actions.innerHTML = `
    <button title="Download folder as ZIP" data-act="zip">⬇️</button>
    <button title="Copy all text in folder" data-act="copy">📋</button>
    <button title="Duplicate folder" data-act="dup">📄</button>
    <button title="Create subfolder" data-act="sub">+</button>
    <button title="Rename folder" data-act="rename">✎</button>
    <button title="Delete folder" data-act="del">×</button>
  `;
  actions.onclick = (e) => {
    e.stopPropagation();
    const act = e.target.dataset.act;
    if (act === 'zip') downloadFolderZip(node.id);
    if (act === 'copy') copyFolderText(node.id);
    if (act === 'dup') duplicateFolder(node.id);
    if (act === 'sub') promptNewFolder(node.id);
    if (act === 'rename') promptRenameFolder(node.id, node.name);
    if (act === 'del') promptDeleteFolder(node.id, node.name);
  };

  row.appendChild(expandBtn);
  row.appendChild(icon);
  row.appendChild(name);
  if (node.file_count > 0) row.appendChild(count);
  row.appendChild(actions);

  row.onclick = () => selectFolder(node.id);

  container.appendChild(row);

  // Render children
  if (hasChildren) {
    const childrenContainer = document.createElement('div');
    childrenContainer.className = `tree-children ${!isExpanded ? 'collapsed' : ''}`;
    node.children.forEach((c) => childrenContainer.appendChild(renderFolderNode(c, depth + 1)));
    container.appendChild(childrenContainer);
  }

  return container;
}

function renderFolders() {
  const tree = buildTree(state.folders);
  const el = $('folder-tree');
  el.innerHTML = '';
  $('folder-count-badge').textContent = state.folders.length;

  if (tree.length === 0) {
    el.innerHTML = '<p style="padding:16px 12px;color:var(--text-muted);font-size:0.82rem;text-align:center;">No folders yet.<br>Click "+ New" to begin.</p>';
    return;
  }

  tree.forEach((node) => el.appendChild(renderFolderNode(node)));
}

async function loadFolders() {
  try {
    const { folders } = await api('/api/folders');
    state.folders = folders;
    renderFolders();
    updateFolderDropdowns();

    // Auto-select first folder if none selected
    if (!state.selectedFolderId && folders.length > 0) {
      selectFolder(folders[0].id);
    } else if (state.selectedFolderId) {
      const stillExists = folders.some((f) => f.id === state.selectedFolderId);
      if (!stillExists) {
        if (folders.length > 0) selectFolder(folders[0].id);
        else showWelcome(true);
      }
    }
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function updateFolderDropdowns() {
  const populate = (selectEl, includeRoot = false) => {
    if (!selectEl) return;
    const currentVal = selectEl.value;
    selectEl.innerHTML = includeRoot ? '<option value="">[Root Directory]</option>' : '';

    // Flat indented options
    const flatTree = (nodes, prefix = '') => {
      nodes.forEach((n) => {
        const opt = document.createElement('option');
        opt.value = n.id;
        opt.textContent = prefix + n.name;
        selectEl.appendChild(opt);
        if (n.children && n.children.length > 0) {
          flatTree(n.children, prefix + '— ');
        }
      });
    };
    flatTree(buildTree(state.folders));
    if (currentVal) selectEl.value = currentVal;
  };

  populate($('file-folder-select'), false);
  populate($('qp-folder-select'), false);
  populate($('import-target-folder'), true);
}

function promptNewFolder(parentId = null) {
  const parent = state.folders.find((f) => f.id === parentId);
  const title = parent ? `New Subfolder in "${parent.name}"` : 'Create New Folder';

  showDialog({
    title,
    message: 'Enter a name for the folder:',
    inputLabel: 'Folder Name',
    inputValue: '',
    confirmText: 'Create Folder',
    onConfirm: async (name) => {
      if (!name) return;
      try {
        const { folder } = await api('/api/folders', {
          method: 'POST',
          body: JSON.stringify({ name, parent_folder_id: parentId }),
        });
        if (parentId) state.expandedFolders.add(parentId);
        await loadFolders();
        selectFolder(folder.id);
        showToast(`Folder "${name}" created!`, 'success');
      } catch (err) {
        showToast(err.message, 'error');
      }
    },
  });
}

function promptRenameFolder(id, currentName) {
  showDialog({
    title: 'Rename Folder',
    message: 'Enter the new name for this folder:',
    inputLabel: 'Folder Name',
    inputValue: currentName,
    confirmText: 'Rename',
    onConfirm: async (newName) => {
      if (!newName || newName === currentName) return;
      try {
        await api(`/api/folders/${id}`, {
          method: 'PATCH',
          body: JSON.stringify({ name: newName }),
        });
        await loadFolders();
        showToast(`Folder renamed to "${newName}"`, 'success');
      } catch (err) {
        showToast(err.message, 'error');
      }
    },
  });
}

function promptDeleteFolder(id, name) {
  showDialog({
    title: 'Delete Folder',
    message: `Are you sure you want to delete "${name}" and all of its files and subfolders? This action cannot be undone.`,
    confirmText: 'Delete Permanently',
    onConfirm: async () => {
      try {
        await api(`/api/folders/${id}`, { method: 'DELETE' });
        if (state.selectedFolderId === id) {
          state.selectedFolderId = null;
          state.selectedFileId = null;
          state.activeFile = null;
        }
        await loadFolders();
        showToast(`Folder "${name}" deleted`, 'info');
      } catch (err) {
        showToast(err.message, 'error');
      }
    },
  });
}

$('new-root-folder-btn').onclick = () => promptNewFolder(null);
$('welcome-new-folder-btn').onclick = () => promptNewFolder(null);

$('folder-filter-input').oninput = (e) => {
  state.folderFilter = e.target.value;
  renderFolders();
};

// --- Files List & Explorer ---

function showWelcome(show) {
  $('welcome-view').classList.toggle('hidden', !show);
  $('workspace-view').classList.toggle('hidden', show);
}

async function selectFolder(id) {
  state.selectedFolderId = id;
  state.selectedFileId = null;
  state.activeFile = null;
  state.expandedFolders.add(id);

  renderFolders();
  renderBreadcrumbs();
  showWelcome(false);
  closeSidebar();

  try {
    const { files } = await api(`/api/files?folder_id=${id}`);
    state.files = files;
    renderFiles();
    showEditor(false);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function renderFiles() {
  const list = $('file-list');
  list.innerHTML = '';

  let filesToRender = state.files;
  if (state.fileFilter) {
    const term = state.fileFilter.toLowerCase();
    filesToRender = filesToRender.filter((f) => f.name.toLowerCase().includes(term));
  }

  if (filesToRender.length === 0) {
    list.innerHTML = `
      <li style="padding: 24px 16px; text-align: center; color: var(--text-muted); font-size: 0.82rem;">
        ${state.fileFilter ? 'No matching files found.' : 'No files in this folder.<br>Click "+ New File" or "Paste".'}
      </li>
    `;
    return;
  }

  filesToRender.forEach((f) => {
    const li = document.createElement('li');
    li.className = `file-list-item ${f.id === state.selectedFileId ? 'active' : ''}`;

    const icon = document.createElement('span');
    icon.className = 'file-item-icon';
    icon.textContent = getFileIcon(f.name);

    const info = document.createElement('div');
    info.className = 'file-item-info';

    const name = document.createElement('div');
    name.className = 'file-item-name';
    name.textContent = f.name;

    const meta = document.createElement('div');
    meta.className = 'file-item-meta';
    meta.innerHTML = `<span>${formatBytes(f.size)}</span>`;

    info.appendChild(name);
    info.appendChild(meta);

    const itemActions = document.createElement('div');
    itemActions.className = 'file-item-actions';
    itemActions.innerHTML = `
      <button class="file-act-btn" title="Copy file text to clipboard" data-act="copy">📋</button>
      <button class="file-act-btn" title="Download file" data-act="down">⬇️</button>
      <button class="file-act-btn" title="Duplicate file" data-act="dup">📄</button>
      <button class="file-act-btn del" title="Delete file" data-act="del">×</button>
    `;
    itemActions.onclick = (e) => {
      e.stopPropagation();
      const act = e.target.dataset.act;
      if (act === 'copy') copySingleFileText(f.id, f.name);
      if (act === 'down') downloadSingleFile(f.id, f.name);
      if (act === 'dup') duplicateSingleFile(f.id);
      if (act === 'del') promptDeleteFile(f.id, f.name);
    };

    li.appendChild(icon);
    li.appendChild(info);
    li.appendChild(itemActions);

    li.onclick = () => openFile(f.id);
    list.appendChild(li);
  });
}

$('file-filter-input').oninput = (e) => {
  state.fileFilter = e.target.value;
  renderFiles();
};

function promptNewFile() {
  if (!state.selectedFolderId) {
    showToast('Please select or create a folder first', 'error');
    return;
  }

  showDialog({
    title: 'Create New File',
    message: 'Enter file name (e.g. note.txt, index.js, script.py):',
    inputLabel: 'File Name',
    inputValue: 'untitled.txt',
    confirmText: 'Create File',
    onConfirm: async (name) => {
      if (!name) return;
      try {
        const { file } = await api('/api/files', {
          method: 'POST',
          body: JSON.stringify({ folder_id: state.selectedFolderId, name, content: '' }),
        });
        const { files } = await api(`/api/files?folder_id=${state.selectedFolderId}`);
        state.files = files;
        renderFiles();
        await openFile(file.id);
        showToast(`File "${name}" created!`, 'success');
      } catch (err) {
        showToast(err.message, 'error');
      }
    },
  });
}

function promptDeleteFile(id, name) {
  showDialog({
    title: 'Delete File',
    message: `Are you sure you want to delete "${name}"?`,
    confirmText: 'Delete',
    onConfirm: async () => {
      try {
        await api(`/api/files/${id}`, { method: 'DELETE' });
        if (state.selectedFileId === id) {
          state.selectedFileId = null;
          state.activeFile = null;
          showEditor(false);
        }
        const { files } = await api(`/api/files?folder_id=${state.selectedFolderId}`);
        state.files = files;
        renderFiles();
        showToast(`File "${name}" deleted`, 'info');
      } catch (err) {
        showToast(err.message, 'error');
      }
    },
  });
}

$('new-file-btn').onclick = promptNewFile;
$('empty-new-file-btn').onclick = promptNewFile;

// --- Editor & Content Management ---

async function openFile(id) {
  state.selectedFileId = id;
  renderFiles();

  try {
    const { file } = await api(`/api/files/${id}`);
    state.activeFile = file;

    $('file-name-input').value = file.name;
    $('file-content-editor').value = file.content;
    $('file-folder-select').value = file.folder_id;

    updateEditorStats(file.content);
    setSaveStatus('saved');
    showEditor(true);
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function showEditor(show) {
  $('editor-empty').classList.toggle('hidden', show);
  $('editor-container').classList.toggle('hidden', !show);
}

function updateEditorStats(text) {
  const lines = text ? text.split('\n').length : 0;
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const chars = text.length;
  const bytes = new Blob([text]).size;

  $('stat-lines').textContent = `${lines} line${lines === 1 ? '' : 's'}`;
  $('stat-words').textContent = `${words} word${words === 1 ? '' : 's'}`;
  $('stat-chars').textContent = `${chars} char${chars === 1 ? '' : 's'}`;
  $('stat-size').textContent = formatBytes(bytes);
}

function setSaveStatus(status) {
  const el = $('save-status-indicator');
  if (status === 'saved') {
    el.textContent = '✓ Saved';
    el.className = 'status-indicator saved';
  } else if (status === 'saving') {
    el.textContent = 'Saving...';
    el.className = 'status-indicator unsaved';
  } else {
    el.textContent = '• Unsaved';
    el.className = 'status-indicator unsaved';
  }
}

async function saveCurrentFile() {
  if (!state.activeFile) return;
  setSaveStatus('saving');

  const newName = $('file-name-input').value.trim() || state.activeFile.name;
  const newContent = $('file-content-editor').value;
  const newFolderId = Number($('file-folder-select').value);

  try {
    const { file } = await api(`/api/files/${state.activeFile.id}`, {
      method: 'PATCH',
      body: JSON.stringify({
        name: newName,
        content: newContent,
        folder_id: newFolderId,
      }),
    });

    state.activeFile = file;
    state.dirty = false;
    setSaveStatus('saved');

    // If folder changed, move to the new folder
    if (file.folder_id !== state.selectedFolderId) {
      await loadFolders();
      selectFolder(file.folder_id);
    } else {
      const { files } = await api(`/api/files?folder_id=${state.selectedFolderId}`);
      state.files = files;
      renderFiles();
    }
  } catch (err) {
    setSaveStatus('unsaved');
    showToast(err.message, 'error');
  }
}

function scheduleAutoSave() {
  state.dirty = true;
  setSaveStatus('unsaved');
  updateEditorStats($('file-content-editor').value);
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveCurrentFile, 700);
}

// Editor Event Listeners
$('file-content-editor').oninput = scheduleAutoSave;
$('file-name-input').oninput = scheduleAutoSave;
$('file-folder-select').onchange = saveCurrentFile;
$('save-file-btn').onclick = saveCurrentFile;

// Support Tab Key in Textarea
$('file-content-editor').addEventListener('keydown', (e) => {
  if (e.key === 'Tab') {
    e.preventDefault();
    const textarea = e.target;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    textarea.value = textarea.value.substring(0, start) + '  ' + textarea.value.substring(end);
    textarea.selectionStart = textarea.selectionEnd = start + 2;
    scheduleAutoSave();
  }
});

// Copy Text to Clipboard
async function copyActiveFileText() {
  if (!state.activeFile) return;
  const content = $('file-content-editor').value;
  try {
    await navigator.clipboard.writeText(content);
    showToast('Text copied to clipboard!', 'success');
  } catch {
    // Fallback copy
    const textarea = document.createElement('textarea');
    textarea.value = content;
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    document.body.removeChild(textarea);
    showToast('Text copied to clipboard!', 'success');
  }
}

$('copy-text-btn').onclick = copyActiveFileText;

// Duplicate Active File
$('duplicate-file-btn').onclick = async () => {
  if (!state.activeFile) return;
  try {
    const { file } = await api(`/api/files/${state.activeFile.id}/duplicate`, { method: 'POST' });
    const { files } = await api(`/api/files?folder_id=${state.selectedFolderId}`);
    state.files = files;
    renderFiles();
    openFile(file.id);
    showToast(`Created copy "${file.name}"`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
};

// Download Active File
$('download-file-btn').onclick = () => {
  if (!state.activeFile) return;
  const name = $('file-name-input').value.trim() || 'export.txt';
  const content = $('file-content-editor').value;
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`Downloaded "${name}"`, 'success');
};

// Delete Active File
$('delete-active-file-btn').onclick = () => {
  if (!state.activeFile) return;
  promptDeleteFile(state.activeFile.id, state.activeFile.name);
};

// --- Entire Folder & File Download / Copy Operations ---

async function downloadFolderZip(folderId) {
  const folder = state.folders.find((f) => f.id === folderId);
  const name = folder ? folder.name : 'folder';
  showToast(`Preparing ZIP for "${name}"...`, 'info');
  try {
    const token = getToken();
    const res = await fetch(`/api/folders/${folderId}/download`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || 'Failed to download folder ZIP');
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${name}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(`Downloaded "${name}.zip"!`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function copyFolderText(folderId) {
  const folder = state.folders.find((f) => f.id === folderId);
  const name = folder ? folder.name : 'folder';
  try {
    const data = await api(`/api/folders/${folderId}/text-bundle`);
    if (!data.bundle_text) {
      showToast(`No files found in folder "${name}" to copy`, 'info');
      return;
    }
    await navigator.clipboard.writeText(data.bundle_text).catch(() => {
      const textarea = document.createElement('textarea');
      textarea.value = data.bundle_text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    });
    showToast(`Copied all ${data.file_count} file(s) from "${name}" to clipboard!`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function duplicateFolder(folderId) {
  const folder = state.folders.find((f) => f.id === folderId);
  const name = folder ? folder.name : 'folder';
  try {
    const { folder: cloned } = await api(`/api/folders/${folderId}/duplicate`, { method: 'POST' });
    await loadFolders();
    selectFolder(cloned.id);
    showToast(`Duplicated folder "${name}"!`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function copySingleFileText(fileId, fileName) {
  try {
    const { file } = await api(`/api/files/${fileId}`);
    await navigator.clipboard.writeText(file.content || '').catch(() => {
      const textarea = document.createElement('textarea');
      textarea.value = file.content || '';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    });
    showToast(`Copied "${fileName}" to clipboard!`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function downloadSingleFile(fileId, fileName) {
  try {
    const { file } = await api(`/api/files/${fileId}`);
    const blob = new Blob([file.content || ''], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(`Downloaded "${fileName}"`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

async function duplicateSingleFile(fileId) {
  try {
    const { file } = await api(`/api/files/${fileId}/duplicate`, { method: 'POST' });
    const { files } = await api(`/api/files?folder_id=${state.selectedFolderId}`);
    state.files = files;
    renderFiles();
    showToast(`Duplicated "${file.name}"`, 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
}

// Folder Action Header Buttons
$('download-folder-btn').onclick = () => {
  if (state.selectedFolderId) downloadFolderZip(state.selectedFolderId);
};
$('copy-folder-text-btn').onclick = () => {
  if (state.selectedFolderId) copyFolderText(state.selectedFolderId);
};
$('duplicate-folder-btn').onclick = () => {
  if (state.selectedFolderId) duplicateFolder(state.selectedFolderId);
};

// --- Quick Paste Feature ---

function openQuickPasteModal(prefillFolderId = null) {
  updateFolderDropdowns();
  const folderId = prefillFolderId || state.selectedFolderId || (state.folders[0] ? state.folders[0].id : '');
  $('qp-folder-select').value = folderId;
  $('qp-file-name').value = '';
  $('qp-content').value = '';
  openModal('quick-paste-modal');
  setTimeout(() => $('qp-content').focus(), 100);
}

$('top-quick-paste-btn').onclick = () => openQuickPasteModal();
$('welcome-quick-paste-btn').onclick = () => openQuickPasteModal();
$('paste-here-btn').onclick = () => openQuickPasteModal(state.selectedFolderId);

$('qp-read-clipboard-btn').onclick = async () => {
  try {
    const text = await navigator.clipboard.readText();
    $('qp-content').value = text;
    if (!$('qp-file-name').value.trim()) {
      const firstLine = text.trim().split('\n')[0].slice(0, 20).replace(/[^a-zA-Z0-9_-]/g, '_');
      $('qp-file-name').value = (firstLine || 'snippet') + '.txt';
    }
  } catch {
    showToast('Clipboard access denied. Please paste manually.', 'error');
  }
};

$('qp-submit-btn').onclick = async () => {
  const folderId = Number($('qp-folder-select').value);
  if (!folderId) {
    showToast('Please choose a folder to save this file', 'error');
    return;
  }

  let fileName = $('qp-file-name').value.trim();
  const content = $('qp-content').value;

  if (!fileName) {
    fileName = 'pasted_note_' + new Date().toISOString().slice(11, 19).replace(/:/g, '') + '.txt';
  }

  try {
    const { file } = await api('/api/files', {
      method: 'POST',
      body: JSON.stringify({ folder_id: folderId, name: fileName, content }),
    });

    closeModal('quick-paste-modal');
    showToast(`File "${file.name}" saved!`, 'success');

    await loadFolders();
    selectFolder(folderId);
    openFile(file.id);
  } catch (err) {
    showToast(err.message, 'error');
  }
};

// --- Local Folder & Multi-File Importer ---

function openImportModal() {
  updateFolderDropdowns();
  $('import-target-folder').value = state.selectedFolderId || '';
  state.stagedImportItems = [];
  renderStagedFiles();
  openModal('import-folder-modal');
}

$('top-import-folder-btn').onclick = openImportModal;
$('sidebar-import-btn').onclick = openImportModal;
$('welcome-import-folder-btn').onclick = openImportModal;

// Tab Switching inside Import Modal
const importTabs = ['folder', 'files', 'paste'];
importTabs.forEach((tab) => {
  $(`tab-btn-${tab}`).onclick = () => {
    importTabs.forEach((t) => {
      $(`tab-btn-${t}`).classList.toggle('active', t === tab);
      $(`tab-pane-${t}`).classList.toggle('hidden', t !== tab);
    });
  };
});

function renderStagedFiles() {
  const summaryEl = $('import-staged-summary');
  const countEl = $('staged-count-text');
  const listEl = $('staged-files-list');
  const submitBtn = $('import-submit-btn');

  if (state.stagedImportItems.length === 0) {
    summaryEl.classList.add('hidden');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Import Files';
    return;
  }

  summaryEl.classList.remove('hidden');
  submitBtn.disabled = false;
  countEl.textContent = `${state.stagedImportItems.length} file(s) ready to import`;
  submitBtn.textContent = `Import ${state.stagedImportItems.length} File(s)`;

  listEl.innerHTML = state.stagedImportItems
    .slice(0, 10)
    .map((item) => `<div>• ${item.path} (${formatBytes(new Blob([item.content]).size)})</div>`)
    .join('');

  if (state.stagedImportItems.length > 10) {
    listEl.innerHTML += `<div>...and ${state.stagedImportItems.length - 10} more</div>`;
  }
}

async function readUploadedFiles(fileList) {
  const items = [];
  for (let i = 0; i < fileList.length; i++) {
    const file = fileList[i];
    // Skip binary files larger than 5MB or non-text where possible
    if (file.size > 5 * 1024 * 1024) continue;

    const path = file.webkitRelativePath || file.name;
    const content = await file.text().catch(() => '');
    items.push({ path, content });
  }
  state.stagedImportItems = items;
  renderStagedFiles();
}

$('local-folder-input').onchange = (e) => readUploadedFiles(e.target.files);
$('local-files-input').onchange = (e) => readUploadedFiles(e.target.files);

// Drag & Drop onto Folder Drop Zone
const dropZone = $('folder-drop-zone');
['dragenter', 'dragover'].forEach((eventName) => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });
});
['dragleave', 'drop'].forEach((eventName) => {
  dropZone.addEventListener(eventName, (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
  });
});
dropZone.addEventListener('drop', (e) => {
  if (e.dataTransfer.files.length) {
    readUploadedFiles(e.dataTransfer.files);
  }
});

// Parse Text Hierarchy Paste Tab
$('paste-hierarchy-text').oninput = (e) => {
  const text = e.target.value;
  if (!text.trim()) {
    state.stagedImportItems = [];
    renderStagedFiles();
    return;
  }

  // Parse snippets separated by --- path/to/file.ext ---
  const sections = text.split(/---+\s*([^\n\r]+?)\s*---+/g);
  const items = [];

  if (sections.length > 1) {
    for (let i = 1; i < sections.length; i += 2) {
      const path = sections[i].trim();
      const content = (sections[i + 1] || '').trim();
      if (path) items.push({ path, content });
    }
  } else {
    // Single file
    items.push({ path: 'imported_snippet.txt', content: text });
  }

  state.stagedImportItems = items;
  renderStagedFiles();
};

$('import-submit-btn').onclick = async () => {
  if (state.stagedImportItems.length === 0) return;
  const targetFolderId = $('import-target-folder').value ? Number($('import-target-folder').value) : null;
  const submitBtn = $('import-submit-btn');
  submitBtn.disabled = true;
  submitBtn.textContent = 'Importing...';

  try {
    const res = await api('/api/import/batch', {
      method: 'POST',
      body: JSON.stringify({
        target_folder_id: targetFolderId,
        items: state.stagedImportItems,
      }),
    });

    closeModal('import-folder-modal');
    showToast(`Successfully imported ${res.created_files} files across ${res.created_folders} new folders!`, 'success');
    await loadFolders();
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Import Files';
  }
};

// --- Global Search (Ctrl/Cmd + K) ---

function openSearchModal() {
  openModal('search-modal');
  const input = $('global-search-input');
  input.value = '';
  $('search-results-container').innerHTML = '<div class="search-empty-hint">Type a keyword to find any file, folder, or text snippet.</div>';
  setTimeout(() => input.focus(), 50);
}

$('search-trigger-btn').onclick = openSearchModal;

$('global-search-input').oninput = (e) => {
  const query = e.target.value.trim();
  clearTimeout(state.searchTimer);
  if (!query) {
    $('search-results-container').innerHTML = '<div class="search-empty-hint">Type a keyword to find any file, folder, or text snippet.</div>';
    return;
  }

  state.searchTimer = setTimeout(async () => {
    try {
      const res = await api(`/api/search?q=${encodeURIComponent(query)}`);
      renderSearchResults(res);
    } catch (err) {
      showToast(err.message, 'error');
    }
  }, 250);
};

function renderSearchResults({ folders, files, query }) {
  const container = $('search-results-container');
  container.innerHTML = '';

  if (folders.length === 0 && files.length === 0) {
    container.innerHTML = `<div class="search-empty-hint">No results found for "${query}".</div>`;
    return;
  }

  if (folders.length > 0) {
    const group = document.createElement('div');
    group.className = 'search-group-title';
    group.textContent = `Folders (${folders.length})`;
    container.appendChild(group);

    folders.forEach((f) => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = `
        <div class="search-item-head">
          <span>📁</span>
          <span>${f.name}</span>
        </div>
      `;
      item.onclick = () => {
        closeModal('search-modal');
        selectFolder(f.id);
      };
      container.appendChild(item);
    });
  }

  if (files.length > 0) {
    const group = document.createElement('div');
    group.className = 'search-group-title';
    group.textContent = `Files (${files.length})`;
    container.appendChild(group);

    files.forEach((f) => {
      const item = document.createElement('div');
      item.className = 'search-result-item';
      item.innerHTML = `
        <div class="search-item-head">
          <span>${getFileIcon(f.name)}</span>
          <span>${f.name}</span>
          <span class="search-item-folder">in 📂 ${f.folder_name}</span>
        </div>
        ${f.snippet ? `<div class="search-item-snippet">${f.snippet.replace(/\n/g, ' ')}</div>` : ''}
      `;
      item.onclick = async () => {
        closeModal('search-modal');
        await selectFolder(f.folder_id);
        openFile(f.id);
      };
      container.appendChild(item);
    });
  }
}

// --- Export Vault Data ---

$('top-export-btn').onclick = async () => {
  try {
    const data = await api('/api/export');
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `text-vault-export-${state.user.username}-${new Date().toISOString().slice(0, 10)}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('Vault backup downloaded successfully!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  }
};

// --- Mobile Sidebar Drawer ---

function closeSidebar() {
  $('sidebar').classList.remove('open');
  $('sidebar-overlay').classList.add('hidden');
}

$('menu-btn').onclick = () => {
  $('sidebar').classList.toggle('open');
  $('sidebar-overlay').classList.toggle('hidden');
};
$('sidebar-overlay').onclick = closeSidebar;

// --- Global Keyboard Shortcuts ---

window.addEventListener('keydown', (e) => {
  // Ctrl/Cmd + S to save file
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
    e.preventDefault();
    if (state.activeFile) {
      saveCurrentFile();
      showToast('File saved!', 'success');
    }
  }

  // Ctrl/Cmd + K to open search
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    openSearchModal();
  }

  // Ctrl/Cmd + Shift + C to copy text
  if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'c') {
    if (state.activeFile) {
      e.preventDefault();
      copyActiveFileText();
    }
  }

  // Escape to close open modals
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay').forEach((modal) => {
      modal.classList.add('hidden');
    });
    closeSidebar();
  }
});

// --- Initialize App ---
checkAuth();
