// Global variables
let chart = null;
let selectedAgent = null;
let chartVisibility = {};
let agentHealthCache = {};
let updateInterval = null;
let deviceListInterval = null;
// Alert cooldown system
const alertCooldowns = {};
const ALERT_COOLDOWN_TIME = 5 * 60 * 1000; // 5 minutes


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
        
        let html = '';
        agents.forEach(agent => {
            const health = getHealthStatus(agent.cpu, agent.memory, agent.disk);
            const lastUpdate = formatTimeFull(agent.timestamp);
            
            // Cache health for alerts
            const previousHealth = agentHealthCache[agent.agent_id];
            agentHealthCache[agent.agent_id] = health.status;
            
            // Check for health status change
            if (previousHealth && previousHealth !== health.status) {
                showNotification(`Device ${agent.agent_id} health changed to ${health.status}`, 
                               health.status === 'danger' ? 'danger' : 
                               health.status === 'moderate' ? 'warning' : 'success');
            }
            
            html += `
                <li class="device-item ${selectedAgent === agent.agent_id ? 'active' : ''}" 
                    data-agent-id="${agent.agent_id}"
                    data-cpu="${agent.cpu}"
                    data-memory="${agent.memory}"
                    data-disk="${agent.disk}">
                    <div class="device-status">
                        <span class="status-dot ${health.color}"></span>
                        <span class="agent-name">${agent.agent_id}</span>
                    </div>
                    <div class="device-metrics">
                        <span class="metric cpu" title="CPU: ${agent.cpu}%">${Math.round(agent.cpu)}%</span>
                        <span class="metric memory" title="Memory: ${agent.memory}%">${Math.round(agent.memory)}%</span>
                        <span class="metric disk" title="Disk: ${agent.disk}%">${Math.round(agent.disk)}%</span>
                    </div>
                    <div class="device-time">
                        <small>${lastUpdate}</small>
                    </div>
                </li>
            `;
        });
        
        deviceList.innerHTML = html;
        
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

// Update metric trend indicator
function updateMetricTrend(metric, value) {
    const trendElement = document.getElementById(`${metric}-trend`);
    const iconElement = document.getElementById(`${metric}-trend-icon`);
    
    if (!trendElement || !iconElement) return;
    
    // Simulated trend (in real app, compare with previous value)
    const trend = Math.random() > 0.5 ? 1 : -1;
    const change = (Math.random() * 5).toFixed(1);
    
    trendElement.textContent = `${trend > 0 ? '+' : ''}${change}%`;
    if (trend > 0) {
        iconElement.className = 'fas fa-arrow-up';
        iconElement.style.color = '#ef4444';
    } else {
        iconElement.className = 'fas fa-arrow-down';
        iconElement.style.color = '#10b981';
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
    
    const feedItem = `
        <div class="feed-item">
            <span class="feed-time">${time}</span>
            <span class="feed-text">${agentId}: CPU ${data.cpu_percent.toFixed(1)}%, 
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

// Export functions for global access
window.updateDeviceList = updateDeviceList;
window.selectDevice = selectDevice;
window.loadHistory = loadHistory;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', initDashboard);