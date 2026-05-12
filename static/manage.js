let allHistory = [];
let currentFilteredHistory = [];
let selectedEntryId = null;

document.addEventListener('DOMContentLoaded', () => {
    fetchHistory();
    setupOpeningTotalsInputs();
    setupContextMenu();
    fetchSynonyms();
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
        populateFilters();
        
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
        
        if (response.status === 401) {
            showToast('Session expired. Please login again.', 'error');
            return;
        }
        
        if (!response.ok) {
            const err = await response.json().catch(() => ({ detail: 'Server Error' }));
            throw new Error(err.detail || 'Failed to fetch history');
        }

        const data = await response.json();
        allHistory = data.history;
        await fetchMetadata();
        populateFilters();
        filterHistory();
    } catch (error) {
        console.error('Error fetching history:', error);
        showToast(`Error loading history: ${error.message}`, 'error');
    }
}

function renderHistory(history) {
    const body = document.getElementById('history-body');
    body.innerHTML = '';

    history.forEach(entry => {
        const row = document.createElement('tr');
        row.id = `row-${entry.id}`;
        row.dataset.id = entry.id;
        
        let displayDate = '---';
        if (entry.is_adjustment) {
            displayDate = 'ADJUST';
        } else if (entry.date_obj) {
            const d = new Date(entry.date_obj);
            if (!isNaN(d)) {
                const day = String(d.getDate()).padStart(2, '0');
                const month = String(d.getMonth() + 1).padStart(2, '0');
                const year = String(d.getFullYear()).slice(-2);
                displayDate = `${day}/${month}/${year}`;
            }
        } else if (entry.date_str) {
            displayDate = entry.date_str; // Fallback
        }

        row.addEventListener('contextmenu', e => {
            e.preventDefault();
            e.stopPropagation(); // Stop from bubbling up to document click
            showContextMenu(e, entry.id);
        });

        row.innerHTML = `
            <td><input type="checkbox" class="select-cb row-cb" data-id="${entry.id}" onchange="updateBatchBar()"></td>
            <td>${displayDate}</td>
            <td>${entry.ac_type || '---'}</td>
            <td>${entry.reg || '---'}</td>
            <td class="route-cell" title="${entry.pic || ''}">${entry.pic || '---'}</td>
            <td class="route-cell" title="${entry.copilot || ''}">${entry.copilot || '---'}</td>
            <td class="route-cell" title="${entry.route || ''}">${entry.route || '---'}</td>
            <td style="text-align: center; color: var(--accent-color); font-weight: 600;">${entry.takeoff || 0}</td>
            <td style="text-align: center; color: var(--accent-color); font-weight: 600;">${entry.landing || 0}</td>
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
        `;
        body.appendChild(row);
    });

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

    if (!yearSelect || !typeSelect) return;

    const currentYear = yearSelect.value;
    const currentType = typeSelect.value;

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

    if (Array.from(years).some(y => y.toString() === currentYear)) yearSelect.value = currentYear;
    if (Array.from(types).some(t => t === currentType)) typeSelect.value = currentType;

    const operatorSelect = document.getElementById('filter-operator');
    const labelSelect = document.getElementById('filter-label');
    
    if (operatorSelect && labelSelect) {
        const currentOperator = operatorSelect.value;
        const currentLabel = labelSelect.value;

        operatorSelect.innerHTML = '<option value="ALL">All Operators</option>';
        labelSelect.innerHTML = '<option value="ALL">All Labels</option>';

        const operators = new Set(metadata.operators);
        const labels = new Set(metadata.labels);

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
    const queryEl = document.getElementById('history-search');
    const yearEl = document.getElementById('filter-year');
    const monthEl = document.getElementById('filter-month');
    const typeEl = document.getElementById('filter-type');
    const operatorEl = document.getElementById('filter-operator');
    const labelEl = document.getElementById('filter-label');
    const dateFromEl = document.getElementById('filter-date-from');
    const dateToEl = document.getElementById('filter-date-to');

    const query = queryEl ? queryEl.value.toLowerCase() : '';
    const filterYear = yearEl ? yearEl.value : 'ALL';
    const filterMonth = monthEl ? monthEl.value : 'ALL';
    const filterType = typeEl ? typeEl.value : 'ALL';
    const filterOperator = operatorEl ? operatorEl.value : 'ALL';
    const filterLabel = labelEl ? labelEl.value : 'ALL';
    const dateFrom = dateFromEl ? dateFromEl.value : '';
    const dateTo = dateToEl ? dateToEl.value : '';

    const filtered = allHistory.filter(entry => {
        const matchesQuery = !query || 
               (entry.date_str && entry.date_str.toLowerCase().includes(query)) ||
               (entry.ac_type && entry.ac_type.toLowerCase().includes(query)) ||
               (entry.reg && entry.reg.toLowerCase().includes(query)) ||
               (entry.route && entry.route.toLowerCase().includes(query)) ||
               (entry.remarks && entry.remarks.toLowerCase().includes(query));

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

        let matchesYear = true;
        if (filterYear !== 'ALL' && entry.date_obj) {
            const year = new Date(entry.date_obj).getFullYear();
            matchesYear = year.toString() === filterYear;
        }

        let matchesMonth = true;
        if (filterMonth !== 'ALL' && entry.date_obj) {
            const month = new Date(entry.date_obj).getMonth();
            matchesMonth = month.toString() === filterMonth;
        }

        let matchesType = true;
        if (filterType !== 'ALL') matchesType = entry.ac_type === filterType;

        let matchesOperator = true;
        if (filterOperator !== 'ALL') matchesOperator = entry.operator === filterOperator;

        let matchesLabel = true;
        if (filterLabel !== 'ALL') matchesLabel = entry.label === filterLabel;

        return matchesQuery && matchesDateRange && matchesYear && matchesMonth && matchesType && matchesOperator && matchesLabel;
    });
    currentFilteredHistory = filtered;
    renderHistory(filtered);
}

function exportToExcel() {
    if (!currentFilteredHistory || currentFilteredHistory.length === 0) {
        showToast("No data to export", "warning");
        return;
    }

    const data = currentFilteredHistory.map(e => {
        const row = {
            "Date": e.date_obj ? e.date_obj.split('T')[0] : e.date_str,
            "Aircraft Type": e.ac_type || "",
            "Registration": e.reg || "",
            "PIC": e.pic || "",
            "Co-Pilot": e.copilot || "",
            "Route": e.route || "",
            "Day P1": e.day_p1 || 0,
            "Day P1(U/S)": e.day_p1us || 0,
            "Day P2": e.day_p2 || 0,
            "Day P/UT": e.day_dual || 0,
            "Night P1": e.night_p1 || 0,
            "Night P1(U/S)": e.night_p1us || 0,
            "Night P2": e.night_p2 || 0,
            "Night P/UT": e.night_dual || 0,
            "IF": e.inst_flying || 0,
            "Sim": e.sim_time || 0,
            "Operator": e.operator || "",
            "Label": e.label || "",
            "Flight ID": e.flight_id || "",
            "Dep Time": e.dep_time || "",
            "Arr Time": e.arr_time || "",
            "Remarks": e.remarks || ""
        };

        // Add metadata columns with synonym protection
        if (e.metadata) {
            const standardSynonyms = [
                'REG', 'REGISTRATION', 'AC REG', 'A/C REG', 'AIRCRAFT REG',
                'FLIGHT ID', 'FLIGHT SN', 'FLT_SN', 'FLT S/N',
                'DATE', 'TIME', 'TYPE', 'MODEL', 'PIC', 'CAPTAIN', 'CO-PILOT', 'COPILOT',
                'ROUTE', 'REMARKS', 'OPERATOR', 'LABEL', 'TOTAL', 'DURATION'
            ];

            Object.entries(e.metadata).forEach(([key, val]) => {
                const keyUpper = key.toUpperCase().trim();
                
                // 1. Check if key is in our explicit standard synonym list
                if (standardSynonyms.includes(keyUpper)) return;

                // 2. Check if any existing row key (uppercase) matches this metadata key (uppercase)
                const exists = Object.keys(row).some(rk => rk.toUpperCase().trim() === keyUpper);
                
                if (!exists) {
                    row[key] = val;
                }
            });
        }
        return row;
    });

    // Collect ALL unique keys from all rows to ensure headers are complete
    const allKeys = [];
    data.forEach(row => {
        Object.keys(row).forEach(key => {
            if (!allKeys.includes(key)) {
                allKeys.push(key);
            }
        });
    });

    const worksheet = XLSX.utils.json_to_sheet(data, { header: allKeys });
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Flight Log");

    // Auto-size columns
    worksheet["!cols"] = allKeys.map(k => ({ wch: Math.max(k.length + 5, 12) }));

    const fileName = `Logbook_Export_${new Date().toISOString().split('T')[0]}.xlsx`;
    XLSX.writeFile(workbook, fileName);
    showToast(`Exported ${data.length} flights to Excel`);
}

// --- Context Menu Logic ---
function setupContextMenu() {
    const menu = document.getElementById('context-menu');
    
    document.addEventListener('click', () => {
        menu.style.display = 'none';
        document.querySelectorAll('tr.selected').forEach(r => r.classList.remove('selected'));
    });

    const editBtn = document.getElementById('ctx-edit');
    const deleteBtn = document.getElementById('ctx-delete');
    
    if (editBtn) editBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        openFlightDetailModal(selectedEntryId);
    };
    if (deleteBtn) deleteBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        deleteEntry(selectedEntryId);
    };
}

