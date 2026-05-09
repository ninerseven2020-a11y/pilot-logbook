let allHistory = [];

document.addEventListener('DOMContentLoaded', () => {
    fetchHistory();
    setupOpeningTotalsInputs();
});

let metadata = { operators: [], labels: [] };

async function fetchMetadata() {
    const token = getToken();
    if (!token) return;
    try {
        const response = await fetch('/api/upload_metadata', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        metadata = await response.json();
        populateFilters(); // Re-populate with metadata if needed
        
        // Populate edit suggestions datalists
        const operatorList = document.getElementById('edit-operator-list');
        const labelList = document.getElementById('edit-label-list');
        if (operatorList && labelList) {
            operatorList.innerHTML = '';
            labelList.innerHTML = '';
            metadata.operators.forEach(o => {
                const opt = document.createElement('option');
                opt.value = o;
                operatorList.appendChild(opt);
            });
            metadata.labels.forEach(n => {
                const opt = document.createElement('option');
                opt.value = n;
                labelList.appendChild(opt);
            });
        }
    } catch (e) {
        console.error('Error fetching metadata:', e);
    }
}

function setupOpeningTotalsInputs() {
    // Re-apply smart decimal logic to the new inputs
    document.querySelectorAll('.smart-decimal').forEach(input => {
        input.addEventListener('blur', function() {
            let val = this.value;
            if (val && !isNaN(val)) {
                if (!val.includes('.')) {
                    val = val + '.0';
                }
                this.value = parseFloat(val).toFixed(1);
            }
        });
    });
}

async function fetchHistory() {
    const token = getToken();
    if (!token) return;

    try {
        const response = await fetch('/api/history', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const data = await response.json();
        allHistory = data.history;
        await fetchMetadata(); // Ensure metadata is fresh for filters
        populateFilters();
        filterHistory();
    } catch (error) {
        console.error('Error fetching history:', error);
        showToast('Error loading history', 'error');
    }
}

function renderHistory(history) {
    const body = document.getElementById('history-body');
    body.innerHTML = '';

    history.forEach(entry => {
        const row = document.createElement('tr');
        row.id = `row-${entry.id}`;
        
        // Format date
        let dateStr = entry.date_str;
        if (entry.is_adjustment) dateStr = 'ADJUST';

        row.innerHTML = `
            <td><input type="checkbox" class="select-cb row-cb" data-id="${entry.id}" onchange="updateBatchBar()"></td>
            <td>${dateStr}</td>
            <td>${entry.ac_type || '---'}</td>
            <td>${entry.reg || '---'}</td>
            <td class="route-cell" title="${entry.pic || ''}">${entry.pic || '---'}</td>
            <td class="route-cell" title="${entry.copilot || ''}">${entry.copilot || '---'}</td>
            <td class="route-cell" title="${entry.route || ''}">${entry.route || '---'}</td>
            <td>${entry.day_p1 || 0.0}</td>
            <td>${entry.day_p1us || 0.0}</td>
            <td>${entry.day_p2 || 0.0}</td>
            <td>${entry.day_dual || 0.0}</td>
            <td>${entry.night_p1 || 0.0}</td>
            <td>${entry.night_p1us || 0.0}</td>
            <td>${entry.night_p2 || 0.0}</td>
            <td>${entry.night_dual || 0.0}</td>
            <td>${entry.inst_flying || 0.0}</td>
            <td>${entry.sim_time || 0.0}</td>
            <td class="route-cell" title="${entry.operator || 'Default'}">${entry.operator || '---'}</td>
            <td class="route-cell" title="${entry.label || 'Default'}">${entry.label || '---'}</td>
            <td>
                <div class="action-btns">
                    <button class="btn-icon btn-edit" onclick="startEdit('${entry.id}')" title="Edit">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </button>
                    <button class="btn-icon btn-delete" onclick="deleteEntry('${entry.id}')" title="Delete">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                    </button>
                </div>
            </td>
        `;
        body.appendChild(row);
    });

    // Reset select-all and batch bar
    const selectAll = document.getElementById('select-all');
    if (selectAll) selectAll.checked = false;
    updateBatchBar();
}

function populateFilters() {
    const years = new Set();
    const types = new Set();
    
    allHistory.forEach(entry => {
        if (entry.date_obj) {
            const date = new Date(entry.date_obj);
            if (!isNaN(date)) years.add(date.getFullYear());
        }
        if (entry.ac_type) types.add(entry.ac_type);
    });

    const yearSelect = document.getElementById('filter-year');
    const typeSelect = document.getElementById('filter-type');

    // Save current values
    const currentYear = yearSelect.value;
    const currentType = typeSelect.value;

    // Clear existing options except "ALL"
    yearSelect.innerHTML = '<option value="ALL">All Years</option>';
    typeSelect.innerHTML = '<option value="ALL">All Types</option>';

    Array.from(years).sort((a, b) => b - a).forEach(year => {
        const opt = document.createElement('option');
        opt.value = year;
        opt.textContent = year;
        yearSelect.appendChild(opt);
    });

    Array.from(types).sort().forEach(type => {
        const opt = document.createElement('option');
        opt.value = type;
        opt.textContent = type;
        typeSelect.appendChild(opt);
    });

    // Restore values if they still exist
    if (Array.from(years).some(y => y.toString() === currentYear)) {
        yearSelect.value = currentYear;
    }
    if (Array.from(types).some(t => t === currentType)) {
        typeSelect.value = currentType;
    }

    // Populate Operator and Label filters
    const operatorSelect = document.getElementById('filter-operator');
    const labelSelect = document.getElementById('filter-label');
    
    if (operatorSelect && labelSelect) {
        const currentOperator = operatorSelect.value;
        const currentLabel = labelSelect.value;

        operatorSelect.innerHTML = '<option value="ALL">All Operators</option>';
        labelSelect.innerHTML = '<option value="ALL">All Labels</option>';

        const operators = new Set(metadata.operators);
        const labels = new Set(metadata.labels);

        // Also add anything present in history but not in metadata
        allHistory.forEach(e => {
            if (e.operator) operators.add(e.operator);
            if (e.label) labels.add(e.label);
        });

        Array.from(operators).sort().forEach(o => {
            const opt = document.createElement('option');
            opt.value = o;
            opt.textContent = o;
            operatorSelect.appendChild(opt);
        });

        Array.from(labels).sort().forEach(n => {
            const opt = document.createElement('option');
            opt.value = n;
            opt.textContent = n;
            labelSelect.appendChild(opt);
        });

        if (Array.from(operators).some(o => o === currentOperator)) operatorSelect.value = currentOperator;
        if (Array.from(labels).some(n => n === currentLabel)) labelSelect.value = currentLabel;
    }
}

function filterHistory() {
    const query = document.getElementById('history-search').value.toLowerCase();
    const filterYear = document.getElementById('filter-year').value;
    const filterMonth = document.getElementById('filter-month').value;
    const filterType = document.getElementById('filter-type').value;
    const filterOperator = document.getElementById('filter-operator').value;
    const filterLabel = document.getElementById('filter-label').value;
    const dateFrom = document.getElementById('filter-date-from').value;
    const dateTo = document.getElementById('filter-date-to').value;

    const filtered = allHistory.filter(entry => {
        // Search query
        const matchesQuery = !query || 
               (entry.date_str && entry.date_str.toLowerCase().includes(query)) ||
               (entry.ac_type && entry.ac_type.toLowerCase().includes(query)) ||
               (entry.reg && entry.reg.toLowerCase().includes(query)) ||
               (entry.route && entry.route.toLowerCase().includes(query)) ||
               (entry.remarks && entry.remarks.toLowerCase().includes(query));

        // Date range filter
        let matchesDateRange = true;
        if ((dateFrom || dateTo) && entry.date_obj) {
            const d = new Date(entry.date_obj);
            if (dateFrom) matchesDateRange = d >= new Date(dateFrom);
            if (dateTo && matchesDateRange) {
                const to = new Date(dateTo);
                to.setHours(23, 59, 59);
                matchesDateRange = d <= to;
            }
        } else if ((dateFrom || dateTo) && !entry.date_obj) {
            matchesDateRange = false;
        }

        // Year filter
        let matchesYear = true;
        if (filterYear !== 'ALL' && entry.date_obj) {
            const year = new Date(entry.date_obj).getFullYear();
            matchesYear = year.toString() === filterYear;
        }

        // Month filter
        let matchesMonth = true;
        if (filterMonth !== 'ALL' && entry.date_obj) {
            const month = new Date(entry.date_obj).getMonth();
            matchesMonth = month.toString() === filterMonth;
        }

        // Type filter
        let matchesType = true;
        if (filterType !== 'ALL') {
            matchesType = entry.ac_type === filterType;
        }

        // Operator filter
        let matchesOperator = true;
        if (filterOperator !== 'ALL') {
            matchesOperator = entry.operator === filterOperator;
        }

        // Label filter
        let matchesLabel = true;
        if (filterLabel !== 'ALL') {
            matchesLabel = entry.label === filterLabel;
        }

        return matchesQuery && matchesDateRange && matchesYear && matchesMonth && matchesType && matchesOperator && matchesLabel;
    });
    renderHistory(filtered);
}

// --- Batch Selection ---
function toggleSelectAll(masterCb) {
    document.querySelectorAll('.row-cb').forEach(cb => {
        cb.checked = masterCb.checked;
    });
    updateBatchBar();
}

function updateBatchBar() {
    const checked = document.querySelectorAll('.row-cb:checked');
    const bar = document.getElementById('batch-bar');
    const count = document.getElementById('batch-count');
    if (checked.length > 0) {
        bar.classList.add('visible');
        count.textContent = `${checked.length} selected`;
    } else {
        bar.classList.remove('visible');
    }
}

function clearSelection() {
    document.querySelectorAll('.row-cb').forEach(cb => cb.checked = false);
    const selectAll = document.getElementById('select-all');
    if (selectAll) selectAll.checked = false;
    updateBatchBar();
}

async function batchDelete() {
    const checked = document.querySelectorAll('.row-cb:checked');
    const ids = Array.from(checked).map(cb => cb.dataset.id);
    if (ids.length === 0) return;
    if (!confirm(`Are you sure you want to delete ${ids.length} entries? This cannot be undone.`)) return;

    const token = getToken();
    try {
        const response = await fetch('/api/entries/batch-delete', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ ids })
        });
        if (response.ok) {
            showToast(`${ids.length} entries deleted`);
            fetchHistory();
        } else {
            showToast('Batch delete failed', 'error');
        }
    } catch (error) {
        showToast('Server error', 'error');
    }
}

