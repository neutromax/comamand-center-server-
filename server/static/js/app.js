// Global variables
let chart = null;
let selectedAgent = null;
let chartVisibility = {};
let agentHealthCache = {};
let previousMetrics = {}; // Track previous values for real trend calculation
let updateInterval = null;
let deviceListInterval = null;
// Alert cooldown system
const alertCooldowns = {};
const ALERT_COOLDOWN_TIME = 5 * 60 * 1000; // 5 minutes

// XSS Prevention: escape HTML entities in user-supplied strings
function escapeHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(str)));
    return div.innerHTML;
}


// Health thresholds
const THRESHOLDS = {
    CRITICAL: 80,  // Red: >80%
    WARNING: 60,   // Yellow: 60-80%
    GOOD: 60       // Green: <60%
};                                               

// Format timestamp for display
function formatTimestamp(timestamp) {
    if (!timestamp) return '--:--:--';
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// Format detailed timestamp
function formatTimeFull(timestamp) {
    if (!timestamp) return 'Never';
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
    });
}

// Determine health status and color
function getHealthStatus(cpu, memory, disk) {
    const maxMetric = Math.max(cpu, memory, disk);
    
    if (maxMetric > THRESHOLDS.CRITICAL) {
        return { status: 'danger', color: 'red' };
    } else if (maxMetric > THRESHOLDS.WARNING) {
        return { status: 'moderate', color: 'yellow' };
    } else {
        return { status: 'good', color: 'green' };
    }
}

// Update device list with health indicators
// Update device list with health indicators
async function updateDeviceList() {
    try {
        const response = await fetch('/api/agents');
        if (!response.ok) throw new Error('Failed to fetch agents');
        
        const agents = await response.json();
        const deviceList = document.getElementById('device-list');
        const deviceCount = document.getElementById('device-count');
        
        if (!agents || agents.length === 0) {
            deviceList.innerHTML = `
                <li class="no-agents">
                    <i class="fas fa-satellite-dish"></i>
                    <p>No devices connected</p>
                    <small>Start an agent to see devices here</small>
                </li>
            `;
            deviceCount.textContent = '0';
            return;
        }
        
        // Update device count
        deviceCount.textContent = agents.length;
        
        // Sort agents by health status (danger first)
        agents.sort((a, b) => {
            const healthA = getHealthStatus(a.cpu, a.memory, a.disk);
            const healthB = getHealthStatus(b.cpu, b.memory, b.disk);
            const priority = { danger: 3, moderate: 2, good: 1 };
            return priority[healthB.status] - priority[healthA.status];
        });
        
        // Get search filter query
        const searchInput = document.getElementById('device-search');
        const searchQuery = searchInput ? searchInput.value.toLowerCase().trim() : '';
        
        // Filter agents by search query (name or health status)
        const filteredAgents = agents.filter(agent => {
            const agentId = agent.agent_id.toLowerCase();
            const status = getHealthStatus(agent.cpu, agent.memory, agent.disk).status;
            return agentId.includes(searchQuery) || status.includes(searchQuery);
        });
        
        if (filteredAgents.length === 0) {
            deviceList.innerHTML = `
                <li class="no-agents">
                    <i class="fas fa-search"></i>
                    <p>No matching devices</p>
                    <small>Try a different search term</small>
                </li>
            `;
            return;
        }
        
        // Save scroll position
        const scrollContainer = document.querySelector('.devices-scroll');
        const prevScrollTop = scrollContainer ? scrollContainer.scrollTop : 0;
        
        let html = '';
        filteredAgents.forEach(agent => {
            const health = getHealthStatus(agent.cpu, agent.memory, agent.disk);
            const lastUpdate = formatTimeFull(agent.timestamp);
            
            // Cache health for alerts
            const previousHealth = agentHealthCache[agent.agent_id];
            agentHealthCache[agent.agent_id] = health.status;
            
            // Check for health status change (rate-limited and filtered to prevent spam at scale)
            if (previousHealth && previousHealth !== health.status) {
                const isSelected = (agent.agent_id === selectedAgent);
                const isDangerTransition = (health.status === 'danger');
                
                if (isSelected || isDangerTransition) {
                    const cooldownKey = `toast-health-${agent.agent_id}-${health.status}`;
                    if (canShowAlert(cooldownKey)) {
                        showNotification(`Device ${escapeHtml(agent.agent_id)} health changed to ${health.status}`, 
                                       health.status === 'danger' ? 'danger' : 
                                       health.status === 'moderate' ? 'warning' : 'success');
                    }
                }
            }
            
            // XSS Prevention: escape agent_id before rendering into HTML
            const safeAgentId = escapeHtml(agent.agent_id);
            const safeCpu = Number(agent.cpu) || 0;
            const safeMemory = Number(agent.memory) || 0;
            const safeDisk = Number(agent.disk) || 0;
            
            html += `
                <li class="device-item ${selectedAgent === agent.agent_id ? 'active' : ''}" 
                    data-agent-id="${safeAgentId}"
                    data-cpu="${safeCpu}"
                    data-memory="${safeMemory}"
                    data-disk="${safeDisk}">
                    <div class="device-status">
                        <span class="status-dot ${health.color}"></span>
                        <span class="agent-name">${safeAgentId}</span>
                    </div>
                    <div class="device-metrics">
                        <span class="metric cpu" title="CPU: ${safeCpu}%">${Math.round(safeCpu)}%</span>
                        <span class="metric memory" title="Memory: ${safeMemory}%">${Math.round(safeMemory)}%</span>
                        <span class="metric disk" title="Disk: ${safeDisk}%">${Math.round(safeDisk)}%</span>
                    </div>
                    <div class="device-time">
                        <small>${lastUpdate}</small>
                    </div>
                </li>
            `;
        });
        
        deviceList.innerHTML = html;
        
        // Restore scroll position
        if (scrollContainer) {
            scrollContainer.scrollTop = prevScrollTop;
        }
        
        // Add click handlers to device items
        document.querySelectorAll('.device-item').forEach(item => {
            item.addEventListener('click', function() {
                const agentId = this.getAttribute('data-agent-id');
                selectDevice(agentId);
            });
        });
        
    } catch (error) {
        console.error('Error updating device list:', error);
    }
}