function showContextMenu(e, id) {
    selectedEntryId = id;
    const menu = document.getElementById('context-menu');
    
    // Highlight row
    document.querySelectorAll('tr.selected').forEach(r => r.classList.remove('selected'));
    document.getElementById(`row-${id}`).classList.add('selected');

    menu.style.display = 'block';
    menu.style.left = `${e.pageX}px`;
    menu.style.top = `${e.pageY}px`;
}

// --- Advanced Detail Modal (JSON Interface) ---
function openFlightDetailModal(id) {
    const entry = allHistory.find(e => e.id === id);
    if (!entry) return;

    document.getElementById('detail-flight-index').value = id;
    
    // Basic Data
    document.getElementById('detail-date').value = entry.date_obj ? entry.date_obj.split('T')[0] : '';
    document.getElementById('detail-type').value = entry.ac_type || '';
    document.getElementById('detail-reg').value = entry.reg || '';
    document.getElementById('detail-route').value = entry.route || '';
    document.getElementById('detail-pic').value = entry.pic || '';
    document.getElementById('detail-copilot').value = entry.copilot || '';
    
    // Metadata/Hidden Fields
    document.getElementById('detail-flight-id').value = entry.flight_id || '';
    document.getElementById('detail-dep-time').value = entry.dep_time || '';
    document.getElementById('detail-arr-time').value = entry.arr_time || '';
    document.getElementById('detail-takeoff').value = entry.takeoff || 0;
    document.getElementById('detail-landing').value = entry.landing || 0;
    document.getElementById('detail-nature').value = entry.remarks || ''; // Map nature to remarks for manual

    // Hours
    document.getElementById('detail-day-p1').value = entry.day_p1 || '0.0';
    document.getElementById('detail-day-p1us').value = entry.day_p1us || '0.0';
    document.getElementById('detail-day-p2').value = entry.day_p2 || '0.0';
    document.getElementById('detail-day-put').value = entry.day_dual || '0.0';
    document.getElementById('detail-night-p1').value = entry.night_p1 || '0.0';
    document.getElementById('detail-night-p1us').value = entry.night_p1us || '0.0';
    document.getElementById('detail-night-p2').value = entry.night_p2 || '0.0';
    document.getElementById('detail-night-put').value = entry.night_dual || '0.0';
    document.getElementById('detail-inst').value = entry.inst_flying || '0.0';
    document.getElementById('detail-sim').value = entry.sim_time || '0.0';

    document.getElementById('detail-operator').value = entry.operator || '';
    document.getElementById('detail-label').value = entry.label || '';

    // Handle Metadata (Raw Excel Columns)
    const metaContainer = document.getElementById('detail-metadata-container');
    if (metaContainer) {
        metaContainer.innerHTML = '';
        if (entry.metadata && Object.keys(entry.metadata).length > 0) {
            Object.entries(entry.metadata).forEach(([key, val]) => {
                const group = document.createElement('div');
                group.className = 'detail-group';
                group.innerHTML = `<label style="color:var(--accent-color); opacity: 0.7;">${key}</label><div style="padding: 0.4rem; background: rgba(255,255,255,0.03); border-radius: 4px; border: 1px solid rgba(255,255,255,0.05); color: #ccc; word-break: break-all; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem;">${val}</div>`;
                metaContainer.appendChild(group);
            });
        } else {
            metaContainer.innerHTML = '<p class="text-muted" style="grid-column: 1/-1; font-size: 0.8rem;">No additional metadata available for this entry.</p>';
        }
    }

    document.getElementById('flight-detail-modal').classList.add('show');
}

