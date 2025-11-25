// ==================== CONFIGURATION ====================
const API_BASE_URL = 'https://view-counter-api.onrender.com';
let currentUser = null;
let currentProjects = [];

// ==================== TELEGRAM WEBAPP INITIALIZATION ====================
const tg = window.Telegram?.WebApp || { initData: '', ready: () => {}, expand: () => {} };

// Initialize Telegram WebApp
function initTelegramApp() {
    tg.ready();
    tg.expand();
}

// ==================== API CALLS ====================
async function apiCall(endpoint, options = {}) {
    try {
        const headers = {
            'Content-Type': 'application/json',
            'X-Telegram-Init-Data': tg.initData || '',
            ...options.headers
        };

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers
        });

        if (!response.ok) {
            throw new Error(`API Error: ${response.statusText}`);
        }

        return await response.json();
    } catch (error) {
        console.error('API Call failed:', error);
        showError(error.message);
        throw error;
    }
}

// ==================== UI FUNCTIONS ====================
function showError(message) {
    console.error('Error:', message);
    // You can add a toast notification here later
}

function formatNumber(num) {
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    } else if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toString();
}

function calculateDaysRemaining(endDate) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const end = new Date(endDate);
    end.setHours(0, 0, 0, 0);

    const diffTime = end - today;
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

    return diffDays;
}

// ==================== CHART FUNCTIONS ====================
function createProgressChart(canvasId, progress) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Clamp progress between 0 and 100
    progress = Math.max(0, Math.min(100, progress));

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            datasets: [{
                data: [progress, 100 - progress],
                backgroundColor: [
                    'rgba(102, 126, 234, 0.8)',  // Accent color for completed
                    'rgba(255, 255, 255, 0.1)'   // Light gray for remaining
                ],
                borderWidth: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '75%',
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    enabled: false
                }
            }
        }
    });
}