async function deleteEntry(id) {
    if (!confirm('Are you sure you want to delete this entry? This action cannot be undone.')) return;

    const token = getToken();
    try {
        const response = await fetch(`/api/entry/${id}`, {
            method: 'DELETE',
            headers: { 'Authorization': `Bearer ${token}` }
        });
        const result = await response.json();
        if (response.ok) {
            showToast('Entry deleted');
            fetchHistory(); // Refresh
        } else {
            showToast(result.detail || 'Delete failed', 'error');
        }
    } catch (error) {
        showToast('Server error', 'error');
    }
}

function startEdit(id) {
    const entry = allHistory.find(e => e.id === id);
    if (!entry) return;

    const row = document.getElementById(`row-${id}`);
    row.classList.add('edit-row');
    
    // Convert cells to inputs
    row.innerHTML = `
        <td></td>
        <td><input type="text" id="edit-date-${id}" value="${entry.date_str}"></td>
        <td><input type="text" id="edit-ac-${id}" value="${entry.ac_type || ''}"></td>
        <td><input type="text" id="edit-reg-${id}" value="${entry.reg || ''}"></td>
        <td><input type="text" id="edit-pic-${id}" value="${entry.pic || ''}"></td>
        <td><input type="text" id="edit-copilot-${id}" value="${entry.copilot || ''}"></td>
        <td><input type="text" id="edit-route-${id}" value="${entry.route || ''}"></td>
        
        <td><input type="number" step="0.1" id="edit-dayp1-${id}" value="${entry.day_p1 || 0.0}"></td>
        <td><input type="number" step="0.1" id="edit-dayp1us-${id}" value="${entry.day_p1us || 0.0}"></td>
        <td><input type="number" step="0.1" id="edit-dayp2-${id}" value="${entry.day_p2 || 0.0}"></td>
        <td><input type="number" step="0.1" id="edit-daydual-${id}" value="${entry.day_dual || 0.0}"></td>

        <td><input type="number" step="0.1" id="edit-nightp1-${id}" value="${entry.night_p1 || 0.0}"></td>
        <td><input type="number" step="0.1" id="edit-nightp1us-${id}" value="${entry.night_p1us || 0.0}"></td>
        <td><input type="number" step="0.1" id="edit-nightp2-${id}" value="${entry.night_p2 || 0.0}"></td>
        <td><input type="number" step="0.1" id="edit-nightdual-${id}" value="${entry.night_dual || 0.0}"></td>

        <td><input type="number" step="0.1" id="edit-inst-${id}" value="${entry.inst_flying || 0.0}"></td>
        <td><input type="number" step="0.1" id="edit-sim-${id}" value="${entry.sim_time || 0.0}"></td>
        <td><input type="text" id="edit-operator-${id}" value="${entry.operator || 'Default'}" list="edit-operator-list"></td>
        <td><input type="text" id="edit-label-${id}" value="${entry.label || 'Default'}" list="edit-label-list"></td>
        <td>
            <div class="action-btns">
                <button class="btn btn-primary btn-sm" onclick="saveEdit('${id}')">Save</button>
                <button class="btn btn-secondary btn-sm" onclick="fetchHistory()">Cancel</button>
            </div>
        </td>
    `;
}