function closeFlightDetailModal() {
    document.getElementById('flight-detail-modal').classList.remove('show');
}

async function handleFlightDetailSubmit(event) {
    event.preventDefault();
    const id = document.getElementById('detail-flight-index').value;
    const token = getToken();

    const payload = {
        date_str: document.getElementById('detail-date').value,
        ac_type: document.getElementById('detail-type').value,
        reg: document.getElementById('detail-reg').value,
        route: document.getElementById('detail-route').value,
        pic: document.getElementById('detail-pic').value,
        copilot: document.getElementById('detail-copilot').value,
        flight_id: document.getElementById('detail-flight-id').value,
        dep_time: document.getElementById('detail-dep-time').value,
        arr_time: document.getElementById('detail-arr-time').value,
        remarks: document.getElementById('detail-nature').value,
        day_p1: parseFloat(document.getElementById('detail-day-p1').value) || 0,
        day_p1us: parseFloat(document.getElementById('detail-day-p1us').value) || 0,
        day_p2: parseFloat(document.getElementById('detail-day-p2').value) || 0,
        day_dual: parseFloat(document.getElementById('detail-day-put').value) || 0,
        night_p1: parseFloat(document.getElementById('detail-night-p1').value) || 0,
        night_p1us: parseFloat(document.getElementById('detail-night-p1us').value) || 0,
        night_p2: parseFloat(document.getElementById('detail-night-p2').value) || 0,
        night_dual: parseFloat(document.getElementById('detail-night-put').value) || 0,
        inst_flying: parseFloat(document.getElementById('detail-inst').value) || 0,
        sim_time: parseFloat(document.getElementById('detail-sim').value) || 0,
        takeoff: parseInt(document.getElementById('detail-takeoff').value) || 0,
        landing: parseInt(document.getElementById('detail-landing').value) || 0,
        operator: document.getElementById('detail-operator').value,
        label: document.getElementById('detail-label').value
    };

    try {
        const response = await fetch(`/api/entry/${id}`, {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        if (response.ok) {
            showToast('Flight data updated');
            closeFlightDetailModal();
            fetchHistory();
        } else {
            showToast('Update failed', 'error');
        }
    } catch (e) {
        showToast('Server error', 'error');
    }
}

// --- Other helpers ---
function toggleSelectAll(masterCb) {
    document.querySelectorAll('.row-cb').forEach(cb => cb.checked = masterCb.checked);
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

function showConfirmModal(title, message, actionText, onConfirm) {
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    const btn = document.getElementById('confirm-btn-action');
    btn.textContent = actionText;
    btn.onclick = () => {
        onConfirm();
        closeConfirmModal();
    };
    document.getElementById('confirm-modal').classList.add('show');
}

function closeConfirmModal() {
    document.getElementById('confirm-modal').classList.remove('show');
}

async function deleteEntry(id) {
    if (!id) return;
    showConfirmModal(
        'Delete Entry?', 
        'Are you sure you want to delete this flight? This cannot be undone.',
        'Delete',
        async () => {
            const token = getToken();
            try {
                const response = await fetch(`/api/entry/${id}`, {
                    method: 'DELETE',
                    headers: { 'Authorization': `Bearer ${token}` }
                });
                if (response.ok) {
                    showToast('Entry deleted');
                    fetchHistory();
                } else {
                    showToast('Delete failed', 'error');
                }
            } catch (e) { showToast('Server error', 'error'); }
        }
    );
}

async function batchDelete() {
    const checked = document.querySelectorAll('.row-cb:checked');
    const ids = Array.from(checked).map(cb => cb.dataset.id);
    if (ids.length === 0) return;
    
    showConfirmModal(
        'Batch Delete?', 
        `Delete ${ids.length} selected entries? This cannot be undone.`,
        'Delete All',
        async () => {
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
                }
            } catch (e) { showToast('Server error', 'error'); }
        }
    );
}

function openBatchEdit() {
    const checked = document.querySelectorAll('.row-cb:checked');
    if (checked.length === 0) return;
    document.getElementById('batch-edit-info').textContent = `Editing ${checked.length} entries`;
    document.getElementById('batch-edit-modal').classList.add('show');
}

function closeBatchEdit() {
    document.getElementById('batch-edit-modal').classList.remove('show');
}

async function submitBatchEdit() {
    const checked = document.querySelectorAll('.row-cb:checked');
    const ids = Array.from(checked).map(cb => cb.dataset.id);
    const field = document.getElementById('batch-field').value;
    const value = document.getElementById('batch-value').value;
    const token = getToken();

    try {
        const response = await fetch('/api/entries/batch-edit', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ ids, updates: { [field]: value } })
        });
        if (response.ok) {
            showToast('Batch updated');
            closeBatchEdit();
            clearSelection();
            fetchHistory();
        }
    } catch (e) { showToast('Server error', 'error'); }
}