// Select device and load its data
async function selectDevice(agentId) {
    if (selectedAgent === agentId) return;
    
    selectedAgent = agentId;
    window.currentAgentId = agentId; // Synchronize with inline scripts
    
    // Update active state
    document.querySelectorAll('.device-item').forEach(item => {
        item.classList.remove('active');
        if (item.getAttribute('data-agent-id') === agentId) {
            item.classList.add('active');
        }
    });
    
    // Show loading state
    const chartContainer = document.getElementById('chart-container');
    const welcomeDiv = document.getElementById('welcome');
    if (chartContainer && welcomeDiv) {
        welcomeDiv.classList.add('hidden');
        chartContainer.classList.remove('hidden');
    }
    
    // Update selected agent name
    const selectedName = document.getElementById('selected-agent-name');
    if (selectedName) {
        selectedName.textContent = agentId;
    }
    
    // Clear existing interval
    if (updateInterval) {
        clearInterval(updateInterval);
    }
    
    // Load initial data
    await loadHistory(agentId);
    
    // Start periodic updates every 10 seconds
    updateInterval = setInterval(() => {
        loadHistory(agentId);
    }, 10000);
    
    // Load active tab data
    const activeTab = document.querySelector('.tab-btn.active');
    if (activeTab) {
        const onclickAttr = activeTab.getAttribute('onclick') || '';
        if (onclickAttr.includes('processes-tab')) {
            dispatchProcessList();
        } else if (onclickAttr.includes('thresholds-tab')) {
            loadDeviceThresholds();
        } else if (onclickAttr.includes('incidents-tab')) {
            loadIncidentsHistory();
        }
    }
}

