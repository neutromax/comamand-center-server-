// Command Center Dashboard JavaScript
console.log("Dashboard loaded - Timezone Fixed");

// Global variables
let chart = null;
let selectedAgent = null;
let autoRefresh = true;
let chartVisibility = {}; // Store visibility per agent

// Format timestamp to readable IST time
function formatTimestamp(timestamp) {
    try {
        const date = new Date(timestamp);
        
        // Force 24-hour format to avoid AM/PM confusion
        const hours = date.getHours().toString().padStart(2, '0');
        const minutes = date.getMinutes().toString().padStart(2, '0');
        const seconds = date.getSeconds().toString().padStart(2, '0');
        
        return `${hours}:${minutes}:${seconds}`;
        
    } catch (error) {
        return timestamp;
    }
}

// Format date for tooltips
function formatDate(timestamp) {
    try {
        const date = new Date(timestamp);
        return date.toLocaleString('en-IN', {
            weekday: 'short',
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        });
    } catch (error) {
        return timestamp;
    }
}

// Clear selection function
function clearSelection() {
    selectedAgent = null;
    
    // Remove active class from all items
    document.querySelectorAll(".device-item").forEach(item => {
        item.classList.remove("active");
    });
    
    // Show welcome, hide chart
    const welcomeDiv = document.getElementById("welcome");
    const chartContainer = document.getElementById("chart-container");
    
    if (welcomeDiv) {
        welcomeDiv.classList.remove("hidden");
        welcomeDiv.innerHTML = `
            <h1>Welcome to Command Center</h1>
            <p>Select a device from the sidebar to view real-time metrics.</p>
        `;
    }
    if (chartContainer) {
        chartContainer.classList.add("hidden");
    }
    
    // Destroy chart if exists
    if (chart) {
        chart.destroy();
        chart = null;
    }
    
    console.log("Selection cleared");
}

// Load connected devices/agents
async function loadDevices() {
    try {
        const response = await fetch("/api/agents");
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const agents = await response.json();
        const deviceList = document.getElementById("device-list");
        
        if (!deviceList) return;
        
        // Clear current list
        deviceList.innerHTML = "";
        
        if (agents.length === 0) {
            deviceList.innerHTML = `
                <li class="no-agents">
                    <i>No devices connected</i><br>
                    <small>Start an agent to see devices here</small>
                </li>
            `;
            return;
        }
        
        // Add each agent to the list
        agents.forEach(agent => {
            const li = document.createElement("li");
            li.className = "device-item";
            li.setAttribute("data-agent-id", agent.agent_id);
            
            // Determine status color
            let statusClass = "status-online";
            let statusText = "Online";
            
            // Create status indicator
            const statusIndicator = document.createElement("span");
            statusIndicator.className = `status-indicator ${statusClass}`;
            statusIndicator.title = statusText;
            
            // Create agent info
            const agentInfo = document.createElement("div");
            agentInfo.className = "agent-info";
            
            agentInfo.innerHTML = `
                <div class="agent-name">${agent.agent_id}</div>
                <div class="agent-metrics">
                    <span class="metric cpu">CPU: ${agent.cpu.toFixed(1)}%</span>
                    <span class="metric memory">RAM: ${agent.memory.toFixed(1)}%</span>
                    <span class="metric disk">Disk: ${agent.disk.toFixed(1)}%</span>
                </div>
                <div class="agent-time">Last: ${formatTimestamp(agent.timestamp)}</div>
            `;
            
            li.appendChild(statusIndicator);
            li.appendChild(agentInfo);
            
            // Add click event
            li.addEventListener("click", () => {
                // Remove active class from all items
                document.querySelectorAll(".device-item").forEach(item => {
                    item.classList.remove("active");
                });
                
                // Add active class to clicked item
                li.classList.add("active");
                
                // Load history for this agent
                loadHistory(agent.agent_id);
            });
            
            deviceList.appendChild(li);
        });
        
    } catch (error) {
        console.error("Error loading devices:", error);
        const deviceList = document.getElementById("device-list");
        if (deviceList) {
            deviceList.innerHTML = `
                <li class="error">
                    <span class="error-icon">⚠</span>
                    Error loading devices: ${error.message}
                </li>
            `;
        }
    }
}