async function handleOpeningTotalsSubmit(event) {
    event.preventDefault();
    const token = getToken();
    const payload = {
        year: parseInt(document.getElementById('open-year').value),
        ac_type: document.getElementById('open-ac-type').value,
        day_p1: parseFloat(document.getElementById('open-day-p1').value) || 0,
        day_p1us: parseFloat(document.getElementById('open-day-p1us').value) || 0,
        day_p2: parseFloat(document.getElementById('open-day-p2').value) || 0,
        day_put: parseFloat(document.getElementById('open-day-put').value) || 0,
        night_p1: parseFloat(document.getElementById('open-night-p1').value) || 0,
        night_p1us: parseFloat(document.getElementById('open-night-p1us').value) || 0,
        night_p2: parseFloat(document.getElementById('open-night-p2').value) || 0,
        night_put: parseFloat(document.getElementById('open-night-put').value) || 0,
        inst: parseFloat(document.getElementById('open-inst').value) || 0,
        sim: parseFloat(document.getElementById('open-sim-day').value) || 0 + parseFloat(document.getElementById('open-sim-night').value) || 0,
        operator: document.getElementById('open-operator').value,
        label: document.getElementById('open-remarks').value
    };

    try {
        const response = await fetch('/api/opening_totals', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (response.ok) {
            showToast('Opening totals added');
            fetchHistory();
        }
    } catch (e) { showToast('Server error', 'error'); }
}
async function fetchSynonyms() {
    const token = getToken();
    const tbody = document.getElementById('synonym-table-body');
    if (!tbody) return;

    try {
        const response = await fetch('/api/synonyms', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (response.ok) {
            const data = await response.json();
            tbody.innerHTML = '';
            Object.entries(data).forEach(([key, synonyms]) => {
                const row = document.createElement('tr');
                row.style.borderBottom = '1px solid rgba(255,255,255,0.05)';
                row.innerHTML = `
                    <td style="padding: 1rem; color: #fff; font-weight: 500; background: rgba(255,255,255,0.01);">
                        <div style="display: flex; align-items: center; gap: 0.5rem;">
                            <span style="width: 8px; height: 8px; border-radius: 50%; background: var(--accent-color); opacity: 0.6;"></span>
                            ${key.replace('_', ' ')}
                        </div>
                    </td>
                    <td style="padding: 0.5rem 1rem;">
                        <input type="text" data-key="${key}" class="synonym-input" 
                            style="width: 100%; background: transparent; border: 1px solid transparent; color: var(--text-muted); padding: 0.5rem; border-radius: 4px; transition: all 0.2s;"
                            onfocus="this.style.border='1px solid var(--accent-color)'; this.style.background='rgba(255,255,255,0.03)'; this.style.color='#fff';"
                            onblur="this.style.border='1px solid transparent'; this.style.background='transparent'; this.style.color='var(--text-muted)';"
                            value="${synonyms.join(', ')}">
                    </td>
                `;
                tbody.appendChild(row);
            });
        }
    } catch (e) { console.error('Failed to fetch synonyms', e); }
}

async function saveSynonyms() {
    const token = getToken();
    const inputs = document.querySelectorAll('.synonym-input');
    const newMap = {};

    inputs.forEach(input => {
        const key = input.dataset.key;
        const synonyms = input.value.split(',').map(s => s.trim()).filter(s => s !== '');
        newMap[key] = synonyms;
    });

    try {
        const response = await fetch('/api/synonyms', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(newMap)
        });
        if (response.ok) {
            showToast('Excel mapping updated');
        } else {
            showToast('Update failed', 'error');
        }
    } catch (e) { showToast('Server error', 'error'); }
}
async function handleRestoreLogbook(input) {
    if (!input.files || input.files.length === 0) return;
    
    const file = input.files[0];
    const token = getToken();
    const formData = new FormData();
    formData.append('file', file);
    
    showConfirmModal(
        'Restore Logbook?',
        `This will REPLACE your current logbook with data from ${file.name}. Are you sure?`,
        'Restore',
        async () => {
            try {
                const response = await fetch('/api/restore', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` },
                    body: formData
                });
                
                if (response.ok) {
                    showToast('Logbook restored successfully!');
                    fetchHistory();
                } else {
                    const err = await response.json();
                    showToast(`Restore failed: ${err.detail}`, 'error');
                }
            } catch (e) {
                showToast('Server error during restore', 'error');
            } finally {
                input.value = '';
            }
        }
    );
}

async function exportLogbookJSON() {
    const token = getToken();
    try {
        const response = await fetch('/api/export_json', {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `logbook_backup_${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            showToast('JSON backup downloaded');
        } else {
            showToast('Export failed', 'error');
        }
    } catch (e) {
        showToast('Server error during export', 'error');
    }
}

async function handleAiMapping() {
    const input = document.getElementById('ai-mapping-input');
    const instruction = input.value.trim();
    if (!instruction) {
        showToast('Please type an instruction for the AI', true);
        return;
    }
    
    showToast('AI is updating your mappings...');
    try {
        const response = await apiFetch('/api/synonyms/ai', {
            method: 'POST',
            body: JSON.stringify({ instruction })
        });
        
        const result = await response.json();
        if (response.ok) {
            showToast(result.message);
            input.value = '';
            // Show summary
            const summary = document.getElementById('mapping-summary');
            summary.style.display = 'block';
            summary.textContent = `Updated keys: ${result.updated_keys.join(', ')}. Your Excel imports will now use these new rules.`;
        } else {
            showToast(result.detail || 'AI mapping failed', true);
        }
    } catch (e) {
        showToast('Server error during AI mapping', true);
    }
}

// Initial loads
document.addEventListener('DOMContentLoaded', () => {
    fetchHistory();
    fetchSyncAdjustments();
});

// --- Mobile Filter Drawer Logic ---
function openFilterModal() {
    const modal = document.getElementById('filter-modal');
    const container = document.getElementById('mobile-filter-container');
    const selectGroup = document.querySelector('.select-group');
    const dateRange = document.querySelector('.date-range');
    
    if (modal && container && selectGroup && dateRange) {
        // Move original filter elements into modal
        container.innerHTML = '';
        container.appendChild(selectGroup);
        container.appendChild(dateRange);
        modal.classList.add('show');
    }
}

function closeFilterModal() {
    const modal = document.getElementById('filter-modal');
    if (modal) modal.classList.remove('show');
}

function syncSearchAndFilter(input) {
    const mainSearch = document.getElementById('history-search');
    if (mainSearch) {
        mainSearch.value = input.value;
        filterHistory();
    }
}

function resetFilters() {
    const selects = document.querySelectorAll('.select-group select');
    selects.forEach(s => s.value = 'ALL');
    const dates = document.querySelectorAll('.date-range input');
    dates.forEach(d => d.value = '');
    const search = document.getElementById('history-search');
    const searchMobile = document.getElementById('history-search-mobile');
    if (search) search.value = '';
    if (searchMobile) searchMobile.value = '';
    filterHistory();
}