// Load history with smooth chart updates
async function loadHistory(agentId) {
    if (!agentId) return;
    
    try {
        const range = document.getElementById("time-range-select")?.value || "30m";
        const response = await fetch(`/api/reports/history/${agentId}?range=${range}`);

        if (!response.ok) throw new Error('Failed to fetch history');
        
        const historyData = await response.json();
        
        if (!historyData || historyData.length === 0) {
            showNotification(`No data available for ${agentId}`, 'warning');
            return;
        }
        
        // Update metrics summary
        updateMetricsSummary(historyData[historyData.length - 1]);
        
        // Prepare chart data (oldest first for chronological order)
        const reversedData = [...historyData].reverse();
        
        const labels = reversedData.map(d => formatTimestamp(d.timestamp));
        const cpuData = reversedData.map(d => d.cpu_percent);
        const memoryData = reversedData.map(d => d.memory_percent);
        const diskData = reversedData.map(d => d.disk_percent);
        
        // Get chart context
        const ctx = document.getElementById('metricsChart').getContext('2d');
        
        // Update or create chart
        if (chart) {
            // Smooth update existing chart
            chart.data.labels = labels;
            chart.data.datasets[0].data = cpuData;
            chart.data.datasets[1].data = memoryData;
            chart.data.datasets[2].data = diskData;
            
            // Update with animation
            chart.update('active');
        } else {
            // Create new chart
            chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: [
                        {
                            label: 'CPU Usage %',
                            data: cpuData,
                            borderColor: '#FF6384',
                            backgroundColor: 'rgba(255, 99, 132, 0.1)',
                            borderWidth: 2,
                            tension: 0.4,
                            fill: true,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            pointBackgroundColor: '#FF6384',
                            cubicInterpolationMode: 'monotone'
                        },
                        {
                            label: 'Memory Usage %',
                            data: memoryData,
                            borderColor: '#36A2EB',
                            backgroundColor: 'rgba(54, 162, 235, 0.1)',
                            borderWidth: 2,
                            tension: 0.4,
                            fill: true,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            pointBackgroundColor: '#36A2EB',
                            cubicInterpolationMode: 'monotone'
                        },
                        {
                            label: 'Disk Usage %',
                            data: diskData,
                            borderColor: '#4BC0C0',
                            backgroundColor: 'rgba(75, 192, 192, 0.1)',
                            borderWidth: 2,
                            tension: 0.4,
                            fill: true,
                            pointRadius: 0,
                            pointHoverRadius: 4,
                            pointBackgroundColor: '#4BC0C0',
                            cubicInterpolationMode: 'monotone'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    animation: {
                        duration: 1000,
                        easing: 'easeInOutQuart'
                    },
                    transitions: {
                        active: {
                            animation: {
                                duration: 1000,
                                easing: 'easeInOutQuart'
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            position: 'top',
                            labels: {
                                color: 'rgba(255, 255, 255, 0.8)',
                                font: {
                                    size: 12
                                },
                                padding: 20,
                                usePointStyle: true
                            }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: 'rgba(30, 41, 59, 0.9)',
                            titleColor: 'rgba(255, 255, 255, 0.9)',
                            bodyColor: 'rgba(255, 255, 255, 0.8)',
                            borderColor: 'rgba(255, 255, 255, 0.1)',
                            borderWidth: 1,
                            cornerRadius: 8,
                            callbacks: {
                                label: function(context) {
                                    let label = context.dataset.label || '';
                                    if (label) {
                                        label = label.split(' ')[0] + ': ';
                                    }
                                    label += context.parsed.y.toFixed(1) + '%';
                                    return label;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)',
                                borderColor: 'rgba(255, 255, 255, 0.1)'
                            },
                            ticks: {
                                color: 'rgba(255, 255, 255, 0.6)',
                                maxTicksLimit: 10
                            }
                        },
                        y: {
                            beginAtZero: true,
                            max: 100,
                            grid: {
                                color: 'rgba(255, 255, 255, 0.1)',
                                borderColor: 'rgba(255, 255, 255, 0.1)'
                            },
                            ticks: {
                                color: 'rgba(255, 255, 255, 0.6)',
                                callback: function(value) {
                                    return value + '%';
                                }
                            }
                        }
                    },
                    elements: {
                        line: {
                            tension: 0.4
                        },
                        point: {
                            radius: 0,
                            hoverRadius: 6
                        }
                    }
                }
            });
        }
        
        // Update live feed
        updateLiveFeed(agentId, historyData[historyData.length - 1]);
        
        // Check for alerts
        checkAlerts(historyData[historyData.length - 1]);
        
    } catch (error) {
        console.error(`Error loading history for ${agentId}:`, error);
        showNotification(`Error loading data for ${agentId}`, 'danger');
    }
}

