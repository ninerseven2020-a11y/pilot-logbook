const AUTH_TOKEN_KEY = 'logbook_auth_token';

function getToken() {
    return localStorage.getItem(AUTH_TOKEN_KEY);
}

function setToken(token) {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
}

function removeToken() {
    localStorage.removeItem(AUTH_TOKEN_KEY);
}

const EYE_OPEN_SVG = `<svg viewBox="0 0 24 24"><path d="M12 4.5C7 4.5 2.73 7.61 1 12c1.73 4.39 6 7.5 11 7.5s9.27-3.11 11-7.5c-1.73-4.39-6-7.5-11-7.5zM12 17c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>`;
const EYE_CLOSED_SVG = `<svg viewBox="0 0 24 24"><path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>`;

function togglePassword(inputId, button) {
    const input = document.getElementById(inputId);
    if (input.type === "password") {
        input.type = "text";
        button.innerHTML = EYE_CLOSED_SVG;
    } else {
        input.type = "password";
        button.innerHTML = EYE_OPEN_SVG;
    }
}

async function apiFetch(url, options = {}) {
    const token = getToken();
    const headers = {
        ...options.headers,
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { ...options, headers });
    
    if (response.status === 401) {
        // Unauthorized, clear token and redirect to login
        removeToken();
        const path = window.location.pathname;
        if (path !== '/login' && path !== '/register') {
            window.location.href = '/login';
        }
    }
    return response;
}

async function init() {
    const path = window.location.pathname.replace(/\/$/, ""); // Remove trailing slash for comparison
    const token = getToken();
    
    console.log(`[Init] Path: ${path}, Token Present: ${!!token}`);

    // Redirect to login if no token and not on auth pages
    if (!token && path !== '/login' && path !== '/register') {
        console.log("[Init] No token, redirecting to login");
        window.location.href = '/login';
        return;
    }

    // Redirect to dashboard if has token and on auth pages
    if (token && (path === '/login' || path === '/register' || path === '' || path === '/')) {
        console.log("[Init] Token present on auth page, redirecting to dashboard");
        window.location.href = '/dashboard';
        return;
    }

    const page = document.body.dataset.page;
    if (page === 'dashboard') {
        await fetchUser();
        await fetchDashboard();
        await fetchSyncAdjustments();
        checkGuide();
        setupEventListeners();
    } else if (page === 'preview') {
        await fetchUser();
        await fetchPreview();
        await fetchSyncAdjustments();
        setupEventListeners();
    } else if (page === 'upload') {
        await fetchUser();
        await fetchUploadMetadata();
        setupManualInputLogic();
        setupSmartDecimalInputs();
    } else if (page === 'manage') {
        await fetchUser();
    }
}

async function fetchDashboard() {
    try {
        // Fetch metadata first to have all labels for filters
        const metaResponse = await apiFetch('/api/upload_metadata');
        if (metaResponse.ok) {
            window._metadata = await metaResponse.json();
        }

        const response = await apiFetch(`/api/dashboard`);
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error("Error fetching dashboard:", error);
    }
}

function toggleTypeFilter(type) {
    let currentFilters = ['ALL'];
    try {
        const stored = localStorage.getItem('ac_type_filter');
        if (stored) {
            const parsed = JSON.parse(stored);
            if (Array.isArray(parsed)) currentFilters = parsed;
        }
    } catch(e) {}

    if (type === 'ALL') {
        currentFilters = ['ALL'];
    } else {
        currentFilters = currentFilters.filter(f => f !== 'ALL');
        if (currentFilters.includes(type)) {
            currentFilters = currentFilters.filter(f => f !== type);
        } else {
            currentFilters.push(type);
        }
        if (currentFilters.length === 0) {
            currentFilters = ['ALL'];
        }
    }

    localStorage.setItem('ac_type_filter', JSON.stringify(currentFilters));
    
    // Re-render type breakdown
    if (window._lastDashboardData) {
        renderTypeBreakdown(window._lastDashboardData.type_breakdown || [], window._lastDashboardData.full_history || []);
    }
}

function setLabelFilter(label) {
    const current = localStorage.getItem('label_filter') || '';
    const newLabel = current === label ? '' : label;
    localStorage.setItem('label_filter', newLabel);
    
    // Re-render type breakdown only (no server call)
    if (window._lastDashboardData) {
        renderTypeBreakdown(window._lastDashboardData.type_breakdown || [], window._lastDashboardData.full_history || []);
    }
    
    // Sync label button UI
    document.querySelectorAll('.label-btn-dynamic').forEach(btn => {
        btn.classList.toggle('active', btn.textContent === newLabel);
    });
}

function updateDashboard(data) {
    const breakdown = data.type_breakdown || [];
    const history = data.full_history || [];

    // Store for client-side re-filtering
    window._lastDashboardData = data;

    // Populate label filter buttons
    const labels = new Set();
    history.forEach(entry => {
        if (entry.label && entry.label.trim()) {
            labels.add(entry.label.trim());
        }
    });

    // Also include labels from metadata if available
    if (window._metadata && window._metadata.labels) {
        window._metadata.labels.forEach(l => labels.add(l));
    }
    
    const container = document.getElementById('breakdown-filters');
    const divider = document.getElementById('label-divider');
    if (container && divider) {
        container.querySelectorAll('.label-btn-dynamic').forEach(b => b.remove());
        
        const activeLabel = localStorage.getItem('label_filter') || '';
        Array.from(labels).sort().forEach(label => {
            const btn = document.createElement('button');
            btn.className = 'filter-btn label-btn-dynamic' + (activeLabel === label ? ' active' : '');
            btn.textContent = label;
            btn.onclick = () => setLabelFilter(label);
            container.insertBefore(btn, divider);
        });
        divider.style.display = labels.size > 0 ? '' : 'none';
    }

    // Render period breakdown
    renderPeriodBreakdown(history);

    // Render type breakdown
    renderTypeBreakdown(breakdown, history);

    // Sync filter buttons
    const category = localStorage.getItem('ac_category_filter') || 'ALL';
    document.querySelectorAll('[data-category]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.category === category);
    });
    const period = localStorage.getItem('period_filter') || 'YTD';
    document.querySelectorAll('[data-period]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.period === period);
    });
}

function getPeriodStartDate(period) {
    const now = new Date();
    switch (period) {
        case 'ALL': return null;
        case '1Y':  return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
        case 'YTD': return new Date(now.getFullYear(), 0, 1);
        case '3M':  return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
        case '1M':  return new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
        case 'MTD': return new Date(now.getFullYear(), now.getMonth(), 1);
        case '1W':  return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
        default:    return new Date(now.getFullYear(), 0, 1);
    }
}

function renderPeriodBreakdown(history) {
    const period = localStorage.getItem('period_filter') || 'YTD';
    const startDate = getPeriodStartDate(period);

    // Filter history by period
    const filtered = startDate ? history.filter(e => {
        const d = new Date(e.date_obj);
        return d >= startDate;
    }) : history;

    // Sum columns
    const cols = ['day_p1','day_p1us','day_p2','day_dual','night_p1','night_p1us','night_p2','night_dual','inst_flying','sim_time'];
    const totals = {};
    cols.forEach(c => totals[c] = 0);
    filtered.forEach(e => { cols.forEach(c => totals[c] += (e[c] || 0)); });

    const grandTotal = totals.day_p1 + totals.day_p1us + totals.day_p2 + totals.day_dual
                     + totals.night_p1 + totals.night_p1us + totals.night_p2 + totals.night_dual;

    document.getElementById('total-hours').innerText = grandTotal.toFixed(1);

    const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val.toFixed(1); };
    setVal('cad-day-p1', totals.day_p1); setVal('cad-day-p1us', totals.day_p1us);
    setVal('cad-day-p2', totals.day_p2); setVal('cad-day-dual', totals.day_dual);
    setVal('cad-night-p1', totals.night_p1); setVal('cad-night-p1us', totals.night_p1us);
    setVal('cad-night-p2', totals.night_p2); setVal('cad-night-dual', totals.night_dual);
    setVal('cad-inst', totals.inst_flying); setVal('cad-sim', totals.sim_time);

    // Render chart
    renderHoursChart(filtered, period);
}

let hoursChartInstance = null;

let currentGranularity = 'M';

function setGranularity(gran) {
    currentGranularity = gran;
    document.querySelectorAll('.gran-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.gran === gran);
    });
    if (window._lastDashboardData) {
        renderPeriodBreakdown(window._lastDashboardData.full_history || []);
    }
}

function updateGranularityUI(period) {
    const controls = document.querySelectorAll('.gran-btn');
    if (!controls.length) return;

    let allowed = [];
    if (period === '1W') allowed = ['D'];
    else if (period === 'MTD') allowed = ['D', 'W'];
    else if (period === '1M') allowed = ['D', 'W'];
    else if (period === '3M') allowed = ['D', 'W', 'M'];
    else if (period === 'YTD') allowed = ['D', 'W', 'M'];
    else if (period === '1Y') allowed = ['D', 'W', 'M'];
    else if (period === 'ALL') allowed = ['Y', 'M', 'W'];

    controls.forEach(btn => {
        const gran = btn.dataset.gran;
        if (allowed.includes(gran)) {
            btn.style.display = 'inline-block';
        } else {
            btn.style.display = 'none';
        }
    });

    if (!allowed.includes(currentGranularity)) {
        if (period === '1W' || period === 'MTD') currentGranularity = 'D';
        else if (period === '1M' || period === '3M') currentGranularity = 'W';
        else if (period === 'ALL') currentGranularity = 'Y';
        else currentGranularity = 'M';
    }

    controls.forEach(btn => {
        btn.classList.toggle('active', btn.dataset.gran === currentGranularity);
    });
}