function createBarChart(canvasId, daysData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    const ctx = canvas.getContext('2d');

    // Calculate difference from previous day for each day
    const differences = daysData.map((day, index) => {
        if (index === 0) return 0;
        return day.views - daysData[index - 1].views;
    });

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: daysData.map(d => d.date),
            datasets: [{
                label: 'Views',
                data: daysData.map(d => d.views),
                backgroundColor: daysData.map((d, index) => {
                    if (index === 0) return 'rgba(102, 126, 234, 0.6)';
                    const diff = differences[index];
                    if (diff > 0) return 'rgba(76, 175, 80, 0.6)';  // Green for increase
                    if (diff < 0) return 'rgba(244, 67, 54, 0.6)';  // Red for decrease
                    return 'rgba(102, 126, 234, 0.6)';  // Purple for no change
                }),
                borderColor: daysData.map((d, index) => {
                    if (index === 0) return 'rgba(102, 126, 234, 1)';
                    const diff = differences[index];
                    if (diff > 0) return 'rgba(76, 175, 80, 1)';
                    if (diff < 0) return 'rgba(244, 67, 54, 1)';
                    return 'rgba(102, 126, 234, 1)';
                }),
                borderWidth: 2,
                borderRadius: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    padding: 12,
                    titleColor: '#fff',
                    bodyColor: '#fff',
                    callbacks: {
                        label: function(context) {
                            const index = context.dataIndex;
                            const value = context.parsed.y;
                            const diff = differences[index];

                            if (index === 0) {
                                return `Views: ${value.toLocaleString()}`;
                            }

                            const sign = diff > 0 ? '+' : '';
                            return [
                                `Views: ${value.toLocaleString()}`,
                                `${sign}${diff.toLocaleString()} from previous day`
                            ];
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        font: {
                            size: 10
                        }
                    },
                    grid: {
                        color: 'rgba(255, 255, 255, 0.1)',
                        drawBorder: false
                    }
                },
                x: {
                    ticks: {
                        color: 'rgba(255, 255, 255, 0.7)',
                        font: {
                            size: 10
                        }
                    },
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// Render projects with TOTAL stats (all participants)
async function renderProjects(projects) {
    const projectsList = document.getElementById('projects-list');

    if (!projectsList) {
        console.error('projects-list element not found');
        return;
    }

    if (projects.length === 0) {
        projectsList.innerHTML = '<div class="no-projects">No projects yet</div>';
        return;
    }

    // Fetch analytics for each project
    const projectsWithStats = await Promise.all(projects.map(async (project) => {
        try {
            const analytics = await apiCall(`/api/projects/${project.id}/analytics`);
            return { ...project, total_views: analytics.total_views || 0 };
        } catch (error) {
            console.error(`Failed to load analytics for project ${project.id}:`, error);
            return { ...project, total_views: 0 };
        }
    }));

    projectsList.innerHTML = projectsWithStats.map((project, index) => {
        const progress = project.target_views > 0 ? Math.round((project.total_views / project.target_views) * 100) : 0;
        const daysRemaining = calculateDaysRemaining(project.end_date);
        const daysText = daysRemaining === 1 ? 'day left' : daysRemaining < 0 ? 'Expired' : `${daysRemaining} days left`;
        const daysClass = daysRemaining < 7 ? 'days-urgent' : daysRemaining < 14 ? 'days-warning' : 'days-normal';

        return `
            <div class="project-card" onclick="openProject('${project.id}')">
                <div class="project-header">
                    <div class="project-header-left">
                        <h3 class="project-name">${project.name}</h3>
                        <span class="project-geo">${project.geo || 'Global'}</span>
                    </div>
                    <div class="project-days ${daysClass}">
                        <span class="days-icon">⏱</span>
                        <span class="days-text">${daysText}</span>
                    </div>
                </div>
                <div class="project-body">
                    <div class="project-chart">
                        <canvas id="chart-total-${index}" width="100" height="100"></canvas>
                        <div class="chart-center-text">
                            <div class="chart-percentage">${progress}%</div>
                            <div class="chart-label">Progress</div>
                        </div>
                    </div>
                    <div class="project-stats-vertical">
                        <div class="stat">
                            <div class="stat-label">Total Views</div>
                            <div class="stat-value">${formatNumber(project.total_views)}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Target</div>
                            <div class="stat-value">${formatNumber(project.target_views)}</div>
                        </div>
                    </div>
                    <div class="project-platforms">
                        <div class="platform-icon tiktok" title="TikTok">♪</div>
                        <div class="platform-icon instagram" title="Instagram">◉</div>
                        <div class="platform-icon youtube" title="YouTube">▶</div>
                        <div class="platform-icon facebook" title="Facebook">f</div>
                        <div class="platform-icon threads" title="Threads">@</div>
                    </div>
                </div>
            </div>
        `;
    }).join('');

    // Render charts after DOM update
    setTimeout(() => {
        projectsWithStats.forEach((project, index) => {
            const progress = project.target_views > 0 ? Math.round((project.total_views / project.target_views) * 100) : 0;
            createProgressChart(`chart-total-${index}`, progress);
        });
    }, 0);
}

// Render projects with MY PERSONAL stats
async function renderMyProjects(projects) {
    const myProjectsList = document.getElementById('my-projects-list');

    if (!myProjectsList) {
        console.error('my-projects-list element not found');
        return;
    }

    if (projects.length === 0) {
        myProjectsList.innerHTML = '<div class="no-projects">No projects yet</div>';
        return;
    }

    // Fetch MY analytics for each project
    const projectsWithMyStats = await Promise.all(projects.map(async (project) => {
        try {
            const myAnalytics = await apiCall(`/api/my-analytics?project_id=${project.id}`);
            return { ...project, my_views: myAnalytics.total_views || 0 };
        } catch (error) {
            console.error(`Failed to load my analytics for project ${project.id}:`, error);
            return { ...project, my_views: 0 };
        }
    }));

    myProjectsList.innerHTML = projectsWithMyStats.map((project, index) => `
        <div class="project-card-detailed" onclick="openProject('${project.id}')">
            <div class="project-header">
                <h3 class="project-name">${project.name}</h3>
                <span class="project-geo">${project.geo || 'Global'}</span>
            </div>

            <div class="project-total-views">
                <div class="total-views-label">My Total Views</div>
                <div class="total-views-value">${formatNumber(project.my_views)}</div>
            </div>

            <div class="project-chart-bar">
                <canvas id="chart-bar-${index}" height="120"></canvas>
            </div>

            <div class="chart-legend">Last 7 days activity</div>
        </div>
    `).join('');

    // Render bar charts after DOM update
    setTimeout(() => {
        projectsWithMyStats.forEach((project, index) => {
            // Generate mock data for last 7 days (placeholder)
            const last7Days = generateMockLast7Days(project.my_views);
            createBarChart(`chart-bar-${index}`, last7Days);
        });
    }, 0);
}

// Generate mock data for last 7 days (placeholder until we have real data)
function generateMockLast7Days(totalViews) {
    const days = [];
    const today = new Date();

    // Generate roughly realistic daily views
    const avgDaily = Math.floor(totalViews / 30); // Assume data is for ~30 days

    for (let i = 6; i >= 0; i--) {
        const date = new Date(today);
        date.setDate(date.getDate() - i);

        // Add some randomness (±30%)
        const randomFactor = 0.7 + Math.random() * 0.6;
        const views = Math.floor(avgDaily * randomFactor);

        days.push({
            date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
            views: views
        });
    }

    return days;
}

function openProject(projectId) {
    console.log('Opening project:', projectId);
    // TODO: Navigate to project details
    showError('Project details coming soon!');
}

// ==================== SIDEBAR ====================
function openSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    if (sidebar && overlay) {
        sidebar.classList.add('active');
        overlay.classList.add('active');
    }
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    if (sidebar && overlay) {
        sidebar.classList.remove('active');
        overlay.classList.remove('active');
    }
}

function showPage(pageName) {
    // Hide all pages
    document.querySelectorAll('.page').forEach(page => {
        page.classList.add('hidden');
    });

    // Show selected page
    const selectedPage = document.getElementById(`${pageName}-page`);
    if (selectedPage) {
        selectedPage.classList.remove('hidden');
    }

    // Update sidebar active state
    document.querySelectorAll('.sidebar-item').forEach(item => {
        item.classList.remove('active');
    });

    const activeItem = document.querySelector(`[onclick="showPage('${pageName}')"]`);
    if (activeItem) {
        activeItem.classList.add('active');
    }

    // Load data for specific pages
    if (pageName === 'projects' && currentProjects.length > 0) {
        renderMyProjects(currentProjects);
    }

    closeSidebar();
}

// ==================== INITIALIZATION ====================
async function init() {
    try {
        console.log('Initializing app...');

        // Initialize Telegram
        initTelegramApp();

        // Load user data and projects
        const data = await apiCall('/api/me');
        currentUser = data.user;
        currentProjects = data.projects || [];

        console.log('User:', currentUser);
        console.log('Projects:', currentProjects);

        // Update UI
        const usernameElement = document.getElementById('username');
        if (usernameElement) {
            usernameElement.textContent = `@${currentUser.username || currentUser.first_name}`;
        }

        // Render projects
        renderProjects(currentProjects);

        // Load analytics in background (non-blocking)
        apiCall('/api/my-analytics').then(statsData => {
            const totalViewsElement = document.getElementById('total-views');
            const totalProjectsElement = document.getElementById('total-projects');

            if (totalViewsElement) {
                totalViewsElement.textContent = formatNumber(statsData.total_views || 0);
            }
            if (totalProjectsElement) {
                totalProjectsElement.textContent = currentProjects.length;
            }
        }).catch(err => console.error('Failed to load analytics:', err));

        // Update profile
        const profileName = document.getElementById('profile-name');
        const profileUsername = document.getElementById('profile-username');
        const profileAvatar = document.getElementById('profile-avatar');

        if (profileName) {
            profileName.textContent = `${currentUser.first_name || ''} ${currentUser.last_name || ''}`.trim();
        }
        if (profileUsername) {
            profileUsername.textContent = `@${currentUser.username || 'user'}`;
        }
        if (profileAvatar) {
            profileAvatar.textContent = (currentUser.first_name || 'U')[0].toUpperCase();
        }

        // Hide loading, show content
        const loadingElement = document.getElementById('loading');
        const homePageElement = document.getElementById('home-page');

        if (loadingElement) {
            loadingElement.classList.add('hidden');
        }
        if (homePageElement) {
            homePageElement.classList.remove('hidden');
        }

        console.log('App initialized successfully');
    } catch (error) {
        console.error('Initialization failed:', error);

        // Show home page anyway
        const loadingElement = document.getElementById('loading');
        const homePageElement = document.getElementById('home-page');

        if (loadingElement) {
            loadingElement.classList.add('hidden');
        }
        if (homePageElement) {
            homePageElement.classList.remove('hidden');
        }

        showError('Failed to load data: ' + error.message);
    }
}

// ==================== VIDEO DOWNLOAD ====================
function downloadVideo() {
    const videoUrl = document.getElementById('video-url')?.value;
    if (!videoUrl) {
        showError('Please enter a video URL');
        return;
    }
    showError('Video download feature coming soon!');
}

// ==================== START APP ====================
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

// Make functions available globally
window.openSidebar = openSidebar;
window.closeSidebar = closeSidebar;
window.showPage = showPage;
window.openProject = openProject;
window.downloadVideo = downloadVideo;