// Update metrics summary cards
function updateMetricsSummary(latestData) {
    if (!latestData) return;
    
    // CPU
    const cpuValue = document.getElementById('cpu-value');
    if (cpuValue) {
        cpuValue.textContent = `${latestData.cpu_percent.toFixed(1)}%`;
        updateMetricColor('cpu', latestData.cpu_percent);
    }
    updateMetricTrend('cpu', latestData.cpu_percent);
    
    // Memory
    const memoryValue = document.getElementById('memory-value');
    if (memoryValue) {
        memoryValue.textContent = `${latestData.memory_percent.toFixed(1)}%`;
        updateMetricColor('memory', latestData.memory_percent);
    }
    updateMetricTrend('memory', latestData.memory_percent);
    
    // Disk
    const diskValue = document.getElementById('disk-value');
    if (diskValue) {
        diskValue.textContent = `${latestData.disk_percent.toFixed(1)}%`;
        updateMetricColor('disk', latestData.disk_percent);
    }
    updateMetricTrend('disk', latestData.disk_percent);
}

// Update metric trend indicator using real data comparison
function updateMetricTrend(metric, value) {
    const trendElement = document.getElementById(`${metric}-trend`);
    const iconElement = document.getElementById(`${metric}-trend-icon`);
    
    if (!trendElement || !iconElement) return;
    
    // Compare with previous value for real trend
    const prevValue = previousMetrics[metric];
    previousMetrics[metric] = value;
    
    if (prevValue === undefined || prevValue === null) {
        trendElement.textContent = '--';
        iconElement.className = 'fas fa-minus';
        iconElement.style.color = 'rgba(255,255,255,0.5)';
        return;
    }
    
    const change = (value - prevValue).toFixed(1);
    const trend = value - prevValue;
    
    trendElement.textContent = `${trend >= 0 ? '+' : ''}${change}%`;
    if (trend > 0) {
        iconElement.className = 'fas fa-arrow-up';
        iconElement.style.color = '#ef4444';
    } else if (trend < 0) {
        iconElement.className = 'fas fa-arrow-down';
        iconElement.style.color = '#10b981';
    } else {
        iconElement.className = 'fas fa-equals';
        iconElement.style.color = 'rgba(255,255,255,0.5)';
    }
}

// Update metric card color based on value
function updateMetricColor(metric, value) {
    const card = document.querySelector(`.${metric}-card .metric-value`);
    if (card) {
        if (value > THRESHOLDS.CRITICAL) {
            card.style.color = '#ef4444';
        } else if (value > THRESHOLDS.WARNING) {
            card.style.color = '#f59e0b';
        } else {
            card.style.color = '#10b981';
        }
    }
}
function canShowAlert(key) {
    const now = Date.now();

    if (!alertCooldowns[key]) {
        alertCooldowns[key] = now;
        return true;
    }

    if (now - alertCooldowns[key] > ALERT_COOLDOWN_TIME) {
        alertCooldowns[key] = now;
        return true;
    }

    return false;
}

// Check for alerts
function checkAlerts(latestData) {
    if (!latestData) return;
    
    const metrics = [
        { name: 'CPU', value: latestData.cpu_percent, threshold: THRESHOLDS.CRITICAL },
        { name: 'Memory', value: latestData.memory_percent, threshold: THRESHOLDS.CRITICAL },
        { name: 'Disk', value: latestData.disk_percent, threshold: THRESHOLDS.CRITICAL }
    ];
    
    metrics.forEach(metric => {
    const key = `${selectedAgent}-${metric.name}`;

    if (metric.value > metric.threshold) {
        if (canShowAlert(key)) {
            showNotification(`${metric.name} usage critical: ${metric.value.toFixed(1)}%`, 'danger');
        }
    } 
    else if (metric.value > THRESHOLDS.WARNING) {
        if (canShowAlert(key)) {
            showNotification(`${metric.name} usage high: ${metric.value.toFixed(1)}%`, 'warning');
        }
    }
});

}