function renderHoursChart(entries, period) {
    const ctx = document.getElementById('hours-chart');
    if (!ctx) return;

    // 1. Calculate the starting cumulative total (Previous Experience + hours before this period)
    let startingCumulative = 0;
    const fullHistory = (window._lastDashboardData && window._lastDashboardData.full_history) || [];
    const startDate = getPeriodStartDate(period);

    fullHistory.forEach(e => {
        const isOpening = e.is_opening === true;
        const entryDate = new Date(e.date_obj);
        
        // If it's an opening balance, ALWAYS add it
        // OR if it's a flight BEFORE our current chart period, add it to start cumulative
        if (isOpening || (startDate && entryDate < startDate)) {
            const hrs = (e.day_p1||0)+(e.day_p1us||0)+(e.day_p2||0)+(e.day_dual||0)
                      +(e.night_p1||0)+(e.night_p1us||0)+(e.night_p2||0)+(e.night_dual||0);
            startingCumulative += hrs;
        }
    });

    // Also include sync adjustments that occurred before the period
    if (window._syncAdjustments) {
        window._syncAdjustments.forEach(adj => {
            const adjDate = new Date(adj.date);
            if (startDate && adjDate < startDate) {
                const off = adj.offsets || {};
                const hrs = (off.day_p1||0)+(off.day_p1us||0)+(off.day_p2||0)+(off.day_dual||0)
                          +(off.night_p1||0)+(off.night_p1us||0)+(off.night_p2||0)+(off.night_dual||0);
                startingCumulative += hrs;
            }
        });
    }

    // Sort entries by date and filter out previous experience (already added to startingCumulative)
    const sorted = [...entries]
        .filter(e => e.date_obj && !e.is_opening)
        .sort((a, b) => new Date(a.date_obj) - new Date(b.date_obj));

    if (sorted.length === 0) {
        if (hoursChartInstance) { hoursChartInstance.destroy(); hoursChartInstance = null; }
        return;
    }

    updateGranularityUI(period);

    // Group by date and compute daily totals
    const dailyMap = {};
    sorted.forEach(e => {
        const d = new Date(e.date_obj);
        const key = d.toISOString().split('T')[0];
        if (!dailyMap[key]) dailyMap[key] = 0;
        const hrs = (e.day_p1||0)+(e.day_p1us||0)+(e.day_p2||0)+(e.day_dual||0)
                  +(e.night_p1||0)+(e.night_p1us||0)+(e.night_p2||0)+(e.night_dual||0);
        dailyMap[key] += hrs;
    });

    // Determine bucket granularity
    const getBucketKey = (dateStr) => {
        const d = new Date(dateStr);
        if (currentGranularity === 'D') {
            return dateStr; // daily
        } else if (currentGranularity === 'W') {
            // Weekly: use Monday of that week
            const day = d.getDay();
            const diff = d.getDate() - day + (day === 0 ? -6 : 1);
            const monday = new Date(d.getFullYear(), d.getMonth(), diff);
            return monday.toISOString().split('T')[0];
        } else if (currentGranularity === 'M') {
            // Monthly
            return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
        } else if (currentGranularity === 'Y') {
            // Yearly
            return `${d.getFullYear()}`;
        }
    };

    const formatBucketLabel = (key) => {
        if (currentGranularity === 'D') {
            const d = new Date(key);
            return d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
        } else if (currentGranularity === 'W') {
            const d = new Date(key);
            return 'W/' + d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
        } else if (currentGranularity === 'M') {
            const [y, m] = key.split('-');
            const d = new Date(parseInt(y), parseInt(m)-1);
            return d.toLocaleDateString('en', { month: 'short', year: '2-digit' });
        } else if (currentGranularity === 'Y') {
            return key;
        }
    };

    // Aggregate into buckets
    const bucketMap = {};
    const allDays = Object.keys(dailyMap).sort();
    allDays.forEach(day => {
        const bk = getBucketKey(day);
        if (!bucketMap[bk]) bucketMap[bk] = 0;
        bucketMap[bk] += dailyMap[day];
    });

    // Fill gaps to ensure constant x-axis spacing across the full period
    let startD = getPeriodStartDate(period);
    let endD = new Date(); // today
    if (!startD) {
        startD = allDays.length > 0 ? new Date(allDays[0]) : new Date();
    }
    // If the latest flight is AFTER today (e.g. future flight), extend endD
    if (allDays.length > 0) {
        const lastFlight = new Date(allDays[allDays.length - 1]);
        if (lastFlight > endD) endD = lastFlight;
    }

    if (currentGranularity === 'D') {
        // Fill daily
        for (let d = new Date(startD); d <= endD; d.setDate(d.getDate() + 1)) {
            const key = d.toISOString().split('T')[0];
            if (!bucketMap[key]) bucketMap[key] = 0;
        }
    } else if (currentGranularity === 'W') {
        // Fill weekly
        const day = startD.getDay();
        const diff = startD.getDate() - day + (day === 0 ? -6 : 1);
        const firstMonday = new Date(startD.getFullYear(), startD.getMonth(), diff);
        for (let d = new Date(firstMonday); d <= endD; d.setDate(d.getDate() + 7)) {
            const key = d.toISOString().split('T')[0];
            if (!bucketMap[key]) bucketMap[key] = 0;
        }
    } else if (currentGranularity === 'M') {
        // Fill monthly
        for (let d = new Date(startD.getFullYear(), startD.getMonth(), 1); d <= endD; d.setMonth(d.getMonth() + 1)) {
            const key = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
            if (!bucketMap[key]) bucketMap[key] = 0;
        }
    } else if (currentGranularity === 'Y') {
        // Fill yearly
        for (let y = startD.getFullYear(); y <= endD.getFullYear(); y++) {
            const key = `${y}`;
            if (!bucketMap[key]) bucketMap[key] = 0;
        }
    }

    const buckets = Object.keys(bucketMap).sort();
    const labels = buckets.map(formatBucketLabel);
    const dailyValues = buckets.map(b => Math.round(bucketMap[b] * 10) / 10);

    // Build cumulative from buckets
    let cumulative = startingCumulative;
    const values = buckets.map(b => {
        cumulative += bucketMap[b];
        return Math.round(cumulative * 10) / 10;
    });

    // Accent color
    const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent-color').trim() || '#3b82f6';

    if (hoursChartInstance) {
        hoursChartInstance.destroy();
        hoursChartInstance = null;
    }

    hoursChartInstance = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Daily Hours',
                    data: dailyValues,
                    backgroundColor: 'rgba(250, 204, 21, 0.4)',
                    borderColor: 'rgba(250, 204, 21, 0.7)',
                    hoverBackgroundColor: 'rgba(250, 204, 21, 0.8)',
                    borderWidth: 1,
                    borderRadius: 3,
                    yAxisID: 'yDaily',
                    order: 2,
                },
                {
                    label: 'Cumulative Hours',
                    type: 'line',
                    data: values,
                    borderColor: '#818cf8',
                    backgroundColor: 'rgba(129, 140, 248, 0.1)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: buckets.length > 60 ? 0 : 3,
                    pointHoverRadius: 5,
                    pointBackgroundColor: '#818cf8',
                    borderWidth: 2,
                    yAxisID: 'yCumulative',
                    order: 1,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: 'nearest', intersect: true },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleColor: '#e2e8f0',
                    bodyColor: '#f8fafc',
                    borderColor: 'rgba(255,255,255,0.15)',
                    borderWidth: 1,
                    padding: 10,
                    callbacks: {
                        label: (item) => `${item.dataset.label}: ${item.parsed.y.toFixed(1)}`
                    }
                }
            },
            scales: {
                x: {
                    ticks: {
                        color: 'rgba(255,255,255,0.4)',
                        font: { size: 10 },
                        maxTicksLimit: 8,
                        maxRotation: 0,
                    },
                    grid: { display: false },
                    border: { display: false }
                },
                yDaily: {
                    position: 'left',
                    ticks: {
                        color: 'rgba(250, 204, 21, 0.6)',
                        font: { size: 10 },
                    },
                    grid: { display: false },
                    border: { display: false },
                    beginAtZero: true,
                },
                yCumulative: {
                    position: 'right',
                    ticks: {
                        color: 'rgba(129, 140, 248, 0.6)',
                        font: { size: 10 },
                    },
                    grid: { display: false },
                    border: { display: false },
                    beginAtZero: true,
                }
            }
        }
    });
}

function setPeriodFilter(period) {
    localStorage.setItem('period_filter', period);
    document.querySelectorAll('[data-period]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.period === period);
    });
    if (window._lastDashboardData) {
        renderPeriodBreakdown(window._lastDashboardData.full_history || []);
    }
}