// Load history for selected agent
async function loadHistory(agentId) {
    if (!agentId) return;
    
    selectedAgent = agentId;
    
    try {
        const response = await fetch(`/api/reports/history/${agentId}`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        
        const historyData = await response.json();
        
        // Show/hide welcome message
        const welcomeDiv = document.getElementById("welcome");
        const chartContainer = document.getElementById("chart-container");
        
        if (!historyData || historyData.length === 0) {
            if (welcomeDiv) welcomeDiv.classList.remove("hidden");
            if (chartContainer) chartContainer.classList.add("hidden");
            
            // Update welcome message
            if (welcomeDiv) {
                welcomeDiv.innerHTML = `
                    <h1>No Data Available</h1>
                    <p>No metrics found for <strong>${agentId}</strong>.</p>
                    <p>Start sending reports to see data here.</p>
                `;
            }
            return;
        }
        
        // Hide welcome, show chart
        if (welcomeDiv) welcomeDiv.classList.add("hidden");
        if (chartContainer) chartContainer.classList.remove("hidden");
        
        // Prepare chart data (reverse for chronological order)
        const reversedData = [...historyData].reverse();
        
        // Extract data for chart
        const labels = reversedData.map(d => formatTimestamp(d.timestamp));
        const cpuData = reversedData.map(d => d.cpu_percent);
        const memoryData = reversedData.map(d => d.memory_percent);
        const diskData = reversedData.map(d => d.disk_percent);
        
        // Get chart canvas
        const ctx = document.getElementById("metricsChart").getContext("2d");
        
        // Initialize visibility for this agent if not exists
        if (!chartVisibility[agentId]) {
            chartVisibility[agentId] = {
                'CPU Usage %': false,
                'Memory Usage %': false,
                'Disk Usage %': false
            };
        }
        
        // Get current visibility if chart exists
        if (chart) {
            try {
                // Store current visibility state before destroying
                if (chart.data && chart.data.datasets) {
                    for (let i = 0; i < chart.data.datasets.length; i++) {
                        const dataset = chart.data.datasets[i];
                        const meta = chart.getDatasetMeta(i);
                        if (dataset.label && meta) {
                            chartVisibility[agentId][dataset.label] = meta.hidden === true;
                        }
                    }
                }
            } catch (e) {
                console.log("Error getting visibility:", e);
            }
            
            // Destroy existing chart
            chart.destroy();
        }
        
        // Create new chart
        chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'CPU Usage %',
                        data: cpuData,
                        borderColor: '#ff6384',
                        backgroundColor: 'rgba(255, 99, 132, 0.1)',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: true,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        hidden: chartVisibility[agentId]['CPU Usage %'] || false
                    },
                    {
                        label: 'Memory Usage %',
                        data: memoryData,
                        borderColor: '#36a2eb',
                        backgroundColor: 'rgba(54, 162, 235, 0.1)',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: true,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        hidden: chartVisibility[agentId]['Memory Usage %'] || false
                    },
                    {
                        label: 'Disk Usage %',
                        data: diskData,
                        borderColor: '#4bc0c0',
                        backgroundColor: 'rgba(75, 192, 192, 0.1)',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: true,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                        hidden: chartVisibility[agentId]['Disk Usage %'] || false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    title: {
                        display: true,
                        text: `Live Metrics - ${agentId}`,
                        font: {
                            size: 18,
                            weight: 'bold'
                        },
                        color: '#2c3e50'
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            title: function(tooltipItems) {
                                const index = tooltipItems[0].dataIndex;
                                return formatDate(reversedData[index].timestamp);
                            }
                        }
                    },
                    legend: {
                        position: 'top',
                        labels: {
                            font: {
                                size: 12
                            },
                            padding: 20,
                            usePointStyle: true
                        },
                        onClick: function(evt, legendItem, legend) {
                            // Update visibility state in our storage
                            const index = legendItem.datasetIndex;
                            const label = legend.chart.data.datasets[index].label;
                            
                            // Toggle visibility
                            const meta = legend.chart.getDatasetMeta(index);
                            meta.hidden = meta.hidden === null ? !legend.chart.data.datasets[index].hidden : null;
                            
                            // Store in our visibility object
                            chartVisibility[agentId][label] = meta.hidden === true;
                            
                            // Update the chart
                            legend.chart.update();
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Time (IST)',
                            font: {
                                size: 12,
                                weight: 'bold'
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        }
                    },
                    y: {
                        beginAtZero: true,
                        max: 100,
                        title: {
                            display: true,
                            text: 'Usage Percentage (%)',
                            font: {
                                size: 12,
                                weight: 'bold'
                            }
                        },
                        grid: {
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            callback: function(value) {
                                return value + '%';
                            }
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'nearest'
                },
                animation: {
                    duration: 750
                }
            }
        });
        
        // Update chart title with agent name
        const chartTitle = document.querySelector('.chart-title');
        if (chartTitle) {
            chartTitle.textContent = `Live Metrics - ${agentId}`;
        }
        
    } catch (error) {
        console.error(`Error loading history for ${agentId}:`, error);
        
        // Show error in welcome div
        const welcomeDiv = document.getElementById("welcome");
        if (welcomeDiv) {
            welcomeDiv.classList.remove("hidden");
            welcomeDiv.innerHTML = `
                <h1>Error Loading Data</h1>
                <p>Could not load metrics for <strong>${agentId}</strong>.</p>
                <p style="color: #e74c3c;">Error: ${error.message}</p>
            `;
        }
        
        const chartContainer = document.getElementById("chart-container");
        if (chartContainer) {
            chartContainer.classList.add("hidden");
        }
    }
}