// Update live feed
function updateLiveFeed(agentId, data) {
    const feedContent = document.getElementById('live-feed-content');
    if (!feedContent) return;
    
    const time = new Date().toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit',
        second: '2-digit'
    });
    
    // XSS Prevention: escape agentId in live feed
    const safeId = escapeHtml(agentId);
    const feedItem = `
        <div class="feed-item">
            <span class="feed-time">${time}</span>
            <span class="feed-text">${safeId}: CPU ${data.cpu_percent.toFixed(1)}%, 
            RAM ${data.memory_percent.toFixed(1)}%, 
            Disk ${data.disk_percent.toFixed(1)}%</span>
        </div>
    `;
    
    // Add new feed item
    feedContent.insertAdjacentHTML('afterbegin', feedItem);
    
    // Keep only last 5 items
    const items = feedContent.querySelectorAll('.feed-item');
    if (items.length > 5) {
        items[5].remove();
    }
}

// Initialize dashboard
function initDashboard() {
    console.log('Initializing dashboard...');
    
    // Update device list immediately
    updateDeviceList();
    
    // Bind search input to filter devices dynamically
    const searchInput = document.getElementById('device-search');
    if (searchInput) {
        searchInput.addEventListener('input', () => {
            updateDeviceList();
        });
    }
    
    // Start periodic device list updates (every 5 seconds)
    deviceListInterval = setInterval(updateDeviceList, 5000);
    
    // Add event listeners
    const refreshBtn = document.getElementById('refresh-chart');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            if (selectedAgent) {
                loadHistory(selectedAgent);
                showNotification('Chart refreshed', 'info');
            }
        });
    }
    
    const exportBtn = document.getElementById('export-chart');
    if (exportBtn) {
        exportBtn.addEventListener('click', () => {
            if (chart) {
                const link = document.createElement('a');
                link.download = `metrics-${selectedAgent || 'dashboard'}.png`;
                link.href = chart.toBase64Image();
                link.click();
                showNotification('Chart exported', 'success');
            }
        });
    }
    
    const refreshDevicesBtn = document.getElementById('refresh-devices');
    if (refreshDevicesBtn) {
        refreshDevicesBtn.addEventListener('click', () => {
            updateDeviceList();
            showNotification('Device list refreshed', 'info');
        });
    }
    
    // Handle window close
    window.addEventListener('beforeunload', () => {
        if (updateInterval) clearInterval(updateInterval);
        if (deviceListInterval) clearInterval(deviceListInterval);
    });
}

// --- Authentication & Custom Features ---

async function logout() {
    try {
        const response = await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();
        if (response.ok && data.status === 'ok') {
            window.location.href = '/login';
        } else {
            showNotification('Logout failed', 'danger');
        }
    } catch (err) {
        console.error('Logout error:', err);
        showNotification('Connection error during logout', 'danger');
    }
}
window.logout = logout;

function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        const onclickAttr = btn.getAttribute('onclick') || '';
        if (onclickAttr.includes(tabId)) {
            btn.classList.add('active');
        }
    });
    
    document.querySelectorAll('.tab-pane').forEach(pane => {
        pane.classList.remove('active');
    });
    const targetPane = document.getElementById(tabId);
    if (targetPane) {
        targetPane.classList.add('active');
    }
    
    if (selectedAgent) {
        if (tabId === 'processes-tab') {
            dispatchProcessList();
        } else if (tabId === 'thresholds-tab') {
            loadDeviceThresholds();
        } else if (tabId === 'incidents-tab') {
            loadIncidentsHistory();
        }
    }
}
window.switchTab = switchTab;

let processPollingInterval = null;