function renderTypeBreakdown(breakdown, history, repopulateSelect = true) {
    let typeFilters = ['ALL'];
    try {
        const stored = localStorage.getItem('ac_type_filter');
        if (stored) {
            const parsed = JSON.parse(stored);
            if (Array.isArray(parsed)) typeFilters = parsed;
            else typeFilters = [stored]; // backwards compatibility
        }
    } catch(e) {
        typeFilters = [localStorage.getItem('ac_type_filter') || 'ALL'];
    }

    const labelFilter = localStorage.getItem('label_filter') || '';

    // If a label is selected, recompute breakdown from history filtered by label
    let data = breakdown;
    if (labelFilter && history && history.length > 0) {
        // Filter history by label, then group by ac_type
        const filtered = history.filter(e => e.label && e.label === labelFilter);
        const grouped = {};
        filtered.forEach(e => {
            const type = e.ac_type === 'SIM' ? 'EC175' : (e.ac_type || 'Unknown');
            if (!grouped[type]) grouped[type] = { ac_type: type, day_p1:0, day_p1us:0, day_p2:0, day_dual:0, night_p1:0, night_p1us:0, night_p2:0, night_dual:0, inst_flying:0, sim_time:0, ac_category: e.ac_category };
            const g = grouped[type];
            g.day_p1 += e.day_p1||0; g.day_p1us += e.day_p1us||0; g.day_p2 += e.day_p2||0; g.day_dual += e.day_dual||0;
            g.night_p1 += e.night_p1||0; g.night_p1us += e.night_p1us||0; g.night_p2 += e.night_p2||0; g.night_dual += e.night_dual||0;
            g.inst_flying += e.inst_flying||0; g.sim_time += e.sim_time||0;
        });
        data = Object.values(grouped);
    }

    // Populate type buttons
    const container = document.getElementById('breakdown-type-buttons');
    if (container && repopulateSelect) {
        container.innerHTML = '';
        
        // "ALL" button
        const allBtn = document.createElement('button');
        allBtn.className = 'filter-btn' + (typeFilters.includes('ALL') ? ' active' : '');
        allBtn.textContent = 'All Types';
        allBtn.onclick = () => toggleTypeFilter('ALL');
        container.appendChild(allBtn);

        const uniqueTypes = [...new Set(data.map(item => item.ac_type))].sort();
        uniqueTypes.forEach(t => {
            if (!t) return;
            const btn = document.createElement('button');
            btn.className = 'filter-btn' + (typeFilters.includes(t) && !typeFilters.includes('ALL') ? ' active' : '');
            btn.textContent = t;
            btn.onclick = () => toggleTypeFilter(t);
            container.appendChild(btn);
        });
    }

    // Type filter
    const finalFilters = typeFilters.length ? typeFilters : ['ALL'];
    const filtered = finalFilters.includes('ALL') ? data : data.filter(item => finalFilters.includes(item.ac_type));

    const tableBody = document.querySelector('#type-table tbody');
    tableBody.innerHTML = '';
    filtered.forEach(item => {
        const dP1 = item.day_p1 || 0, dP1us = item.day_p1us || 0;
        const dP2 = item.day_p2 || 0, dDual = item.day_dual || 0;
        const nP1 = item.night_p1 || 0, nP1us = item.night_p1us || 0;
        const nP2 = item.night_p2 || 0, nDual = item.night_dual || 0;
        const inst = item.inst_flying || 0, sim = item.sim_time || 0;
        const total = dP1 + dP1us + dP2 + dDual + nP1 + nP1us + nP2 + nDual;

        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><strong>${item.ac_type}</strong></td>
            <td>${dP1.toFixed(1)}</td>
            <td>${dP1us.toFixed(1)}</td>
            <td>${dP2.toFixed(1)}</td>
            <td>${dDual.toFixed(1)}</td>
            <td>${nP1.toFixed(1)}</td>
            <td>${nP1us.toFixed(1)}</td>
            <td>${nP2.toFixed(1)}</td>
            <td>${nDual.toFixed(1)}</td>
            <td>${inst.toFixed(1)}</td>
            <td>${sim.toFixed(1)}</td>
            <td class="total-cell">${total.toFixed(1)}</td>
        `;
        tableBody.appendChild(tr);
    });
}


let allPages = [];
window.allPages = allPages;
let currentPageIndex = 0;
window.currentPageIndex = currentPageIndex;

async function fetchPreview(retries = 3) {
    const tableBody = document.querySelector('#logbook-table tbody');
    if (tableBody && allPages.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="21" style="text-align: center; padding: 40px;">⏳ Loading your logbook data... (945 entries)</td></tr>';
    }

    let url = '/api/preview?page=1';
    const dateFrom = document.getElementById('filter-date-from')?.value;
    const dateTo = document.getElementById('filter-date-to')?.value;
    if (dateFrom && dateFrom !== "") url += `&date_from=${dateFrom}`;
    if (dateTo && dateTo !== "") url += `&date_to=${dateTo}`;

    try {
        // Fetch adjustments in parallel
        fetchSyncAdjustments();

        const response = await apiFetch(url);
        const data = await response.json();
        
        if (data.length === 0 && retries > 0) {
            console.log(`Preview empty, retrying... (${retries} left)`);
            setTimeout(() => fetchPreview(retries - 1), 1500);
            return;
        }

        allPages = data;
        if (allPages.length > 0) {
            // Default to last page
            currentPageIndex = allPages.length - 1;
            populatePageSelect();
            renderLogbookTable();
        } else {
            tableBody.innerHTML = '<tr><td colspan="21" style="text-align: center; padding: 40px;">ℹ️ No logbook data found. Please import an Excel file.</td></tr>';
        }
    } catch (error) {
        console.error("Error fetching preview:", error);
        if (tableBody) tableBody.innerHTML = '<tr><td colspan="21" style="text-align: center; color: #ef4444;">❌ Error loading logbook. Please refresh.</td></tr>';
    }
}

function applyDateFilter() {
    allPages = [];
    currentPageIndex = 0;
    fetchPreview(0);
}

function clearDateFilter() {
    if (document.getElementById('filter-date-from')) document.getElementById('filter-date-from').value = '';
    if (document.getElementById('filter-date-to')) document.getElementById('filter-date-to').value = '';
    applyDateFilter();
}

function populatePageSelect() {
    const select = document.getElementById('page-select');
    if (!select) return;
    select.innerHTML = '';
    allPages.forEach((page, index) => {
        const option = document.createElement('option');
        option.value = index;
        option.innerText = `Page ${page.page_number}`;
        select.appendChild(option);
    });
    select.value = currentPageIndex;
}

function firstPage() {
    if (allPages.length > 0) {
        currentPageIndex = 0;
        updateNavigation();
    }
}

function prevPage() {
    if (currentPageIndex > 0) {
        currentPageIndex--;
        updateNavigation();
    }
}

function nextPage() {
    if (currentPageIndex < allPages.length - 1) {
        currentPageIndex++;
        updateNavigation();
    }
}

function jumpToPage() {
    const select = document.getElementById('page-select');
    currentPageIndex = parseInt(select.value);
    renderLogbookTable();
}

function lastPage() {
    if (allPages.length > 0) {
        currentPageIndex = allPages.length - 1;
        updateNavigation();
    }
}

function updateNavigation() {
    const select = document.getElementById('page-select');
    if (select) select.value = currentPageIndex;
    
    const pageInfo = document.getElementById('page-info');
    if (pageInfo && allPages[currentPageIndex]) {
        pageInfo.innerText = `Page ${allPages[currentPageIndex].page_number}`;
    }
    
    renderLogbookTable();
}

function renderLogbookTable() {
    const tableBody = document.querySelector('#logbook-table tbody');
    tableBody.innerHTML = '';

    if (!allPages || allPages.length === 0) return;
    
    const pageData = allPages[currentPageIndex];
    const entries = pageData.entries;
    
    // Update header info
    const yearEl = document.getElementById('current-year');
    if (yearEl) yearEl.innerText = `Year / ${pageData.year || '----'}`;
    
    const pageNumEl = document.getElementById('page-number-display');
    if (pageNumEl) pageNumEl.innerText = `Page ${pageData.page_number}`;

    // Update footer info
    const grandTotalEl = document.getElementById('grand-total-display');
    if (grandTotalEl) {
        grandTotalEl.innerText = pageData.grand_total_1_8.toFixed(1);
    }

    // Helper for rounding/formatting
    const fmt = (val) => {
        if (val === undefined || val === null) return '';
        const num = parseFloat(val);
        return (num !== 0) ? num.toFixed(1) : '';
    };

    // 1. Add "Brought Forward" Row
    const bf = pageData.brought_forward || {};
    const bfTr = document.createElement('tr');
    bfTr.className = 'totals-row brought-forward';
    bfTr.innerHTML = `
        <td></td>
        <td></td>
        <td></td>
        <td></td>
        <td></td>
        <td></td>
        <td colspan="3" style="text-align: center; font-weight: 700;">Totals brought forward</td>
        <td></td>
        <td></td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(1)</span>${fmt(bf.day_p1)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(2)</span>${fmt(bf.day_p1us)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(3)</span>${fmt(bf.day_p2)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(4)</span>${fmt(bf.day_dual)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(5)</span>${fmt(bf.night_p1)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(6)</span>${fmt(bf.night_p1us)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(7)</span>${fmt(bf.night_p2)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(8)</span>${fmt(bf.night_dual)}</td>
        <td>${fmt(bf.inst_flying)}</td>
        <td>${fmt(bf.sim_time)}</td>
        <td></td>
    `;
    tableBody.appendChild(bfTr);

    // 2. Add Entries (exactly 18 lines)
    for (let i = 0; i < 18; i++) {
        const entry = entries[i] || {};
        const tr = document.createElement('tr');
        
        if (entry.is_monthly_total) {
            tr.className = 'monthly-total-row';
            tr.innerHTML = `
                <td colspan="11" style="text-align: left; padding-left: 20px;"><strong>${entry.date_str}</strong></td>
                <td>${fmt(entry.day_p1)}</td>
                <td>${fmt(entry.day_p1us)}</td>
                <td>${fmt(entry.day_p2)}</td>
                <td>${fmt(entry.day_dual)}</td>
                <td>${fmt(entry.night_p1)}</td>
                <td>${fmt(entry.night_p1us)}</td>
                <td>${fmt(entry.night_p2)}</td>
                <td>${fmt(entry.night_dual)}</td>
                <td>${fmt(entry.inst_flying)}</td>
                <td>${fmt(entry.sim_time)}</td>
                <td></td>
            `;
        } else {
            // Split route if possible, or handle GFS case
            let route = entry.route || '';
            let dep = '';
            let arr = '';
            if (entry.operator === 'GFS') {
                dep = 'VHHH';
                arr = 'VHHH';
            } else if (route.includes(' ')) {
                const parts = route.split(/\s+/);
                dep = parts[0];
                arr = parts[parts.length - 1];
            } else {
                dep = route;
            }

            tr.innerHTML = `
                <td>${entry.date_str || ''}</td>
                <td>${entry.ac_type || ''}</td>
                <td>${entry.reg || ''}</td>
                <td>${entry.pic || ''}</td>
                <td>${entry.copilot || ''}</td>
                <td>${entry.capacity || ''}</td>
                
                <td style="text-align: center;">${dep}</td>
                <td style="text-align: center; color: #64748b; font-weight: 500;">${entry.total_time_str || ''}</td>
                <td style="text-align: center;">${arr}</td>
                
                <td style="text-align: center;">${entry.takeoff || ''}</td>
                <td style="text-align: center;">${entry.landing || ''}</td>
                
                <td>${fmt(entry.day_p1)}</td>
                <td>${fmt(entry.day_p1us)}</td>
                <td>${fmt(entry.day_p2)}</td>
                <td>${fmt(entry.day_dual)}</td>
                <td>${fmt(entry.night_p1)}</td>
                <td>${fmt(entry.night_p1us)}</td>
                <td>${fmt(entry.night_p2)}</td>
                <td>${fmt(entry.night_dual)}</td>
                <td>${fmt(entry.inst_flying)}</td>
                <td>${fmt(entry.sim_time)}</td>
                <td><small>${entry.remarks || ''}</small></td>
            `;
        }
        tableBody.appendChild(tr);
    }

    // 3. Add "Carried Forward" Row
    const cf = pageData.carried_forward || {};
    const cfTr = document.createElement('tr');
    cfTr.className = 'totals-row carried-forward';
    cfTr.innerHTML = `
        <td></td>
        <td></td>
        <td></td>
        <td></td>
        <td></td>
        <td></td>
        <td colspan="3" style="text-align: center; font-weight: 700;">Totals carried forward</td>
        <td></td>
        <td></td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(1)</span>${fmt(cf.day_p1)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(2)</span>${fmt(cf.day_p1us)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(3)</span>${fmt(cf.day_p2)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(4)</span>${fmt(cf.day_dual)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(5)</span>${fmt(cf.night_p1)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(6)</span>${fmt(cf.night_p1us)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(7)</span>${fmt(cf.night_p2)}</td>
        <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.65rem; color:#64748b;">(8)</span>${fmt(cf.night_dual)}</td>
        <td>${fmt(cf.inst_flying)}</td>
        <td>${fmt(cf.sim_time)}</td>
        <td></td>
    `;
    tableBody.appendChild(cfTr);
    
    // 4. After rendering, adjust font sizes if text overflows
    setTimeout(adjustFontSizeForFit, 50);
}

/**
 * Adjusts the font size of table cells if their content overflows the fixed column width.
 */
function adjustFontSizeForFit() {
    const cells = document.querySelectorAll('.cad407-table td');
    cells.forEach(cell => {
        // Reset to original font size first (to handle re-renders)
        cell.style.fontSize = '';
        
        // Skip empty cells or those with wrapping (like Remarks)
        if (!cell.innerText.trim() || cell.style.whiteSpace === 'normal') return;
        
        // Calculate the maximum width allowed (including padding)
        const computedStyle = window.getComputedStyle(cell);
        const paddingLeft = parseFloat(computedStyle.paddingLeft);
        const paddingRight = parseFloat(computedStyle.paddingRight);
        const availableWidth = cell.clientWidth - paddingLeft - paddingRight;
        
        // Create a temporary span to measure the real text width accurately
        const span = document.createElement('span');
        span.style.visibility = 'hidden';
        span.style.position = 'absolute';
        span.style.whiteSpace = 'nowrap';
        span.style.font = computedStyle.font;
        span.innerText = cell.innerText;
        document.body.appendChild(span);
        
        let currentSize = parseFloat(computedStyle.fontSize);
        const minSize = 6.5; 
        
        let textWidth = span.offsetWidth;
        
        while (textWidth > availableWidth && currentSize > minSize) {
            currentSize -= 0.3;
            span.style.fontSize = currentSize + 'px';
            textWidth = span.offsetWidth;
            cell.style.fontSize = currentSize + 'px';
        }
        
        document.body.removeChild(span);
    });
}

function setupEventListeners() {
    const uploadEl = document.getElementById('excel-upload');
    if (uploadEl) {
        uploadEl.addEventListener('change', async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            const formData = new FormData();
            formData.append('file', file);

            showToast("Uploading and parsing...");
            try {
                const response = await apiFetch('/api/import', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                showToast(result.message);
                updateDashboard(result.data);
                fetchPreview();
            } catch (error) {
                showToast("Error importing Excel", true);
            }
        });
    }
}

async function handleLogin(event) {
    event.preventDefault();
    console.log("[Login] Attempting login...");
    const formData = new URLSearchParams();
    formData.append('username', document.getElementById('username').value);
    formData.append('password', document.getElementById('password').value);

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: formData
        });
        
        if (response.ok) {
            console.log("[Login] Success! Saving token and redirecting...");
            const data = await response.json();
            setToken(data.access_token);
            window.location.href = '/dashboard';
        } else {
            const error = await response.json();
            console.error("[Login] Failed:", error);
            showToast(error.detail || "Login failed", true);
        }
    } catch (error) {
        console.error("[Login] Error:", error);
        showToast("An error occurred during login", true);
    }
}

async function handleRegister(event) {
    event.preventDefault();
    const formData = new FormData();
    formData.append('username', document.getElementById('username').value);
    formData.append('password', document.getElementById('password').value);
    formData.append('full_name', document.getElementById('full_name').value);
    formData.append('pilot_name', document.getElementById('pilot_name').value);
    formData.append('email', document.getElementById('email').value);
    formData.append('license_type', document.getElementById('license_type').value);
    formData.append('aircraft_type', document.getElementById('aircraft_type').value);

    try {
        const response = await fetch('/api/register', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            showToast("Registration successful! Please login.");
            setTimeout(() => { window.location.href = '/login'; }, 1500);
        } else {
            const error = await response.json();
            showToast(error.detail || "Registration failed", true);
        }
    } catch (error) {
        showToast("An error occurred during registration", true);
    }
}

let currentUserData = null;

async function fetchUser() {
    try {
        const response = await apiFetch('/api/me');
        if (response.ok) {
            currentUserData = await response.json();
            updateProfileUI(currentUserData);
        }
    } catch (error) {
        console.error("Error fetching user info:", error);
    }
}

function updateProfileUI(user) {
    // Update nav icon
    const navInitial = document.getElementById('user-avatar-initial');
    if (navInitial) navInitial.innerText = user.full_name.charAt(0).toUpperCase();

    // Update popover info
    const popAvatar = document.getElementById('popover-avatar');
    if (popAvatar) popAvatar.innerText = user.full_name.charAt(0).toUpperCase();

    const popName = document.getElementById('popover-name');
    if (popName) popName.innerText = user.full_name;

    const popEmail = document.getElementById('popover-email');
    if (popEmail) popEmail.innerText = user.email;

    // Add Admin link if user is admin
    if (user.is_admin) {
        const logoutBtn = document.querySelector('.popover-logout');
        if (logoutBtn && !document.getElementById('admin-menu-item')) {
            const adminBtn = document.createElement('button');
            adminBtn.id = 'admin-menu-item';
            adminBtn.className = 'popover-menu-item';
            adminBtn.style.color = '#60a5fa'; // Blue-ish for admin
            adminBtn.onclick = () => window.location.href = '/admin';
            adminBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                Admin Dashboard
            `;
            logoutBtn.parentNode.insertBefore(adminBtn, logoutBtn);
        }
    }

    // Update popover badges
    const popBadges = document.getElementById('popover-badges');
    if (popBadges) {
        popBadges.innerHTML = `
            <span class="badge">${user.license_type}</span>
            <span class="badge">${user.aircraft_type}</span>
        `;
    }

    // Pre-fill edit form
    const editName = document.getElementById('edit-full-name');
    if (editName) editName.value = user.full_name;

    const editPilot = document.getElementById('edit-pilot-name');
    if (editPilot) editPilot.value = user.pilot_name;


    const editLicense = document.getElementById('edit-license');
    if (editLicense) editLicense.value = user.license_type;

    const editAircraft = document.getElementById('edit-aircraft');
    if (editAircraft) editAircraft.value = user.aircraft_type;
    
    const editEmail = document.getElementById('edit-email');
    if (editEmail) editEmail.value = user.email;
}

function toggleProfilePopover() {
    const popover = document.getElementById('profile-popover');
    if (popover) popover.classList.toggle('open');
}

function closeProfilePopover() {
    const popover = document.getElementById('profile-popover');
    if (popover) popover.classList.remove('open');
}

// Close popover when clicking outside
document.addEventListener('click', function(e) {
    const container = document.querySelector('.user-menu-container');
    if (container && !container.contains(e.target)) {
        closeProfilePopover();
    }
});

function openEditProfileModal() {
    closeProfilePopover();
    if (currentUserData) {
        document.getElementById('edit-full-name').value = currentUserData.full_name || '';
        document.getElementById('edit-pilot-name').value = currentUserData.pilot_name || '';
        document.getElementById('edit-license').value = currentUserData.license_type || '';
        document.getElementById('edit-aircraft').value = currentUserData.aircraft_type || '';
        const emailInput = document.getElementById('edit-email');
        if (emailInput) emailInput.value = currentUserData.email || '';
    }
    document.getElementById('profile-modal').classList.add('show');
}

function closeEditProfileModal() {
    document.getElementById('profile-modal').classList.remove('show');
}

async function handleUpdateProfile(event) {
    event.preventDefault();
    const formData = new FormData();
    formData.append('full_name', document.getElementById('edit-full-name').value);
    formData.append('pilot_name', document.getElementById('edit-pilot-name').value);
    formData.append('license_type', document.getElementById('edit-license').value);
    formData.append('aircraft_type', document.getElementById('edit-aircraft').value);
    const emailInput = document.getElementById('edit-email');
    if (emailInput) {
        formData.append('email', emailInput.value);
    }

    try {
        const response = await apiFetch('/api/profile', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const result = await response.json();
            showToast("Profile updated successfully!");
            closeEditProfileModal();
            await fetchUser(); // Refresh UI
            if (document.body.dataset.page === 'manage') {
                loadFlightHistory();
                loadSynonyms();
                loadSystemStatus();
            }
            if (document.body.dataset.page === 'dashboard') {
                await fetchDashboard(); // Refresh stats in case pilot name changed
            }
        } else {
            const error = await response.json();
            showToast(error.detail || "Update failed", true);
        }
    } catch (error) {
        showToast("An error occurred during update", true);
    }
}

async function loadSystemStatus() {
    try {
        const response = await fetch('/api/system-status', {
            headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
        });
        const status = await response.json();
        
        const calElement = document.getElementById('status-calamine');
        const csvElement = document.getElementById('status-xlsx2csv');
        const gemElement = document.getElementById('status-gemini');
        
        if (calElement) {
            calElement.textContent = status.calamine_installed ? '✅ Ready' : '❌ Missing';
            calElement.style.color = status.calamine_installed ? '#10b981' : '#ef4444';
        }
        if (csvElement) {
            csvElement.textContent = status.xlsx2csv_installed ? '✅ Ready' : '❌ Missing';
            csvElement.style.color = status.xlsx2csv_installed ? '#10b981' : '#ef4444';
        }
        if (gemElement) {
            gemElement.textContent = status.gemini_api_configured ? '✅ Configured' : '❌ Key Missing';
            gemElement.style.color = status.gemini_api_configured ? '#10b981' : '#ef4444';
        }
    } catch (err) {
        console.error("Failed to load system status:", err);
    }
}

async function handleSystemRepair() {
    showToast("🛠️ Starting self-repair. This may take 30-60 seconds...");
    try {
        const response = await fetch('/api/system-repair', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
        });
        const result = await response.json();
        showToast("✅ Repair attempt finished. Results: " + result.results.join(', '));
        loadSystemStatus();
    } catch (err) {
        showToast("❌ Repair failed: " + err.message, true);
    }
}

function handleLogout() {
    removeToken();
    window.location.href = '/login';
}

function exportPDF() {
    const pageIndex = window.currentPageIndex || 0;
    const currentPageNum = pageIndex + 1;
    const maxPageNum = (window.allPages && window.allPages.length) ? window.allPages.length : currentPageNum;

    const pageNumEl = document.getElementById('pdf-current-page-num');
    if (pageNumEl) pageNumEl.innerText = currentPageNum;
    
    const startPageInput = document.getElementById('pdf-start-page');
    if (startPageInput) startPageInput.value = currentPageNum;
    
    const endPageInput = document.getElementById('pdf-end-page');
    if (endPageInput) endPageInput.value = maxPageNum;
    
    const modal = document.getElementById('pdf-modal');
    if (modal) modal.classList.add('show');
}

function closePDFModal() {
    document.getElementById('pdf-modal').classList.remove('show');
}

function togglePDFRangeInput() {
    const rangeType = document.querySelector('input[name="pdf-range"]:checked').value;
    const inputs = document.getElementById('pdf-custom-range-inputs');
    if (rangeType === 'custom') {
        inputs.style.display = 'block';
    } else {
        inputs.style.display = 'none';
    }
}

function renderLogbookPageToHTML(pageData) {
    const fmt = (val) => {
        if (val === undefined || val === null) return '';
        const num = parseFloat(val);
        return (num !== 0) ? num.toFixed(1) : '';
    };

    const bf = pageData.brought_forward || {};
    const cf = pageData.carried_forward || {};
    const entries = pageData.entries || [];

    let rowsHtml = `
        <tr class="totals-row brought-forward">
            <td></td><td></td><td></td><td></td><td></td><td></td>
            <td style="text-align: center;">Totals brought forward</td>
            <td></td><td></td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(1)</span>${fmt(bf.day_p1)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(2)</span>${fmt(bf.day_p1us)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(3)</span>${fmt(bf.day_p2)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(4)</span>${fmt(bf.day_dual)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(5)</span>${fmt(bf.night_p1)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(6)</span>${fmt(bf.night_p1us)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(7)</span>${fmt(bf.night_p2)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(8)</span>${fmt(bf.night_dual)}</td>
            <td>${fmt(bf.inst_flying)}</td>
            <td>${fmt(bf.sim_time)}</td>
            <td></td>
        </tr>
    `;

    for (let i = 0; i < 18; i++) {
        const entry = entries[i] || {};
        if (entry.is_monthly_total) {
            rowsHtml += `
                <tr class="monthly-total-row">
                    <td colspan="9" style="text-align: left; padding-left: 20px;"><strong>${entry.date_str}</strong></td>
                    <td>${fmt(entry.day_p1)}</td><td>${fmt(entry.day_p1us)}</td><td>${fmt(entry.day_p2)}</td><td>${fmt(entry.day_dual)}</td>
                    <td>${fmt(entry.night_p1)}</td><td>${fmt(entry.night_p1us)}</td><td>${fmt(entry.night_p2)}</td><td>${fmt(entry.night_dual)}</td>
                    <td>${fmt(entry.inst_flying)}</td><td>${fmt(entry.sim_time)}</td><td></td>
                </tr>
            `;
        } else {
            rowsHtml += `
                <tr>
                    <td>${entry.date_str || ''}</td><td>${entry.ac_type || ''}</td><td>${entry.reg || ''}</td><td>${entry.pic || ''}</td><td>${entry.copilot || ''}</td><td>${entry.capacity || ''}</td>
                    <td>${entry.route || ''}</td><td></td><td></td>
                    <td>${fmt(entry.day_p1)}</td><td>${fmt(entry.day_p1us)}</td><td>${fmt(entry.day_p2)}</td><td>${fmt(entry.day_dual)}</td>
                    <td>${fmt(entry.night_p1)}</td><td>${fmt(entry.night_p1us)}</td><td>${fmt(entry.night_p2)}</td><td>${fmt(entry.night_dual)}</td>
                    <td>${fmt(entry.inst_flying)}</td><td>${fmt(entry.sim_time)}</td><td><small>${entry.remarks || ''}</small></td>
                </tr>
            `;
        }
    }

    rowsHtml += `
        <tr class="totals-row carried-forward">
            <td></td><td></td><td></td><td></td><td></td><td></td>
            <td style="text-align: center;">Totals carried forward</td>
            <td></td><td></td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(1)</span>${fmt(cf.day_p1)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(2)</span>${fmt(cf.day_p1us)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(3)</span>${fmt(cf.day_p2)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(4)</span>${fmt(cf.day_dual)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(5)</span>${fmt(cf.night_p1)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(6)</span>${fmt(cf.night_p1us)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(7)</span>${fmt(cf.night_p2)}</td>
            <td style="position:relative;"><span style="position:absolute; top:2px; left:4px; font-size:0.6rem; color:#94a3b8;">(8)</span>${fmt(cf.night_dual)}</td>
            <td>${fmt(cf.inst_flying)}</td>
            <td>${fmt(cf.sim_time)}</td>
            <td></td>
        </tr>
    `;

    return `
        <div class="pdf-page-wrapper" style="padding: 40px; background: white; color: black; min-height: 1000px; page-break-after: always;">
            <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
                <h2 style="font-size: 1.2rem; color: #1e293b; margin: 0;">CIVIL AVIATION DEPARTMENT - PILOT'S LOG BOOK</h2>
                <div style="font-weight: bold; font-size: 1.1rem; color: #1e293b;">Page ${pageData.page_number}</div>
            </div>
            <div style="margin-bottom: 10px; font-weight: bold; color: #1e293b;">Year / ${pageData.year || '----'}</div>
            <div class="cad407-wrapper" style="box-shadow: none; border: 1px solid #e2e8f0; padding: 0;">
                <table class="cad407-table" style="margin-top: 0; font-size: 0.8rem; width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background-color: #1e293b; color: white;">
                            <th rowspan="2" style="width: 70px; border: 1px solid #334155;">Date</th>
                            <th rowspan="2" style="width: 55px; border: 1px solid #334155;">Type</th>
                            <th rowspan="2" style="width: 80px; border: 1px solid #334155;">Reg</th>
                            <th rowspan="2" style="width: 100px; border: 1px solid #334155;">P.I.C</th>
                            <th rowspan="2" style="width: 100px; border: 1px solid #334155;">Co-Pilot</th>
                            <th rowspan="2" style="width: 65px; border: 1px solid #334155;">Cap</th>
                            <th rowspan="2" style="width: 220px; border: 1px solid #334155;">Journey</th>
                            <th colspan="2" style="border: 1px solid #334155;">No. of</th>
                            <th colspan="4" style="border: 1px solid #334155;">Day flying</th>
                            <th colspan="4" style="border: 1px solid #334155;">Night flying</th>
                            <th rowspan="2" style="width: 75px; border: 1px solid #334155;">Inst</th>
                            <th rowspan="2" style="width: 75px; border: 1px solid #334155;">Sim</th>
                            <th rowspan="2" style="width: 120px; border: 1px solid #334155;">Remarks</th>
                        </tr>
                        <tr style="background-color: #1e293b; color: white;">
                            <th style="border: 1px solid #334155;">T/O</th><th style="border: 1px solid #334155;">Lnd</th>
                            <th style="border: 1px solid #334155;">P1</th><th style="border: 1px solid #334155;">P1(U/S)</th><th style="border: 1px solid #334155;">P2</th><th style="border: 1px solid #334155;">P/UT</th>
                            <th style="border: 1px solid #334155;">P1</th><th style="border: 1px solid #334155;">P1(U/S)</th><th style="border: 1px solid #334155;">P2</th><th style="border: 1px solid #334155;">P/UT</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                    <tfoot>
                        <tr style="background: #f8fafc; color: #1e293b; font-weight: bold;">
                            <td colspan="17" style="text-align: right; padding-right: 20px; border: 1px solid #e2e8f0;">Grand total column (1) to (8):</td>
                            <td colspan="3" style="border: 1px solid #e2e8f0;">${pageData.grand_total_1_8.toFixed(1)}</td>
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    `;
}

function confirmExportPDF() {
    const rangeType = document.querySelector('input[name="pdf-range"]:checked').value;
    let start = 0;
    let end = 0;

    const maxPageCount = (window.allPages && window.allPages.length) ? window.allPages.length : 1;

    if (rangeType === 'all') {
        start = 1;
        end = maxPageCount;
    } else if (rangeType === 'current') {
        start = (window.currentPageIndex || 0) + 1;
        end = start;
    } else {
        start = parseInt(document.getElementById('pdf-start-page').value) || 1;
        end = parseInt(document.getElementById('pdf-end-page').value) || start;
    }

    // Basic validation
    if (start < 1) start = 1;
    if (end > maxPageCount) end = maxPageCount;
    if (start > end) {
        showToast("Invalid page range", true);
        return;
    }

    const token = getToken();
    const url = `/api/export_pdf?token=${token}&start_page=${start}&end_page=${end}`;
    
    showToast("Exporting high-fidelity PDF to your local drive... Please wait.");
    
    fetch(url)
        .then(response => {
            if (response.ok) {
                return response.blob();
            } else {
                return response.json().then(err => { throw err; });
            }
        })
        .then(blob => {
            const downloadUrl = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = `Logbook_Export_${start}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(downloadUrl);
            showToast("✅ Export complete!");
        })
        .catch(err => {
            console.error("Export error:", err);
            const msg = err.detail || err.message || "Error during export";
            showToast("❌ Export failed: " + msg, true);
        });
        
    closePDFModal();
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    if (!toast) return;
    
    let displayMsg = message;
    if (typeof message === 'object' && message !== null) {
        if (message.detail) {
            displayMsg = typeof message.detail === 'string' ? message.detail : JSON.stringify(message.detail);
        } else {
            displayMsg = JSON.stringify(message);
        }
    }
    
    // Legacy support for boolean isError
    let toastType = type;
    if (type === true) toastType = 'error';
    if (type === false) toastType = 'success';
    
    // Add to Error History if it's an error
    if (toastType === 'error') {
        addErrorToHistory(displayMsg);
    }
    
    const icon = toastType === 'error' ? '🚫' : (toastType === 'warning' ? '⚠️' : '✅');
    
    toast.innerHTML = `<span style="margin-right: 8px;">${icon}</span> <span>${displayMsg}</span> <span style="margin-left: 10px; cursor: pointer; opacity: 0.7;" onclick="this.parentElement.classList.remove('show')">✕</span>`;
    
    toast.className = 'toast show ' + toastType;
    
    if (window._toastTimeout) clearTimeout(window._toastTimeout);
    
    // Auto-hide unless it's a critical error
    if (toastType !== 'error') {
        window._toastTimeout = setTimeout(() => {
            toast.classList.remove('show');
        }, 4000);
    }
}

function addErrorToHistory(msg) {
    let history = JSON.parse(localStorage.getItem('error_history') || '[]');
    history.unshift({ msg, time: new Date().toLocaleTimeString() });
    if (history.length > 5) history.pop();
    localStorage.setItem('error_history', JSON.stringify(history));
    updateErrorBell();
}

function updateErrorBell() {
    let bell = document.getElementById('error-bell');
    if (!bell) {
        bell = document.createElement('div');
        bell.id = 'error-bell';
        bell.style = "position:fixed; bottom:20px; right:20px; width:40px; height:40px; background:#ef4444; border-radius:50%; display:flex; align-items:center; justify-content:center; cursor:pointer; z-index:10000; box-shadow:0 4px 12px rgba(0,0,0,0.5); font-size:20px;";
        bell.innerHTML = "🔔";
        bell.onclick = toggleErrorHistory;
        document.body.appendChild(bell);
    }
    const history = JSON.parse(localStorage.getItem('error_history') || '[]');
    bell.style.display = history.length > 0 ? 'flex' : 'none';
}

function toggleErrorHistory() {
    let panel = document.getElementById('error-history-panel');
    if (panel) {
        panel.remove();
        return;
    }
    
    panel = document.createElement('div');
    panel.id = 'error-history-panel';
    panel.style = "position:fixed; bottom:70px; right:20px; width:300px; background:#1a1b1e; border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:15px; z-index:10000; box-shadow:0 10px 25px rgba(0,0,0,0.5);";
    
    const history = JSON.parse(localStorage.getItem('error_history') || '[]');
    let html = '<h4 style="margin:0 0 10px 0; color:#ef4444;">Error History</h4>';
    if (history.length === 0) html += '<p style="font-size:0.8rem; opacity:0.5;">No errors yet.</p>';
    history.forEach(item => {
        html += `<div style="border-bottom:1px solid rgba(255,255,255,0.05); padding:8px 0;">
                    <div style="font-size:0.7rem; opacity:0.4;">${item.time}</div>
                    <div style="font-size:0.85rem;">${item.msg}</div>
                 </div>`;
    });
    html += '<button onclick="localStorage.removeItem(\'error_history\'); updateErrorBell(); this.parentElement.remove();" style="width:100%; margin-top:10px; background:transparent; border:1px solid rgba(255,255,255,0.1); color:white; padding:5px; border-radius:4px; cursor:pointer;">Clear History</button>';
    
    panel.innerHTML = html;
    document.body.appendChild(panel);
}

// Check bell on load
window.addEventListener('DOMContentLoaded', updateErrorBell);

function showForgotPassword(event) {
    if (event) event.preventDefault();
    const email = prompt("Please enter your account email to receive a reset link:");
    if (!email) return;
    
    const formData = new FormData();
    formData.append('email', email);
    
    fetch('/api/forgot-password', {
        method: 'POST',
        body: formData
    }).then(res => res.json())
      .then(data => {
          showToast(data.message);
      }).catch(err => {
          showToast("Failed to send reset link", true);
      });
}


async function fetchUploadMetadata() {
    try {
        const response = await apiFetch('/api/upload_metadata');
        const data = await response.json();
        
        const operatorList = document.getElementById('operator-list');
        const labelList = document.getElementById('label-list');
        
        if (operatorList) {
            operatorList.innerHTML = data.operators.map(org => `<option value="${org}">`).join('');
        }
        if (labelList) {
            labelList.innerHTML = data.labels.map(nat => `<option value="${nat}">`).join('');
        }
    } catch (error) {
        console.error("Error fetching upload metadata:", error);
    }
}

function updateFileName(input) {
    const fileNameDisplay = document.getElementById('file-name');
    if (input.files && input.files[0]) {
        fileNameDisplay.innerText = `Selected: ${input.files[0].name}`;
    }
}

function setupManualInputLogic() {
    const depInput = document.getElementById('manual-dep');
    const arrInput = document.getElementById('manual-arr');
    const totalInput = document.getElementById('manual-total-input');

    if (!depInput || !arrInput || !totalInput) return;

    function calculateTotal() {
        const dep = depInput.value.replace(/[^0-9]/g, '');
        const arr = arrInput.value.replace(/[^0-9]/g, '');
        
        if (dep.length === 4 && arr.length === 4) {
            const dH = parseInt(dep.substring(0, 2));
            const dM = parseInt(dep.substring(2, 4));
            const aH = parseInt(arr.substring(0, 2));
            const aM = parseInt(arr.substring(2, 4));
            
            if (dH < 24 && dM < 60 && aH < 24 && aM < 60) {
                let diffMin = (aH * 60 + aM) - (dH * 60 + dM);
                if (diffMin < 0) diffMin += 24 * 60; // Handle overnight
                
                const totalHours = diffMin / 60;
                totalInput.value = totalHours.toFixed(1);
            }
        }
    }

    [depInput, arrInput].forEach(el => el.addEventListener('input', calculateTotal));
}

function setupSmartDecimalInputs() {
    const inputs = document.querySelectorAll('.smart-decimal');
    
    inputs.forEach(input => {
        // Handle selection/focus behavior
        input.addEventListener('focus', () => {
            // Select all text so user can start typing over it
            setTimeout(() => input.select(), 0);
        });
        
        // Restore default on blur if empty
        input.addEventListener('blur', () => {
            if (input.value === '' || input.value === '.') {
                input.value = '0.0';
            }
        });

        input.addEventListener('input', (e) => {
            // Only allow digits
            let val = input.value.replace(/[^0-9]/g, '');
            
            if (val === '') {
                // If user deleted everything
                return;
            }
            
            // Limit to reasonable number of digits (e.g. 9999.9)
            if (val.length > 5) val = val.substring(0, 5);
            
            // Convert to number and shift decimal
            let num = parseInt(val, 10);
            let formatted = (num / 10).toFixed(1);
            
            input.value = formatted;
        });

        // Handle backspace properly
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Backspace') {
                let val = input.value.replace(/[^0-9]/g, '');
                if (val.length <= 1) {
                    input.value = '0.0';
                    e.preventDefault();
                }
            }
        });
    });
}

async function handleManualSubmit() {
    // We just trigger handleAdvancedUpload but we can add specific logic if needed
    // Actually, let's call the same function but it will prioritize manual if fields are filled
    await handleAdvancedUpload(new Event('manual'));
}

async function handleAdvancedUpload(event) {
    if (event) event.preventDefault();
    // ... rest of logic unchanged ...
    const fileInput = document.getElementById('excel-file');
    const operatorInput = document.getElementById('operator');
    const labelInput = document.getElementById('label');
    
    const formData = new FormData();
    formData.append('operator', operatorInput.value);
    formData.append('label', labelInput.value);
    // Always provide a file field (even if null) to avoid 422 errors
    formData.append('file', ''); 

    // Check if manual entry is being used
    const manualDate = document.getElementById('manual-date').value;
    if (manualDate) {
        // Validate mandatory fields
        const requiredManualFields = [
            { id: 'manual-date', name: 'DATE' },
            { id: 'manual-ac-type', name: 'AC TYPE' },
            { id: 'manual-ac-reg', name: 'AC REG' },
            { id: 'manual-pic', name: 'CAPTAIN' },
            { id: 'manual-capacity', name: 'OPERATING CAPACITY' }
        ];

        for (const field of requiredManualFields) {
            if (!document.getElementById(field.id).value) {
                showToast(`Please fill in required manual field: ${field.name}`, true);
                return;
            }
        }

        const total = parseFloat(document.getElementById('manual-total-input').value) || 0;
        
        if (total <= 0) {
            showToast("TOTAL hours must be greater than 0", true);
            return;
        }

        const flyingFields = [
            'day-p1', 'day-p1us', 'day-p2', 'day-put',
            'night-p1', 'night-p1us', 'night-p2', 'night-put'
        ];
        
        const flyingSum = flyingFields.reduce((sum, id) => {
            return sum + (parseFloat(document.getElementById(id).value) || 0);
        }, 0);

        if (Math.abs(flyingSum - total) > 0.05) {
            showToast(`Error: Sum of flying hours (${flyingSum.toFixed(1)}) does not equal TOTAL hours (${total.toFixed(1)})`, true);
            return;
        }

        formData.append('is_manual', 'true');
        formData.append('date', manualDate);
        formData.append('ac_type', document.getElementById('manual-ac-type').value);
        formData.append('ac_reg', document.getElementById('manual-ac-reg').value);
        formData.append('pic', document.getElementById('manual-pic').value);
        formData.append('copilot', document.getElementById('manual-copilot').value);
        formData.append('capacity', document.getElementById('manual-capacity').value);
        formData.append('route', document.getElementById('manual-route').value);
        formData.append('dep', document.getElementById('manual-dep').value);
        formData.append('arr', document.getElementById('manual-arr').value);
        formData.append('total', total);
        
        flyingFields.forEach(id => {
            formData.append(id.replace('-', '_'), document.getElementById(id).value);
        });
        
        formData.append('instr', document.getElementById('manual-instr').value);
        formData.append('sim', document.getElementById('manual-sim').value);
        formData.append('takeoff', document.getElementById('manual-takeoff').value);
        formData.append('landing', document.getElementById('manual-landing').value);
        formData.append('remarks', document.getElementById('manual-remarks').value);
    } else if (fileInput.files[0]) {
        formData.append('file', fileInput.files[0]);
    } else {
        showToast("Please provide a manual entry or select a file", true);
        return;
    }

    showToast("Uploading data...");
    try {
        let response = await apiFetch('/api/import', {
            method: 'POST',
            body: formData
        });
        
        // Handle Mapping Confirmation (Tiered AI detection)
        if (response.status === 422) {
            const result = await response.json();
            if (result.requires_mapping_confirmation) {
                showMappingModal(result.proposed_mapping, result.all_columns, result.ai_used);
                return; 
            }
        }

        // Handle year confirmation request
        if (response.status === 409) {
            const result = await response.json();
            if (result.requires_confirmation) {
                const confirmed = window.confirm(result.message);
                if (confirmed) {
                    formData.append('confirm_year', 'true');
                    showToast("Importing with confirmed year...");
                    response = await apiFetch('/api/import', {
                        method: 'POST',
                        body: formData
                    });
                } else {
                    showToast("Upload cancelled by user", true);
                    return;
                }
            }
        }
        
        if (response.ok) {
            const result = await response.json();
            if (result.status === "OVERLAP") {
                showToast(result.message, 'warning');
            } else if (result.status === "MERGED") {
                showToast(result.message);
                setTimeout(() => { window.location.href = '/preview'; }, 1500);
            } else {
                showToast(result.message || "Upload complete!");
                setTimeout(() => { window.location.href = '/preview'; }, 1500);
            }
        } else {
            const error = await response.json();
            showToast(error.detail || "Upload failed", true);
        }
    } catch (error) {
        showToast("An error occurred during upload", true);
    }
}

// --- Sync Adjustment Logic ---

let _syncAdjustments = [];

async function fetchSyncAdjustments() {
    try {
        const response = await apiFetch('/api/sync_adjustments');
        const data = await response.json();
        _syncAdjustments = data.adjustments || [];
        updateSyncStatusPanel();
    } catch (error) {
        console.error("Error fetching sync adjustments:", error);
    }
}

function updateSyncStatusPanel() {
    const activePanel = document.getElementById('sync-status-panel');
    const noPanel = document.getElementById('no-sync-panel');
    const pointsContainer = document.getElementById('active-sync-points');
    
    if (!activePanel || !noPanel || !pointsContainer) return;

    if (_syncAdjustments.length > 0) {
        activePanel.style.display = 'block';
        noPanel.style.display = 'none';
        
        pointsContainer.innerHTML = '';
        _syncAdjustments.forEach(adj => {
            const date = new Date(adj.date).toLocaleDateString();
            const badge = document.createElement('div');
            badge.style = "background: rgba(255,255,255,0.05); border: 1px solid var(--glass-border); padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.8rem; color: #e2e8f0; display: flex; align-items: center; gap: 0.5rem;";
            badge.innerHTML = `
                <span><strong>${date}</strong>: ${adj.remarks || 'Sync Point'}</span>
                <button onclick="deleteSyncAdjustment('${adj.id}')" style="background: none; border: none; color: #ef4444; cursor: pointer; padding: 0; font-size: 1rem; line-height: 1;">&times;</button>
            `;
            pointsContainer.appendChild(badge);
        });
    } else {
        activePanel.style.display = 'none';
        noPanel.style.display = 'block';
    }
}

function openSyncModal() {
    if (!allPages || allPages.length === 0) {
        showToast("Please wait for logbook data to load...", true);
        return;
    }
    const modal = document.getElementById('sync-modal');
    if (!modal) return;
    
    // Set default date to today or current page date
    const pageData = allPages[currentPageIndex];
    if (pageData && pageData.entries && pageData.entries.length > 0) {
        const entry = pageData.entries[0];
        if (entry.date_obj) {
            document.getElementById('sync-date').value = new Date(entry.date_obj).toISOString().split('T')[0];
        }
    } else {
        document.getElementById('sync-date').value = new Date().toISOString().split('T')[0];
    }
    
    updateSyncColumnsList();
    renderExistingSyncList();
    modal.classList.add('show');
}

function closeSyncModal() {
    document.getElementById('sync-modal').classList.remove('show');
}

function updateSyncColumnsList() {
    const rowLabels = document.getElementById('sync-row-labels');
    const rowDigital = document.getElementById('sync-row-digital');
    const rowPhysical = document.getElementById('sync-row-physical');
    const rowDelta = document.getElementById('sync-row-delta');
    
    if (!rowLabels || !rowDigital || !rowPhysical || !rowDelta) return;
    
    const pageData = allPages[currentPageIndex];
    if (!pageData) return;
    
    const totals = pageData.carried_forward || {};
    const cols = [
        { key: 'day_p1', name: 'Day P1' },
        { key: 'day_p1us', name: 'Day P1(U/S)' },
        { key: 'day_p2', name: 'Day P2' },
        { key: 'day_dual', name: 'Day Dual' },
        { key: 'night_p1', name: 'Night P1' },
        { key: 'night_p1us', name: 'Night P1(U/S)' },
        { key: 'night_p2', name: 'Night P2' },
        { key: 'night_dual', name: 'Night Dual' },
        { key: 'inst_flying', name: 'Inst.' },
        { key: 'sim_time', name: 'Sim.' }
    ];
    
    // Clear previous cells (keeping the headers)
    [rowLabels, rowDigital, rowPhysical, rowDelta].forEach(row => {
        while (row.cells.length > 1) row.deleteCell(1);
    });
    
    cols.forEach(col => {
        const currentVal = totals[col.key] || 0;
        
        // Category Label
        const tdLabel = rowLabels.insertCell();
        tdLabel.style = "padding: 8px; font-weight: 600; text-align: center; border: 1px solid rgba(255,255,255,0.05);";
        tdLabel.innerHTML = col.name;
        
        // Digital Value
        const tdDigital = rowDigital.insertCell();
        tdDigital.id = `digital-total-${col.key}`;
        tdDigital.style = "padding: 8px; text-align: center; font-family: var(--font-mono); border: 1px solid rgba(255,255,255,0.05);";
        tdDigital.innerText = currentVal.toFixed(1);
        
        // Physical Input
        const tdPhysical = rowPhysical.insertCell();
        tdPhysical.style = "padding: 8px; text-align: center; border: 1px solid rgba(255,255,255,0.05);";
        tdPhysical.innerHTML = `
            <input type="number" step="0.1" class="sync-input" data-col="${col.key}" 
                style="width: 60px; background: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; padding: 4px; border-radius: 4px; text-align: center; font-family: var(--font-mono); font-weight: bold;"
                oninput="calculateSyncDelta('${col.key}', ${currentVal})"
                placeholder="${currentVal.toFixed(1)}">
        `;
        
        // Delta Value
        const tdDelta = rowDelta.insertCell();
        tdDelta.id = `delta-${col.key}`;
        tdDelta.style = "padding: 8px; text-align: center; font-family: var(--font-mono); font-weight: bold; color: #94a3b8; border: 1px solid rgba(255,255,255,0.05);";
        tdDelta.innerText = "0.0";
    });
}

function calculateSyncDelta(colKey, currentVal) {
    const input = document.querySelector(`.sync-input[data-col="${colKey}"]`);
    const deltaEl = document.getElementById(`delta-${colKey}`);
    if (!input || !deltaEl) return;
    
    const paperVal = parseFloat(input.value);
    if (isNaN(paperVal)) {
        deltaEl.innerText = '0.0';
        deltaEl.style.color = '#94a3b8';
        return;
    }
    
    const delta = paperVal - currentVal;
    deltaEl.innerText = (delta >= 0 ? '+' : '') + delta.toFixed(1);
    deltaEl.style.color = delta === 0 ? '#94a3b8' : (delta > 0 ? '#4ade80' : '#f87171');
}

async function saveSyncAdjustment() {
    const date = document.getElementById('sync-date').value;
    const remarks = document.getElementById('sync-remarks').value;
    
    const offsets = {};
    document.querySelectorAll('.sync-input').forEach(input => {
        const col = input.dataset.col;
        const paperVal = parseFloat(input.value);
        if (!isNaN(paperVal)) {
            const digitalVal = parseFloat(document.getElementById(`digital-total-${col}`).innerText);
            const delta = paperVal - digitalVal;
            if (Math.abs(delta) > 0.001) {
                offsets[col] = delta;
            }
        }
    });
    
    if (Object.keys(offsets).length === 0) {
        showToast("No changes detected.", true);
        return;
    }
    
    try {
        const response = await apiFetch('/api/sync_adjustments', {
            method: 'POST',
            body: JSON.stringify({ date, offsets, remarks })
        });
        
        if (response.ok) {
            showToast("Sync adjustment saved!");
            closeSyncModal();
            // Refresh preview and adjustments
            await fetchSyncAdjustments();
            await fetchPreview();
        } else {
            showToast("Failed to save adjustment", true);
        }
    } catch (error) {
        showToast("Error saving adjustment", true);
    }
}

async function deleteSyncAdjustment(id) {
    if (!confirm("Are you sure you want to delete this sync point? The logbook totals will revert to their uncorrected values.")) return;
    
    try {
        const response = await apiFetch(`/api/sync_adjustments/${id}`, { method: 'DELETE' });
        if (response.ok) {
            showToast("Sync point deleted.");
            await fetchSyncAdjustments();
            await fetchPreview();
        }
    } catch (error) {
        showToast("Error deleting sync point", true);
    }
}

function renderExistingSyncList() {
    const container = document.getElementById('existing-sync-list');
    if (!container) return;
    
    if (_syncAdjustments.length === 0) {
        container.innerHTML = '<p style="color: #64748b; font-style: italic;">No active sync points.</p>';
        return;
    }
    
    container.innerHTML = '';
    _syncAdjustments.forEach(adj => {
        const div = document.createElement('div');
        div.style = "background: rgba(255,255,255,0.03); border: 1px solid var(--glass-border); padding: 0.75rem; border-radius: 6px; display: flex; justify-content: space-between; align-items: center;";
        
        const offsetsText = Object.entries(adj.offsets || {})
            .map(([k, v]) => `${k.replace('_', ' ').toUpperCase()}: ${v > 0 ? '+' : ''}${v}`)
            .join(', ');
            
        div.innerHTML = `
            <div>
                <div style="font-weight: 600; margin-bottom: 0.2rem;">${new Date(adj.date).toLocaleDateString()} - ${adj.remarks || 'Sync Point'}</div>
                <div style="font-size: 0.8rem; color: #94a3b8;">${offsetsText}</div>
            </div>
            <button class="btn btn-secondary btn-sm" onclick="deleteSyncAdjustment('${adj.id}')" style="color: #ef4444;">Delete</button>
        `;
        container.appendChild(div);
    });
}


document.addEventListener('DOMContentLoaded', init);

async function handleGoogleLogin() {
    try {
        const response = await fetch('/api/auth/google/login');
        const data = await response.json();
        if (data.url) {
            window.location.href = data.url;
        } else {
            alert("Failed to get Google login URL");
        }
    } catch (error) {
        console.error("Error initiating Google login:", error);
        alert("An error occurred during Google login");
    }
}

async function handleGoogleLink() {
    try {
        if (typeof currentUserData === 'undefined' || !currentUserData) {
            alert("You must be logged in to link your account.");
            return;
        }
        
        const response = await fetch(`/api/auth/google/login?link=true&current_user_id=${currentUserData.id}`);
        const data = await response.json();
        if (data.url) {
            window.location.href = data.url;
        } else {
            alert("Failed to get Google login URL");
        }
    } catch (error) {
        console.error("Error initiating Google link:", error);
        alert("An error occurred during Google link");
    }
}




function checkGuide() {
    const isDismissed = localStorage.getItem('onboarding_guide_dismissed');
    const guide = document.getElementById('onboarding-guide');
    if (guide && !isDismissed) {
        guide.style.display = 'block';
    }
}

let currentExcelColumns = [];

function showMappingModal(mapping, allColumns = [], aiUsed = false) {
    currentExcelColumns = allColumns; // Store for re-mapping
    const modal = document.getElementById('mapping-modal');
    const list = document.getElementById('mapping-list');
    const aiBadge = document.getElementById('ai-status-badge');
    list.innerHTML = '';
    
    if (aiBadge) aiBadge.style.display = aiUsed ? 'block' : 'none';
    
    // Core fields to show/confirm
    const coreFields = {
        'DEP': 'Flight Date',
        'FLT_SN': 'Flight S/N',
        'AC_TYPE': 'Aircraft Type',
        'AC_REG': 'Aircraft Reg',
        'TOTAL': 'Total Time',
        'ROUTE': 'Route',
        'CAPTAIN': 'PIC Name',
        'COPILOT': 'Copilot Name',
        'TAKEOFF': 'Takeoffs',
        'LANDING': 'Landings'
    };
    
    Object.entries(coreFields).forEach(([key, label]) => {
        const row = document.createElement('div');
        row.style.marginBottom = '1rem';
        row.style.padding = '0.75rem';
        row.style.background = 'rgba(255,255,255,0.03)';
        row.style.borderRadius = '8px';
        row.style.border = '1px solid rgba(255,255,255,0.05)';
        
        const colVal = mapping[key] || "";
        
        // Create select dropdown
        let optionsHtml = `<option value="">--- NOT FOUND ---</option>`;
        allColumns.forEach(col => {
            const selected = col === colVal ? 'selected' : '';
            optionsHtml += `<option value="${col}" ${selected}>${col}</option>`;
        });

        row.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
                <span style="font-weight: 700; font-size: 0.75rem; text-transform: uppercase; color: var(--accent-color);">${label}</span>
                <span style="font-size: 0.65rem; color: var(--text-muted); font-style: italic;">${colVal ? 'AI Matched' : 'Missing'}</span>
            </div>
            <select class="mapping-select" data-key="${key}" style="width: 100%; background: rgba(0,0,0,0.3); color: #fff; border: 1px solid rgba(255,255,255,0.1); border-radius: 4px; padding: 6px; font-size: 0.85rem;">
                ${optionsHtml}
            </select>
        `;
        list.appendChild(row);
    });
    
    modal.classList.add('show');
}

async function reMapWithAI() {
    const instruction = document.getElementById('ai-modal-instruction').value;
    if (!instruction) return;
    
    showToast("AI is analyzing your instruction...");
    
    try {
        const response = await apiFetch('/api/synonyms/ai', {
            method: 'POST',
            body: JSON.stringify({ instruction: instruction })
        });
        
        if (response.ok) {
            const result = await response.json();
            // We need to re-detect columns with the updated synonyms
            // For now, we can just let the AI tell us the mapping directly or suggest new ones
            showToast("Mapping rules updated! Re-scanning columns...");
            
            // Re-trigger the modal with the same columns but potentially new mapping
            // Note: Ideally the /api/synonyms/ai would also return the new mapping for currentExcelColumns
            // But for now, we'll just inform the user to try uploading again or manually select
            showToast("Synonyms updated. Please manually select or try uploading again for auto-match.");
        } else {
            showToast("AI could not process instruction", true);
        }
    } catch (e) {
        showToast("Error re-mapping", true);
    }
}

function closeMappingModal() {
    document.getElementById('mapping-modal').classList.remove('show');
}

async function confirmMapping() {
    // Gather custom mapping from dropdowns
    const selects = document.querySelectorAll('.mapping-select');
    const customMapping = {};
    selects.forEach(s => {
        customMapping[s.dataset.key] = s.value;
    });

    closeMappingModal();
    
    const form = document.getElementById('upload-form');
    const formData = new FormData(form);
    
    formData.append('confirm_mapping', 'true');
    formData.append('custom_mapping_raw', JSON.stringify(customMapping));
    
    showToast("Finalizing import with confirmed mapping...");
    
    const fileInput = document.getElementById('excel-file');
    if (fileInput.files[0]) {
        formData.append('file', fileInput.files[0]);
    }
    
    try {
        const response = await apiFetch('/api/import', {
            method: 'POST',
            body: formData
        });
        
        if (response.ok) {
            const result = await response.json();
            showToast(result.message || "Import successful!");
            setTimeout(() => { window.location.href = '/preview'; }, 1500);
        } else {
            const err = await response.json();
            showToast(err.detail || "Import failed", true);
        }
    } catch (e) {
        showToast("Error during confirmation", true);
    }
}
document.addEventListener('DOMContentLoaded', init);

function showConfirmModal(title, message, actionText, onConfirm) {
    const modal = document.getElementById('confirm-modal');
    if (!modal) {
        if (confirm(`${title}\n\n${message}`)) {
            onConfirm();
        }
        return;
    }
    document.getElementById('confirm-title').textContent = title;
    document.getElementById('confirm-message').textContent = message;
    const btn = document.getElementById('confirm-btn-action');
    btn.textContent = actionText;
    btn.onclick = () => {
        onConfirm();
        closeConfirmModal();
    };
    modal.classList.add('show');
}

function closeConfirmModal() {
    const modal = document.getElementById('confirm-modal');
    if (modal) modal.classList.remove('show');
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
                    showToast('Logbook restored successfully! Reloading...');
                    setTimeout(() => window.location.reload(), 1500);
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