async function saveEdit(id) {
    const token = getToken();
    const updatedData = {
        date_str: document.getElementById(`edit-date-${id}`).value,
        ac_type: document.getElementById(`edit-ac-${id}`).value,
        reg: document.getElementById(`edit-reg-${id}`).value,
        pic: document.getElementById(`edit-pic-${id}`).value,
        copilot: document.getElementById(`edit-copilot-${id}`).value,
        route: document.getElementById(`edit-route-${id}`).value,
        
        day_p1: parseFloat(document.getElementById(`edit-dayp1-${id}`).value),
        day_p1us: parseFloat(document.getElementById(`edit-dayp1us-${id}`).value),
        day_p2: parseFloat(document.getElementById(`edit-dayp2-${id}`).value),
        day_dual: parseFloat(document.getElementById(`edit-daydual-${id}`).value),

        night_p1: parseFloat(document.getElementById(`edit-nightp1-${id}`).value),
        night_p1us: parseFloat(document.getElementById(`edit-nightp1us-${id}`).value),
        night_p2: parseFloat(document.getElementById(`edit-nightp2-${id}`).value),
        night_dual: parseFloat(document.getElementById(`edit-nightdual-${id}`).value),

        inst_flying: parseFloat(document.getElementById(`edit-inst-${id}`).value),
        sim_time: parseFloat(document.getElementById(`edit-sim-${id}`).value),
        operator: document.getElementById(`edit-operator-${id}`).value,
        label: document.getElementById(`edit-label-${id}`).value
    };

    try {
        const response = await fetch(`/api/entry/${id}`, {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(updatedData)
        });
        
        if (response.ok) {
            showToast('Entry updated');
            fetchHistory();
        } else {
            showToast('Update failed', 'error');
        }
    } catch (error) {
        showToast('Server error', 'error');
    }
}