async function dispatchProcessList() {
    if (!selectedAgent) {
        showNotification('Please select a device first', 'warning');
        return;
    }
    
    const tbody = document.getElementById('process-list-body');
    if (tbody) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="table-empty">
                    <i class="fas fa-spinner fa-spin"></i> Requesting process list from device...
                </td>
            </tr>
        `;
    }
    
    try {
        const response = await fetch('/api/command/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agent_id: selectedAgent,
                action: 'list_processes'
            })
        });
        
        const data = await response.json();
        if (response.ok && data.status === 'ok') {
            pollCommandStatus(data.command_id, 'list_processes');
        } else {
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="5" class="table-empty text-danger">Failed to dispatch command: ${escapeHtml(data.message)}</td></tr>`;
            }
            showNotification(`Failed to request process list: ${data.message}`, 'danger');
        }
    } catch (err) {
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="5" class="table-empty text-danger">Connection error requesting process list</td></tr>`;
        }
        showNotification('Connection error requesting process list', 'danger');
    }
}
window.dispatchProcessList = dispatchProcessList;

function pollCommandStatus(cmdId, action) {
    if (processPollingInterval) {
        clearInterval(processPollingInterval);
    }
    
    let attempts = 0;
    const maxAttempts = 30;
    
    processPollingInterval = setInterval(async () => {
        attempts++;
        if (attempts > maxAttempts) {
            clearInterval(processPollingInterval);
            handleCommandTimeout(action);
            return;
        }
        
        try {
            const response = await fetch(`/api/command/${cmdId}/status`);
            const data = await response.json();
            
            if (response.ok && data.status) {
                if (data.status === 'completed') {
                    clearInterval(processPollingInterval);
                    if (action === 'list_processes') {
                        renderProcessList(data.output);
                    } else if (action === 'kill_process') {
                        showNotification('Process terminated successfully', 'success');
                        dispatchProcessList();
                    }
                } else if (data.status === 'failed') {
                    clearInterval(processPollingInterval);
                    if (action === 'list_processes') {
                        const tbody = document.getElementById('process-list-body');
                        if (tbody) {
                            tbody.innerHTML = `<tr><td colspan="5" class="table-empty text-danger">Process list failed: ${escapeHtml(data.output)}</td></tr>`;
                        }
                    } else {
                        showNotification(`Command execution failed: ${data.output}`, 'danger');
                    }
                }
            }
        } catch (err) {
            console.error('Error polling command status:', err);
        }
    }, 1000);
}

function handleCommandTimeout(action) {
    if (action === 'list_processes') {
        const tbody = document.getElementById('process-list-body');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="5" class="table-empty text-danger">Request timed out. The device is unresponsive.</td></tr>`;
        }
    } else {
        showNotification('Command execution timed out', 'danger');
    }
}

function renderProcessList(outputJson) {
    const tbody = document.getElementById('process-list-body');
    if (!tbody) return;
    
    try {
        const processes = JSON.parse(outputJson);
        if (!Array.isArray(processes) || processes.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="table-empty">No running processes found.</td></tr>`;
            return;
        }
        
        let html = '';
        processes.forEach(proc => {
            const name = escapeHtml(proc.name || 'unknown');
            const pid = Number(proc.pid);
            const cpu = (Number(proc.cpu_percent) || 0).toFixed(1);
            const mem = (Number(proc.memory_percent) || 0).toFixed(1);
            
            html += `
                <tr>
                    <td><code>${pid}</code></td>
                    <td class="proc-name"><strong>${name}</strong></td>
                    <td>${cpu}%</td>
                    <td>${mem}%</td>
                    <td>
                        <button class="kill-btn" onclick="killProcess(${pid})">
                            <i class="fas fa-trash-alt"></i> Kill
                        </button>
                    </td>
                </tr>
            `;
        });
        tbody.innerHTML = html;
    } catch (e) {
        tbody.innerHTML = `<tr><td colspan="5" class="table-empty text-danger">Error rendering processes: ${escapeHtml(e.message)}</td></tr>`;
    }
}

async function killProcess(pid) {
    if (!selectedAgent) return;
    if (!confirm(`Are you sure you want to terminate process PID ${pid}?`)) return;
    
    showNotification(`Requesting termination for process ${pid}...`, 'info');
    
    try {
        const response = await fetch('/api/command/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agent_id: selectedAgent,
                action: 'kill_process',
                payload: String(pid)
            })
        });
        
        const data = await response.json();
        if (response.ok && data.status === 'ok') {
            pollCommandStatus(data.command_id, 'kill_process');
        } else {
            showNotification(`Failed to request process kill: ${data.message}`, 'danger');
        }
    } catch (err) {
        showNotification('Connection error sending kill command', 'danger');
    }
}
window.killProcess = killProcess;

function runPresetCommand(command) {
    const input = document.getElementById('terminal-input');
    if (input) {
        input.value = command;
    }
    const form = document.getElementById('terminal-form');
    if (form) {
        const event = new Event('submit', { cancelable: true });
        form.dispatchEvent(event);
    }
}
window.runPresetCommand = runPresetCommand;

async function executeTerminalCommand(event) {
    if (event) event.preventDefault();
    
    if (!selectedAgent) {
        showNotification('Please select a device first', 'warning');
        return;
    }
    
    const input = document.getElementById('terminal-input');
    if (!input) return;
    
    const command = input.value.trim();
    if (!command) return;
    
    appendTerminalLine(`device:~# ${command}`, 'command-line');
    input.value = '';
    
    appendTerminalLine('Executing command on device, please wait...', 'system-line');
    
    try {
        const response = await fetch('/api/command/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                agent_id: selectedAgent,
                action: 'run_shell',
                payload: command
            })
        });
        
        const data = await response.json();
        if (response.ok && data.status === 'ok') {
            pollTerminalCommand(data.command_id);
        } else {
            appendTerminalLine(`Error: ${data.message}`, 'error-line');
            showNotification(`Failed to dispatch command: ${data.message}`, 'danger');
        }
    } catch (err) {
        appendTerminalLine('Connection error sending command to server', 'error-line');
    }
}
window.executeTerminalCommand = executeTerminalCommand;

