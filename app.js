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
        return `
            <div class="project-card" onclick="openProject('${project.id}')">
                <div class="project-header">
                    <h3 class="project-name">${project.name}</h3>
                    <span class="project-geo">${project.geo || 'Global'}</span>
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
        <div class="project-card" onclick="openProject('${project.id}')">
            <div class="project-header">
                <h3 class="project-name">${project.name}</h3>
                <span class="project-geo">${project.geo || 'Global'}</span>
            </div>
            <div class="project-body">
                <div class="project-chart">
                    <canvas id="chart-my-${index}" width="100" height="100"></canvas>
                    <div class="chart-center-text">
                        <div class="chart-percentage">${formatNumber(project.my_views)}</div>
                        <div class="chart-label">Views</div>
                    </div>
                </div>
                <div class="project-stats-vertical">
                    <div class="stat">
                        <div class="stat-label">My Views</div>
                        <div class="stat-value">${formatNumber(project.my_views)}</div>
                    </div>
                    <div class="stat">
                        <div class="stat-label">Target</div>
                        <div class="stat-value">${formatNumber(project.target_views)}</div>
                    </div>
                </div>
            </div>
        </div>
    `).join('');

    // Render charts after DOM update
    setTimeout(() => {
        projectsWithMyStats.forEach((project, index) => {
            // For "My Projects" show a simple donut chart (placeholder)
            const myProgress = project.target_views > 0 ? Math.round((project.my_views / project.target_views) * 100) : 0;
            createProgressChart(`chart-my-${index}`, myProgress);
        });
    }, 0);
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