async function handleOpeningTotalsSubmit(event) {
    event.preventDefault();
    const token = getToken();
    
    const payload = {
        year: parseInt(document.getElementById('open-year').value) || 1900,
        ac_type: document.getElementById('open-ac-type').value,
        day_p1: parseFloat(document.getElementById('open-day-p1').value || 0),
        day_p1us: parseFloat(document.getElementById('open-day-p1us').value || 0),
        day_p2: parseFloat(document.getElementById('open-day-p2').value || 0),
        day_put: parseFloat(document.getElementById('open-day-put').value || 0),
        night_p1: parseFloat(document.getElementById('open-night-p1').value || 0),
        night_p1us: parseFloat(document.getElementById('open-night-p1us').value || 0),
        night_p2: parseFloat(document.getElementById('open-night-p2').value || 0),
        night_put: parseFloat(document.getElementById('open-night-put').value || 0),
        inst: parseFloat(document.getElementById('open-inst').value || 0),
        sim: parseFloat(document.getElementById('open-sim-day').value || 0) + parseFloat(document.getElementById('open-sim-night').value || 0),
        operator: document.getElementById('open-operator').value || 'Default',
        label: document.getElementById('open-remarks').value || ' Initial Training, PPEP'
    };

    try {
        const response = await fetch('/api/opening_totals', {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            showToast('Opening totals added');
            event.target.reset();
            fetchHistory();
        } else {
            showToast('Failed to add opening totals', 'error');
        }
    } catch (error) {
        showToast('Server error', 'error');
    }
}

// --- Batch Edit ---
function openBatchEdit() {
    const checked = document.querySelectorAll('.row-cb:checked');
    if (checked.length === 0) return;
    
    document.getElementById('batch-edit-info').textContent = `Editing ${checked.length} entries`;
    document.getElementById('batch-edit-modal').classList.add('show');
    document.getElementById('batch-value').value = '';

    // Update suggestions based on field
    const fieldSelect = document.getElementById('batch-field');
    const updateSuggestions = () => {
        const field = fieldSelect.value;
        const datalist = document.getElementById('batch-suggestions');
        datalist.innerHTML = '';
        if (field === 'operator') {
            metadata.operators.forEach(o => {
                const opt = document.createElement('option');
                opt.value = o;
                datalist.appendChild(opt);
            });
        } else if (field === 'label') {
            metadata.labels.forEach(n => {
                const opt = document.createElement('option');
                opt.value = n;
                datalist.appendChild(opt);
            });
        }
    };
    fieldSelect.onchange = updateSuggestions;
    updateSuggestions();
}

function closeBatchEdit() {
    document.getElementById('batch-edit-modal').classList.remove('show');
}

async function submitBatchEdit() {
    const checked = document.querySelectorAll('.row-cb:checked');
    const ids = Array.from(checked).map(cb => cb.dataset.id);
    const field = document.getElementById('batch-field').value;
    let value = document.getElementById('batch-value').value;

    if (!value && !confirm('Are you sure you want to set this field to empty?')) return;

    // Convert to number if it's a numeric field
    const numericFields = ['day_p1', 'day_p1us', 'day_p2', 'day_dual', 'night_p1', 'night_p1us', 'night_p2', 'night_dual', 'inst_flying', 'sim_time'];
    if (numericFields.includes(field)) {
        value = parseFloat(value) || 0;
    }

    const token = getToken();
    try {
        const response = await fetch('/api/entries/batch-edit', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                ids,
                updates: { [field]: value }
            })
        });

        if (response.ok) {
            showToast(`${ids.length} entries updated`);
            closeBatchEdit();
            clearSelection();
            fetchHistory();
        } else {
            const errorData = await response.json().catch(() => ({}));
            const msg = errorData.detail || 'Unknown server error';
            showToast(`Batch update failed: ${msg}`, 'error');
        }
    } catch (error) {
        showToast(`Server error: ${error.message}`, 'error');
    }
}