function appendTerminalLine(text, className) {
    const consoleDiv = document.getElementById('terminal-console');
    if (!consoleDiv) return;
    
    const line = document.createElement('div');
    line.className = `term-line ${className || ''}`;
    
    if (className === 'output-line') {
        const pre = document.createElement('pre');
        pre.textContent = text;
        line.appendChild(pre);
    } else {
        line.textContent = text;
    }
    
    consoleDiv.appendChild(line);
    consoleDiv.scrollTop = consoleDiv.scrollHeight;
}

let terminalPollingInterval = null;

function pollTerminalCommand(cmdId) {
    if (terminalPollingInterval) {
        clearInterval(terminalPollingInterval);
    }
    
    let attempts = 0;
    const maxAttempts = 30;
    
    terminalPollingInterval = setInterval(async () => {
        attempts++;
        if (attempts > maxAttempts) {
            clearInterval(terminalPollingInterval);
            appendTerminalLine('Command timed out.', 'error-line');
            return;
        }
        
        try {
            const response = await fetch(`/api/command/${cmdId}/status`);
            const data = await response.json();
            
            if (response.ok && data.status) {
                if (data.status === 'completed') {
                    clearInterval(terminalPollingInterval);
                    appendTerminalLine(data.output, 'output-line');
                } else if (data.status === 'failed') {
                    clearInterval(terminalPollingInterval);
                    appendTerminalLine(data.output, 'error-line');
                }
            }
        } catch (err) {
            console.error('Error polling terminal status:', err);
        }
    }, 1000);
}

function updateSliderLabel(metric) {
    let warning = parseInt(document.getElementById(`${metric}-warning-range`).value);
    let critical = parseInt(document.getElementById(`${metric}-critical-range`).value);
    
    if (warning >= critical) {
        critical = warning + 5;
        if (critical > 100) critical = 100;
        document.getElementById(`${metric}-critical-range`).value = critical;
    }
    
    const label = document.getElementById(`${metric}-thresh-val`);
    if (label) {
        label.textContent = `Warning: ${warning}% | Critical: ${critical}%`;
    }
}
window.updateSliderLabel = updateSliderLabel;

async function loadDeviceThresholds() {
    if (!selectedAgent) return;
    
    try {
        const response = await fetch(`/api/thresholds/${selectedAgent}`);
        if (!response.ok) throw new Error('Failed to fetch thresholds');
        
        const data = await response.json();
        
        document.getElementById('cpu-warning-range').value = data.cpu_warning;
        document.getElementById('cpu-critical-range').value = data.cpu_critical;
        
        document.getElementById('mem-warning-range').value = data.memory_warning;
        document.getElementById('mem-critical-range').value = data.memory_critical;
        
        document.getElementById('disk-warning-range').value = data.disk_warning;
        document.getElementById('disk-critical-range').value = data.disk_critical;
        
        updateSliderLabel('cpu');
        updateSliderLabel('mem');
        updateSliderLabel('disk');
        
    } catch (error) {
        console.error('Error loading thresholds:', error);
        showNotification('Error loading device thresholds', 'danger');
    }
}
window.loadDeviceThresholds = loadDeviceThresholds;