// Toggle auto-refresh
function toggleAutoRefresh() {
    autoRefresh = !autoRefresh;
    const toggleBtn = document.getElementById("refresh-toggle");
    
    if (toggleBtn) {
        toggleBtn.textContent = autoRefresh ? "⏸ Pause" : "▶ Resume";
        toggleBtn.title = autoRefresh ? "Pause auto-refresh" : "Resume auto-refresh";
    }
    
    console.log(`Auto-refresh ${autoRefresh ? 'enabled' : 'disabled'}`);
}

// Initialize dashboard
function initDashboard() {
    console.log("Initializing dashboard...");
    
    // Load devices immediately
    loadDevices();
    
    // Set up auto-refresh for devices (every 3 seconds)
    setInterval(() => {
        if (autoRefresh) {
            loadDevices();
        }
    }, 3000);
    
    // Set up auto-refresh for selected agent (every 5 seconds)
    setInterval(() => {
        if (autoRefresh && selectedAgent) {
            loadHistory(selectedAgent);
        }
    }, 5000);
    
    // Add refresh toggle button if not exists
    if (!document.getElementById("refresh-toggle")) {
        const sidebar = document.querySelector(".sidebar h2");
        if (sidebar) {
            const toggleBtn = document.createElement("button");
            toggleBtn.id = "refresh-toggle";
            toggleBtn.textContent = "⏸ Pause";
            toggleBtn.title = "Pause auto-refresh";
            toggleBtn.className = "refresh-toggle";
            toggleBtn.addEventListener("click", toggleAutoRefresh);
            
            sidebar.insertAdjacentElement("afterend", toggleBtn);
        }
    }
    
    // Add server status check
    checkServerStatus();
    
    // Add click to welcome screen to clear selection
    const welcomeDiv = document.getElementById("welcome");
    if (welcomeDiv) {
        welcomeDiv.addEventListener("click", clearSelection);
    }
}

// Check server status
async function checkServerStatus() {
    try {
        const response = await fetch("/api/server/info");
        if (response.ok) {
            const data = await response.json();
            console.log("Server status:", data);
        }
    } catch (error) {
        console.warn("Server status check failed:", error);
    }
}

// Initialize when DOM is loaded
document.addEventListener("DOMContentLoaded", initDashboard);

// Export functions for debugging
window.dashboard = {
    loadDevices,
    loadHistory,
    toggleAutoRefresh,
    formatTimestamp,
    clearSelection
};