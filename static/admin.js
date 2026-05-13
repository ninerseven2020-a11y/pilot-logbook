function getToken() {
    return localStorage.getItem('logbook_auth_token');
}

async function fetchAdminData() {
    const token = getToken();
    if (!token) {
        window.location.href = '/login';
        return;
    }

    try {
        const response = await fetch('/api/admin/users', {
            headers: { 'Authorization': `Bearer ${token}` }
        });

        if (response.status === 403) {
            alert('Access Denied: Admin privileges required.');
            window.location.href = '/dashboard';
            return;
        }

        if (!response.ok) throw new Error('Failed to fetch admin data');

        const users = await response.json();
        renderAdminDashboard(users);
    } catch (error) {
        console.error('Admin Fetch Error:', error);
    }
}

function renderAdminDashboard(users) {
    const tbody = document.getElementById('user-table-body');
    tbody.innerHTML = '';

    let totalAI = 0;
    let active24h = 0;
    const now = new Date();
    const oneDayAgo = new Date(now.getTime() - (24 * 60 * 60 * 1000));

    let usersData = [];
    users.forEach(user => {
        usersData.push(user);
        const lastLogin = user.last_login ? new Date(user.last_login) : null;
        const joinedDate = user.created_at ? new Date(user.created_at) : null;
        
        totalAI += (user.ai_count || 0);
        if (lastLogin && lastLogin > oneDayAgo) active24h++;

        const functions = (user.functions_used || "").split(',').filter(f => f.trim());
        const funcHtml = functions.map(f => `<span class="func-tag">${f.trim()}</span>`).join('');

        const row = document.createElement('tr');
        row.innerHTML = `
            <td style="font-weight: 600; color: #fff;">${user.pilot_name || 'N/A'}</td>
            <td style="font-family: var(--font-mono); font-size: 0.8rem; color: #94a3b8;">${user.username}</td>
            <td style="font-size: 0.8rem; color: #64748b;">${joinedDate ? joinedDate.toLocaleDateString() : 'N/A'}</td>
            <td style="font-size: 0.85rem;">${lastLogin ? formatRelativeTime(lastLogin) : 'Never'}</td>
            <td style="font-weight: 600; color: #fff; text-align: center;">${user.login_count || 0}</td>
            <td>${funcHtml || '<span style="color: #475569; font-size: 0.7rem;">None</span>'}</td>
            <td style="text-align: right;">
                <button class="btn btn-sm" onclick="openMergeModal(${user.id}, '${user.pilot_name || user.username}')" style="background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.2); font-size: 0.7rem;">Merge</button>
            </td>
        `;
        tbody.appendChild(row);
    });

    window._allUsers = usersData;
    document.getElementById('total-users').textContent = users.length;
    document.getElementById('active-users').textContent = active24h;
    document.getElementById('total-ai').textContent = totalAI;
}

let mergeSourceId = null;

function openMergeModal(sourceId, sourceName) {
    mergeSourceId = sourceId;
    document.getElementById('merge-source-name').textContent = sourceName;
    
    const select = document.getElementById('merge-target-select');
    select.innerHTML = '<option value="">-- Select Target --</option>';
    
    window._allUsers.forEach(u => {
        if (u.id !== sourceId) {
            const opt = document.createElement('option');
            opt.value = u.id;
            opt.textContent = `${u.pilot_name || u.username} (${u.flight_count} flights)`;
            select.appendChild(opt);
        }
    });
    
    document.getElementById('merge-modal').style.display = 'flex';
}

function closeMergeModal() {
    document.getElementById('merge-modal').style.display = 'none';
}

async function confirmMerge() {
    const targetId = document.getElementById('merge-target-select').value;
    if (!targetId) {
        alert('Please select a target account.');
        return;
    }

    if (!confirm('Are you absolutely sure? This will delete the source account and move its data.')) return;

    try {
        const response = await fetch('/api/admin/merge_users', {
            method: 'POST',
            headers: { 
                'Authorization': `Bearer ${getToken()}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ source_id: mergeSourceId, target_id: parseInt(targetId) })
        });

        if (response.ok) {
            alert('Accounts merged successfully!');
            closeMergeModal();
            fetchAdminData();
        } else {
            const err = await response.json();
            alert('Merge failed: ' + (err.detail || 'Unknown error'));
        }
    } catch (e) {
        console.error('Merge error:', e);
        alert('An error occurred during merging.');
    }
}

function formatRelativeTime(date) {
    const now = new Date();
    const diff = Math.floor((now - date) / 1000);
    
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleDateString();
}

document.addEventListener('DOMContentLoaded', fetchAdminData);