async function saveDeviceThresholds() {
    if (!selectedAgent) {
        showNotification('Please select a device first', 'warning');
        return;
    }
    
    const cpuWarning = parseFloat(document.getElementById('cpu-warning-range').value);
    const cpuCritical = parseFloat(document.getElementById('cpu-critical-range').value);
    const memWarning = parseFloat(document.getElementById('mem-warning-range').value);
    const memCritical = parseFloat(document.getElementById('mem-critical-range').value);
    const diskWarning = parseFloat(document.getElementById('disk-warning-range').value);
    const diskCritical = parseFloat(document.getElementById('disk-critical-range').value);
    
    try {
        const response = await fetch(`/api/thresholds/${selectedAgent}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                cpu_warning: cpuWarning,
                cpu_critical: cpuCritical,
                memory_warning: memWarning,
                memory_critical: memCritical,
                disk_warning: diskWarning,
                disk_critical: diskCritical
            })
        });
        
        const data = await response.json();
        if (response.ok && data.status === 'ok') {
            showNotification('Thresholds saved successfully', 'success');
        } else {
            showNotification(`Failed to save thresholds: ${data.message}`, 'danger');
        }
    } catch (error) {
        console.error('Error saving thresholds:', error);
        showNotification('Connection error saving thresholds', 'danger');
    }
}
window.saveDeviceThresholds = saveDeviceThresholds;

async function loadIncidentsHistory() {
    if (!selectedAgent) return;
    
    const container = document.getElementById('incidents-timeline-list');
    if (!container) return;
    
    container.innerHTML = '<div class="timeline-loading"><i class="fas fa-spinner fa-spin"></i> Loading incident logs...</div>';
    
    try {
        const response = await fetch(`/api/incidents/${selectedAgent}`);
        if (!response.ok) throw new Error('Failed to fetch incidents');
        
        const incidents = await response.json();
        
        if (!incidents || incidents.length === 0) {
            container.innerHTML = '<div class="timeline-empty"><i class="fas fa-check-circle"></i> No incidents logged. Everything is running smoothly!</div>';
            return;
        }
        
        let html = '';
        incidents.forEach(inc => {
            const timeStr = formatTimeFull(inc.timestamp);
            const dateStr = new Date(inc.timestamp).toLocaleDateString([], { month: 'short', day: 'numeric' });
            const metric = escapeHtml(inc.metric.toUpperCase());
            const status = escapeHtml(inc.status);
            const valueStr = inc.value !== null ? `${Number(inc.value).toFixed(1)}%` : '';
            
            let statusClass = 'resolved';
            let icon = 'fa-check-circle';
            if (status === 'critical') {
                statusClass = 'critical';
                icon = 'fa-exclamation-circle';
            } else if (status === 'warning') {
                statusClass = 'warning';
                icon = 'fa-exclamation-triangle';
            }
            
            let message = '';
            if (inc.metric === 'connection') {
                message = status === 'critical' ? 'Device went OFFLINE' : 'Device recovered ONLINE';
            } else {
                message = status === 'resolved' ? `${metric} utilization returned to normal` : `${metric} usage is ${status} at ${valueStr}`;
            }
            
            html += `
                <div class="incident-item ${statusClass}">
                    <div class="incident-icon-wrapper">
                        <i class="fas ${icon}"></i>
                    </div>
                    <div class="incident-info">
                        <div class="incident-title">${message}</div>
                        <div class="incident-meta">${timeStr} | Status: ${status} ${valueStr ? `| Value: ${valueStr}` : ''}</div>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading incidents:', error);
        container.innerHTML = '<div class="timeline-empty text-danger"><i class="fas fa-times-circle"></i> Failed to load incidents.</div>';
    }
}
window.loadIncidentsHistory = loadIncidentsHistory;

// Export functions for global access
window.updateDeviceList = updateDeviceList;
window.selectDevice = selectDevice;
window.loadHistory = loadHistory;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', initDashboard);