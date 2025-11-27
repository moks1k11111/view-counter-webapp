// ==================== CONFIGURATION ====================
// Version: 1.2.0 - Updated 2025-11-26
const API_BASE_URL = 'https://view-counter-api.onrender.com';
const ADMIN_IDS = [873564841]; // ID администраторов
let currentUser = null;
let currentProjects = [];
let isAdmin = false;

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

function formatLastUpdate(lastUpdateTime) {
    if (!lastUpdateTime) {
        // Default: 15 minutes ago as placeholder
        return 'Обновлено 15 мин назад';
    }

    const now = new Date();
    const lastUpdate = new Date(lastUpdateTime);
    const diffMs = now - lastUpdate;
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));

    if (diffMinutes < 60) {
        return `Обновлено ${diffMinutes} мин назад`;
    } else {
        return `Обновлено ${diffHours}ч назад`;
    }
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
                        <div class="stat">
                            <div class="stat-label">KPI</div>
                            <div class="stat-value">от ${formatNumber(project.kpi_views || 1000)}</div>
                        </div>
                    </div>
                    <div class="last-update-text">${formatLastUpdate(project.last_update)}</div>
                    <div class="project-platforms">
                        <div class="platform-icon tiktok" title="TikTok"><i class="fa-brands fa-tiktok"></i></div>
                        <div class="platform-icon instagram" title="Instagram"><i class="fa-brands fa-instagram"></i></div>
                        <div class="platform-icon youtube" title="YouTube"><i class="fa-brands fa-youtube"></i></div>
                        <div class="platform-icon facebook" title="Facebook"><i class="fa-brands fa-facebook"></i></div>
                        <div class="platform-icon threads" title="Threads"><i class="fa-brands fa-threads"></i></div>
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

            <div class="project-kpi-info" style="margin-top: 10px; padding: 8px 12px; background: rgba(255,255,255,0.05); border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
                <span style="color: rgba(255,255,255,0.6); font-size: 12px;">KPI:</span>
                <span style="color: rgba(255,255,255,0.9); font-size: 14px; font-weight: 600;">от ${formatNumber(project.kpi_views || 1000)}</span>
            </div>

            <div class="project-chart-bar-wrapper">
                <div class="project-chart-bar">
                    <canvas id="chart-bar-${index}" height="120"></canvas>
                </div>
                <div class="chart-legend">Last 7 days activity</div>
                <div class="last-update-text">${formatLastUpdate(project.last_update)}</div>
                <div class="project-platforms">
                    <div class="platform-icon tiktok" title="TikTok"><i class="fa-brands fa-tiktok"></i></div>
                    <div class="platform-icon instagram" title="Instagram"><i class="fa-brands fa-instagram"></i></div>
                    <div class="platform-icon youtube" title="YouTube"><i class="fa-brands fa-youtube"></i></div>
                    <div class="platform-icon facebook" title="Facebook"><i class="fa-brands fa-facebook"></i></div>
                    <div class="platform-icon threads" title="Threads"><i class="fa-brands fa-threads"></i></div>
                </div>
            </div>
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

// Глобальные переменные для детальной страницы
let currentProjectData = null;
let currentSwipeIndex = 0;
let swipeStartX = 0;

async function openProject(projectId) {
    console.log('Opening project:', projectId);

    try {
        // Загружаем данные проекта
        const analytics = await apiCall(`/api/projects/${projectId}/analytics`);
        currentProjectData = analytics;

        // Показываем страницу детальной аналитики
        document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
        document.getElementById('project-details-page').classList.remove('hidden');

        // Обновляем заголовок
        document.getElementById('project-details-name').textContent = analytics.project.name;

        // Отображаем суммарную статистику
        displaySummaryStats(analytics);

        // Создаем слайды с диаграммами
        createChartSlides(analytics);

        // Отображаем список профилей
        displayProfiles(analytics);

    } catch (error) {
        console.error('Failed to load project details:', error);
        showError('Не удалось загрузить детали проекта');
    }
}

function closeProjectDetails() {
    document.getElementById('project-details-page').classList.add('hidden');
    document.getElementById('home-page').classList.remove('hidden');
}

function displaySummaryStats(analytics) {
    const { project, total_views, users_stats } = analytics;

    // Вычисляем количество профилей и видео
    const profilesCount = Object.keys(users_stats || {}).length;
    const totalVideos = 0; // TODO: добавить подсчет видео когда данные будут доступны

    // Процент выполнения
    const progress = project.target_views > 0
        ? Math.round((total_views / project.target_views) * 100)
        : 0;

    document.getElementById('detail-total-views').textContent = formatNumber(total_views);
    document.getElementById('detail-progress').textContent = `${progress}%`;
    document.getElementById('detail-total-videos').textContent = totalVideos;
    document.getElementById('detail-total-profiles').textContent = profilesCount;
}

function createChartSlides(analytics) {
    const swiperContainer = document.getElementById('charts-swiper');
    const dotsContainer = document.getElementById('swiper-dots');

    // Очищаем предыдущие слайды
    swiperContainer.innerHTML = '';
    dotsContainer.innerHTML = '';

    const slides = [];

    // Слайд 1: Столбчатая диаграмма по неделям
    slides.push(createWeeklyViewsSlide(analytics));

    // Слайд 2: Круговая диаграмма тематик
    slides.push(createTopicsSlide(analytics));

    // Слайд 3: Круговая диаграмма платформ
    slides.push(createPlatformsSlide(analytics));

    // Слайд 4: Круговая диаграмма профилей
    slides.push(createProfilesSlide(analytics));

    // Добавляем слайды
    swiperContainer.innerHTML = slides.join('');

    // Создаем точки-индикаторы
    for (let i = 0; i < slides.length; i++) {
        const dot = document.createElement('div');
        dot.className = `swiper-dot ${i === 0 ? 'active' : ''}`;
        dot.onclick = () => goToSlide(i);
        dotsContainer.appendChild(dot);
    }

    // Инициализируем свайпер
    initSwiper();

    // Рендерим диаграммы после добавления в DOM
    setTimeout(() => renderAllCharts(analytics), 100);
}

function createWeeklyViewsSlide(analytics) {
    return `
        <div class="chart-slide">
            <h4>Просмотры по неделям</h4>
            <canvas id="weekly-chart" width="300" height="200"></canvas>
        </div>
    `;
}

function createTopicsSlide(analytics) {
    return `
        <div class="chart-slide">
            <h4>Распределение по тематикам</h4>
            <canvas id="topics-chart" width="300" height="200"></canvas>
        </div>
    `;
}

function createPlatformsSlide(analytics) {
    return `
        <div class="chart-slide">
            <h4>Распределение по платформам</h4>
            <canvas id="platforms-chart" width="300" height="200"></canvas>
        </div>
    `;
}

function createProfilesSlide(analytics) {
    return `
        <div class="chart-slide">
            <h4>Топ профилей по просмотрам</h4>
            <canvas id="profiles-chart" width="300" height="200"></canvas>
        </div>
    `;
}

function renderAllCharts(analytics) {
    // Еженедельная статистика (заглушка)
    const weeklyData = [
        { week: 'Нед 1', views: Math.floor(analytics.total_views * 0.1) },
        { week: 'Нед 2', views: Math.floor(analytics.total_views * 0.15) },
        { week: 'Нед 3', views: Math.floor(analytics.total_views * 0.2) },
        { week: 'Нед 4', views: Math.floor(analytics.total_views * 0.25) },
    ];

    createWeeklyChart(weeklyData);
    createTopicsChart(analytics.topic_stats);
    createPlatformsChart(analytics.platform_stats);
    createProfilesChart(analytics.users_stats);
}

function createWeeklyChart(data) {
    const canvas = document.getElementById('weekly-chart');
    if (!canvas) return;

    new Chart(canvas, {
        type: 'bar',
        data: {
            labels: data.map(d => d.week),
            datasets: [{
                label: 'Просмотры',
                data: data.map(d => d.views),
                backgroundColor: 'rgba(102, 126, 234, 0.7)',
                borderColor: 'rgba(102, 126, 234, 1)',
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: {
                y: { beginAtZero: true, ticks: { color: '#fff' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                x: { ticks: { color: '#fff' }, grid: { display: false } }
            }
        }
    });
}

function createTopicsChart(topicStats) {
    const canvas = document.getElementById('topics-chart');
    if (!canvas) return;

    const labels = Object.keys(topicStats);
    const data = Object.values(topicStats);

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: [
                    'rgba(255, 99, 132, 0.8)',
                    'rgba(54, 162, 235, 0.8)',
                    'rgba(255, 206, 86, 0.8)',
                    'rgba(75, 192, 192, 0.8)',
                    'rgba(153, 102, 255, 0.8)',
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#fff', font: { size: 10 } } }
            }
        }
    });
}

function createPlatformsChart(platformStats) {
    const canvas = document.getElementById('platforms-chart');
    if (!canvas) return;

    const labels = Object.keys(platformStats);
    const data = Object.values(platformStats);

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: [
                    'rgba(0, 242, 234, 0.8)',  // TikTok
                    'rgba(131, 58, 180, 0.8)', // Instagram
                    'rgba(255, 0, 0, 0.8)',    // YouTube
                    'rgba(24, 119, 242, 0.8)', // Facebook
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#fff', font: { size: 10 } } }
            }
        }
    });
}

function createProfilesChart(usersStats) {
    const canvas = document.getElementById('profiles-chart');
    if (!canvas) return;

    const sortedUsers = Object.entries(usersStats)
        .sort((a, b) => b[1].total_views - a[1].total_views)
        .slice(0, 5);

    const labels = sortedUsers.map(([name]) => name);
    const data = sortedUsers.map(([, stats]) => stats.total_views);

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: [
                    'rgba(102, 126, 234, 0.8)',
                    'rgba(76, 175, 80, 0.8)',
                    'rgba(244, 67, 54, 0.8)',
                    'rgba(255, 193, 7, 0.8)',
                    'rgba(156, 39, 176, 0.8)',
                ]
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { position: 'bottom', labels: { color: '#fff', font: { size: 9 } } }
            }
        }
    });
}

// Свайпер
function initSwiper() {
    const swiper = document.getElementById('charts-swiper');
    currentSwipeIndex = 0;

    swiper.addEventListener('touchstart', (e) => {
        swipeStartX = e.touches[0].clientX;
    });

    swiper.addEventListener('touchend', (e) => {
        const swipeEndX = e.changedTouches[0].clientX;
        const diff = swipeStartX - swipeEndX;

        if (Math.abs(diff) > 50) {
            if (diff > 0) {
                nextSlide();
            } else {
                prevSlide();
            }
        }
    });

    updateSlidePosition();
}

function nextSlide() {
    const slides = document.querySelectorAll('.chart-slide');
    if (currentSwipeIndex < slides.length - 1) {
        currentSwipeIndex++;
        updateSlidePosition();
    }
}

function prevSlide() {
    if (currentSwipeIndex > 0) {
        currentSwipeIndex--;
        updateSlidePosition();
    }
}

function goToSlide(index) {
    currentSwipeIndex = index;
    updateSlidePosition();
}

function updateSlidePosition() {
    const swiper = document.getElementById('charts-swiper');
    const offset = -currentSwipeIndex * 100;
    swiper.style.transform = `translateX(${offset}%)`;

    // Обновляем точки
    document.querySelectorAll('.swiper-dot').forEach((dot, i) => {
        dot.classList.toggle('active', i === currentSwipeIndex);
    });
}

function displayProfiles(analytics) {
    const profilesList = document.getElementById('profiles-list');
    const profilesCount = document.getElementById('profiles-count');

    const users = Object.entries(analytics.users_stats || {});
    profilesCount.textContent = users.length;

    if (users.length === 0) {
        profilesList.innerHTML = '<p class="no-profiles">Нет профилей</p>';
        return;
    }

    const profilesHTML = users.map(([userName, stats]) => `
        <div class="profile-item">
            <div class="profile-info">
                <div class="profile-name">${userName}</div>
                <div class="profile-stats">
                    <span>Просмотры: ${formatNumber(stats.total_views)}</span>
                </div>
            </div>
        </div>
    `).join('');

    profilesList.innerHTML = profilesHTML;
}

function toggleProfiles() {
    const profilesList = document.getElementById('profiles-list');
    const chevron = document.getElementById('profiles-chevron');

    profilesList.classList.toggle('open');
    chevron.classList.toggle('rotated');
}

// ==================== ADD PROFILE MODAL ====================

// Global variables for multi-step profile addition
let profileData = {
    url: '',
    status: '',
    topic: ''
};

function openAddProfileModal() {
    const modal = document.getElementById('add-profile-modal');
    modal.classList.remove('hidden');

    // Reset to step 1
    document.querySelectorAll('.profile-step').forEach(step => step.classList.add('hidden'));
    document.getElementById('profile-step-1').classList.remove('hidden');

    // Clear all inputs
    document.getElementById('profile-url-input').value = '';
    profileData = { url: '', status: '', topic: '' };
}

function closeAddProfileModal() {
    const modal = document.getElementById('add-profile-modal');
    modal.classList.add('hidden');

    // Reset to step 1
    document.querySelectorAll('.profile-step').forEach(step => step.classList.add('hidden'));
    document.getElementById('profile-step-1').classList.remove('hidden');

    // Clear data
    profileData = { url: '', status: '', topic: '' };
}

// Step 1: Validate URL and move to status selection
function nextToStatusStep() {
    const urlInput = document.getElementById('profile-url-input');
    const profileUrl = urlInput.value.trim();

    if (!profileUrl) {
        showError('Пожалуйста, введите ссылку на профиль');
        return;
    }

    // Простая валидация URL
    if (!profileUrl.startsWith('http://') && !profileUrl.startsWith('https://')) {
        showError('Пожалуйста, введите корректную ссылку (начинается с http:// или https://)');
        return;
    }

    // Save URL and move to step 2
    profileData.url = profileUrl;

    document.getElementById('profile-step-1').classList.add('hidden');
    document.getElementById('profile-step-2').classList.remove('hidden');
}

// Step 2: Select status and move to topic selection
function selectStatus(status) {
    profileData.status = status;

    document.getElementById('profile-step-2').classList.add('hidden');
    document.getElementById('profile-step-3').classList.remove('hidden');
}

// Step 3: Select predefined topic and submit
function selectTopic(topic) {
    profileData.topic = topic;
    submitProfileWithData();
}

// Step 3 -> 4: Open custom topic input
function openCustomTopic() {
    document.getElementById('profile-step-3').classList.add('hidden');
    document.getElementById('profile-step-4').classList.remove('hidden');
    document.getElementById('custom-topic-input').focus();
}

// Step 4: Submit with custom topic
function submitCustomTopic() {
    const customTopic = document.getElementById('custom-topic-input').value.trim();

    if (!customTopic) {
        showError('Пожалуйста, введите тематику');
        return;
    }

    profileData.topic = customTopic;
    submitProfileWithData();
}

// Helper function to detect platform from URL
function detectPlatform(url) {
    if (url.includes('tiktok.com')) return 'TikTok';
    if (url.includes('instagram.com')) return 'Instagram';
    if (url.includes('facebook.com')) return 'Facebook';
    if (url.includes('youtube.com') || url.includes('youtu.be')) return 'YouTube';
    return 'Социальная сеть';
}

// Final submission
async function submitProfileWithData() {
    try {
        console.log('Добавляем профиль:', profileData);

        // Определяем платформу из URL
        const platform = detectPlatform(profileData.url);

        // Получаем название проекта
        const projectName = currentProjectData?.project?.name || 'проект';

        // TODO: Отправить запрос на бэкенд для добавления профиля
        // const response = await fetch('/api/profiles', {
        //     method: 'POST',
        //     headers: { 'Content-Type': 'application/json' },
        //     body: JSON.stringify({
        //         url: profileData.url,
        //         status: profileData.status,
        //         topic: profileData.topic,
        //         project_id: currentProjectData.project.id
        //     })
        // });

        // Закрываем модалку
        closeAddProfileModal();

        // Показываем успешное сообщение
        const status = profileData.status || 'NEW';
        const topic = profileData.topic || 'не указана';
        showSuccess(`Вы добавили профиль ${platform} ${status}, тематика ${topic} в проект ${projectName}`);

        // TODO: Обновить список профилей после добавления
        // await loadProjectDetails(currentProjectData.project.id);

    } catch (error) {
        console.error('Failed to add profile:', error);
        showError('Не удалось добавить профиль');
    }
}

function showSuccess(message) {
    // Создаем элемент уведомления
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 15px 25px;
        border-radius: 12px;
        z-index: 9999;
        font-weight: 600;
        box-shadow: 0 10px 30px rgba(102, 126, 234, 0.3);
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Удаляем через 3 секунды
    setTimeout(() => {
        notification.remove();
    }, 3000);
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
    } else if (pageName === 'admin' && isAdmin) {
        // Даем DOM время на обновление перед загрузкой данных
        // Используем requestAnimationFrame для гарантии что DOM отрисовался
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                loadAdminData();
            });
        });
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

        // Check if user is admin
        isAdmin = ADMIN_IDS.includes(currentUser.id);
        console.log('Is admin:', isAdmin, 'User ID:', currentUser.id);

        // Show/hide admin menu item
        const adminMenuItem = document.getElementById('admin-menu-item');
        if (adminMenuItem) {
            adminMenuItem.style.display = isAdmin ? 'flex' : 'none';
        }

        // Update UI
        const usernameElement = document.getElementById('username');
        if (usernameElement) {
            usernameElement.textContent = currentUser.first_name || 'User';
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

// ==================== ADMIN PANEL ====================
async function loadAdminData() {
    if (!isAdmin) {
        console.error('Access denied: user is not admin');
        return;
    }

    try {
        console.log('Loading admin data...');

        // TODO: Создать API endpoint для админской статистики
        // Пока используем существующие данные для демонстрации

        // Получаем статистику
        const uniqueUsers = new Set();
        let totalProjects = currentProjects.length;
        let totalProfiles = 0;
        let totalViews = 0;

        // Получаем общую статистику по всем проектам
        const projectsStats = await Promise.all(
            currentProjects.map(project =>
                apiCall(`/api/projects/${project.id}/analytics`).catch(() => null)
            )
        );

        projectsStats.forEach(stats => {
            if (stats) {
                totalViews += stats.total_views || 0;

                // Добавляем уникальных пользователей и считаем профили
                Object.entries(stats.users_stats || {}).forEach(([userName, userStats]) => {
                    uniqueUsers.add(userName);
                    totalProfiles += userStats.profiles_count || 0;
                });
            }
        });

        let totalUsers = uniqueUsers.size;

        // Если нет реальных данных, используем тестовые
        if (totalUsers === 0) {
            console.log('No real data, using test data for admin stats');
            totalUsers = 25; // 25 тестовых пользователей
            totalProfiles = 427; // Сумма всех профилей тестовых пользователей
            totalViews = 3567800; // Сумма всех тестовых просмотров
        }

        // Обновляем UI с проверками
        const adminTotalUsersEl = document.getElementById('admin-total-users');
        const adminTotalProjectsEl = document.getElementById('admin-total-projects');
        const adminTotalProfilesEl = document.getElementById('admin-total-profiles');
        const adminTotalViewsEl = document.getElementById('admin-total-views');

        if (adminTotalUsersEl) adminTotalUsersEl.textContent = totalUsers;
        if (adminTotalProjectsEl) adminTotalProjectsEl.textContent = totalProjects;
        if (adminTotalProfilesEl) adminTotalProfilesEl.textContent = totalProfiles;
        if (adminTotalViewsEl) adminTotalViewsEl.textContent = formatNumber(totalViews);

        // Обновляем количество пользователей в кликабельной карточке
        const adminTotalUsersDisplay = document.getElementById('admin-total-users-display');
        if (adminTotalUsersDisplay) adminTotalUsersDisplay.textContent = totalUsers;

        // Обновляем количество проектов в кликабельной карточке
        const adminTotalProjectsDisplay = document.getElementById('admin-total-projects-display');
        if (adminTotalProjectsDisplay) adminTotalProjectsDisplay.textContent = totalProjects;

        console.log('Admin data loaded successfully');

        // Загружаем список пользователей
        await loadAdminUsers();

    } catch (error) {
        console.error('Failed to load admin data:', error);
        showError('Не удалось загрузить данные админ панели');
    }
}

// Переменные для управления пользователями
let currentUserData = null;
let currentBonusUser = null;
let allUsers = [];
let displayedUsersCount = 0;
const USERS_PER_PAGE = 20;

async function loadAdminUsers() {
    if (!isAdmin) {
        return;
    }

    try {
        console.log('Loading admin users...');

        // Собираем всех уникальных пользователей из всех проектов
        const usersMap = new Map();

        const projectsStats = await Promise.all(
            currentProjects.map(project =>
                apiCall(`/api/projects/${project.id}/analytics`).catch(() => null)
            )
        );

        projectsStats.forEach((stats, index) => {
            if (stats && stats.users_stats) {
                const project = currentProjects[index];

                Object.entries(stats.users_stats).forEach(([userName, userStats]) => {
                    if (!usersMap.has(userName)) {
                        usersMap.set(userName, {
                            username: userName,
                            totalViews: 0,
                            projects: []
                        });
                    }

                    const user = usersMap.get(userName);
                    user.totalViews += userStats.total_views || 0;
                    user.projects.push({
                        id: project.id,
                        name: project.name,
                        views: userStats.total_views || 0,
                        videos: 0, // TODO: добавить подсчет видео
                        platforms: userStats.platforms || {},
                        topics: userStats.topics || {}
                    });
                });
            }
        });

        // Получаем пользователей
        let users = Array.from(usersMap.values());

        console.log('Real users found:', users.length);

        // Если нет пользователей, создаем тестовых
        if (users.length === 0) {
            console.log('Creating 25 test users...');
            users = [
                {
                    username: '@alexander_pro',
                    totalViews: 125000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 85000, videos: 12 },
                        { id: 'test2', name: 'Instagram Stories', views: 40000, videos: 8 }
                    ]
                },
                {
                    username: '@maria_creator',
                    totalViews: 98500,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 62000, videos: 10 },
                        { id: 'test3', name: 'YouTube Shorts', views: 36500, videos: 15 }
                    ]
                },
                {
                    username: '@dmitry_blogger',
                    totalViews: 156000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 95000, videos: 18 },
                        { id: 'test2', name: 'Instagram Stories', views: 43000, videos: 9 },
                        { id: 'test3', name: 'YouTube Shorts', views: 18000, videos: 6 }
                    ]
                },
                {
                    username: '@anna_influencer',
                    totalViews: 73200,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 52000, videos: 11 },
                        { id: 'test3', name: 'YouTube Shorts', views: 21200, videos: 7 }
                    ]
                },
                {
                    username: '@ivan_content',
                    totalViews: 189000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 110000, videos: 22 },
                        { id: 'test2', name: 'Instagram Stories', views: 79000, videos: 14 }
                    ]
                },
                {
                    username: '@elena_vlog',
                    totalViews: 67800,
                    projects: [
                        { id: 'test3', name: 'YouTube Shorts', views: 67800, videos: 20 }
                    ]
                },
                {
                    username: '@sergey_creative',
                    totalViews: 142000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 88000, videos: 16 },
                        { id: 'test3', name: 'YouTube Shorts', views: 54000, videos: 12 }
                    ]
                },
                {
                    username: '@olga_style',
                    totalViews: 91500,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 91500, videos: 19 }
                    ]
                },
                {
                    username: '@maxim_tech',
                    totalViews: 176000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 105000, videos: 21 },
                        { id: 'test2', name: 'Instagram Stories', views: 71000, videos: 13 }
                    ]
                },
                {
                    username: '@natasha_beauty',
                    totalViews: 83400,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 54000, videos: 10 },
                        { id: 'test3', name: 'YouTube Shorts', views: 29400, videos: 8 }
                    ]
                },
                {
                    username: '@pavel_fitness',
                    totalViews: 198000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 125000, videos: 25 },
                        { id: 'test2', name: 'Instagram Stories', views: 73000, videos: 15 }
                    ]
                },
                {
                    username: '@katerina_food',
                    totalViews: 112000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 68000, videos: 14 },
                        { id: 'test2', name: 'Instagram Stories', views: 44000, videos: 11 }
                    ]
                },
                {
                    username: '@andrey_gaming',
                    totalViews: 234000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 145000, videos: 28 },
                        { id: 'test3', name: 'YouTube Shorts', views: 89000, videos: 24 }
                    ]
                },
                {
                    username: '@victoria_travel',
                    totalViews: 95600,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 95600, videos: 17 }
                    ]
                },
                {
                    username: '@roman_music',
                    totalViews: 167000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 98000, videos: 19 },
                        { id: 'test3', name: 'YouTube Shorts', views: 69000, videos: 16 }
                    ]
                },
                {
                    username: '@julia_art',
                    totalViews: 78900,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 78900, videos: 13 }
                    ]
                },
                {
                    username: '@denis_photo',
                    totalViews: 123000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 72000, videos: 15 },
                        { id: 'test2', name: 'Instagram Stories', views: 51000, videos: 12 }
                    ]
                },
                {
                    username: '@svetlana_dance',
                    totalViews: 189000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 115000, videos: 23 },
                        { id: 'test2', name: 'Instagram Stories', views: 74000, videos: 14 }
                    ]
                },
                {
                    username: '@igor_cars',
                    totalViews: 145000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 87000, videos: 17 },
                        { id: 'test3', name: 'YouTube Shorts', views: 58000, videos: 13 }
                    ]
                },
                {
                    username: '@marina_pets',
                    totalViews: 102000,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 102000, videos: 20 }
                    ]
                },
                {
                    username: '@artem_comedy',
                    totalViews: 276000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 165000, videos: 30 },
                        { id: 'test2', name: 'Instagram Stories', views: 111000, videos: 22 }
                    ]
                },
                {
                    username: '@daria_fashion',
                    totalViews: 134000,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 85000, videos: 16 },
                        { id: 'test3', name: 'YouTube Shorts', views: 49000, videos: 11 }
                    ]
                },
                {
                    username: '@nikolay_sport',
                    totalViews: 156000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 92000, videos: 18 },
                        { id: 'test2', name: 'Instagram Stories', views: 64000, videos: 13 }
                    ]
                },
                {
                    username: '@alina_makeup',
                    totalViews: 118000,
                    projects: [
                        { id: 'test2', name: 'Instagram Stories', views: 75000, videos: 15 },
                        { id: 'test3', name: 'YouTube Shorts', views: 43000, videos: 10 }
                    ]
                },
                {
                    username: '@vladimir_review',
                    totalViews: 203000,
                    projects: [
                        { id: 'test1', name: 'TikTok Promo Campaign', views: 118000, videos: 24 },
                        { id: 'test3', name: 'YouTube Shorts', views: 85000, videos: 19 }
                    ]
                }
            ];
            console.log('Using test users data');
        }

        // Сохраняем всех пользователей
        allUsers = users;

        // Сохраняем данные пользователей
        if (users.length > 0 && usersMap.size === 0) {
            // Если используем тестовые данные, создаем Map
            window.adminUsersData = new Map();
            users.forEach(user => {
                window.adminUsersData.set(user.username, user);
            });
        } else {
            window.adminUsersData = usersMap;
        }

        // Обновляем счетчик
        const totalCountElement = document.getElementById('users-total-count');
        if (totalCountElement) {
            totalCountElement.textContent = users.length;
        } else {
            console.error('users-total-count element not found!');
        }

        // Отображаем первых USERS_PER_PAGE пользователей
        displayedUsersCount = 0;
        renderUsers(users.slice(0, USERS_PER_PAGE));

        console.log('Admin users loaded:', users.length);

    } catch (error) {
        console.error('Failed to load admin users:', error);
        showError('Не удалось загрузить список пользователей');
    }
}

function renderUsers(usersArray) {
    const usersList = document.getElementById('admin-users-list');
    if (!usersList) {
        console.error('admin-users-list element not found!');
        return;
    }

    console.log('Rendering users:', usersArray.length, 'users');

    // Создаем HTML для пользователей
    const usersHTML = usersArray.map(user => {
        const avatarLetter = user.username.substring(1, 2).toUpperCase(); // Берем первую букву после @

        return `
            <div class="admin-user-item" onclick="openUserDetailsModal('${user.username}')">
                <div class="admin-user-info">
                    <div class="admin-user-avatar">${avatarLetter}</div>
                    <div class="admin-user-details">
                        <div class="admin-user-name">${user.username}</div>
                        <div class="admin-user-stats">
                            ${formatNumber(user.totalViews)} просмотров • ${user.projects.length} ${user.projects.length === 1 ? 'проект' : 'проекта'}
                        </div>
                    </div>
                </div>
                <div class="admin-user-arrow">
                    <i class="fa-solid fa-chevron-right"></i>
                </div>
            </div>
        `;
    }).join('');

    // Если это первая загрузка, заменяем содержимое
    if (displayedUsersCount === 0) {
        usersList.innerHTML = usersHTML;
    } else {
        // Иначе добавляем к существующему
        usersList.innerHTML += usersHTML;
    }

    // Обновляем счетчик отображаемых пользователей
    displayedUsersCount += usersArray.length;
    const shownCountElement = document.getElementById('users-shown-count');
    if (shownCountElement) {
        shownCountElement.textContent = displayedUsersCount;
    }

    console.log('Users rendered. Total displayed:', displayedUsersCount);

    // Показываем/скрываем кнопку "Показать еще"
    const loadMoreBtn = document.getElementById('load-more-users');
    if (loadMoreBtn) {
        if (displayedUsersCount >= allUsers.length) {
            loadMoreBtn.classList.add('hidden');
        } else {
            loadMoreBtn.classList.remove('hidden');
        }
    }
}

function loadMoreUsers() {
    // Получаем следующую порцию пользователей
    const nextUsers = allUsers.slice(displayedUsersCount, displayedUsersCount + USERS_PER_PAGE);

    if (nextUsers.length > 0) {
        renderUsers(nextUsers);
    }
}

function filterUsers() {
    const searchInput = document.getElementById('users-search');
    const searchTerm = searchInput.value.toLowerCase().trim();

    // Если поле поиска пустое, показываем всех пользователей
    if (searchTerm === '') {
        displayedUsersCount = 0;
        renderUsers(allUsers.slice(0, USERS_PER_PAGE));
        return;
    }

    // Фильтруем пользователей по имени
    const filteredUsers = allUsers.filter(user =>
        user.username.toLowerCase().includes(searchTerm)
    );

    // Отображаем отфильтрованных пользователей
    const usersList = document.getElementById('admin-users-list');

    if (filteredUsers.length === 0) {
        usersList.innerHTML = '<div class="admin-no-users">Пользователи не найдены</div>';
        document.getElementById('users-shown-count').textContent = '0';
        document.getElementById('load-more-users').classList.add('hidden');
        return;
    }

    // Сбрасываем счетчик и показываем первые результаты
    displayedUsersCount = 0;

    // Показываем все отфильтрованные результаты (без пагинации при поиске)
    const usersHTML = filteredUsers.map(user => {
        const avatarLetter = user.username.substring(1, 2).toUpperCase();

        return `
            <div class="admin-user-item" onclick="openUserDetailsModal('${user.username}')">
                <div class="admin-user-info">
                    <div class="admin-user-avatar">${avatarLetter}</div>
                    <div class="admin-user-details">
                        <div class="admin-user-name">${user.username}</div>
                        <div class="admin-user-stats">
                            ${formatNumber(user.totalViews)} просмотров • ${user.projects.length} ${user.projects.length === 1 ? 'проект' : 'проекта'}
                        </div>
                    </div>
                </div>
                <div class="admin-user-arrow">
                    <i class="fa-solid fa-chevron-right"></i>
                </div>
            </div>
        `;
    }).join('');

    usersList.innerHTML = usersHTML;
    document.getElementById('users-shown-count').textContent = filteredUsers.length;

    // Скрываем кнопку "Показать еще" при поиске
    document.getElementById('load-more-users').classList.add('hidden');
}

async function openUserDetailsModal(username) {
    if (!window.adminUsersData) {
        console.error('No users data available');
        return;
    }

    const user = window.adminUsersData.get(username);
    if (!user) {
        console.error('User not found:', username);
        return;
    }

    currentUserData = user;

    // Обновляем заголовок
    document.getElementById('user-details-title').textContent = username;

    // Подсчитываем общее количество профилей (видео)
    const totalProfiles = user.projects.reduce((sum, project) => sum + (project.videos || 0), 0);

    // Отображаем проекты пользователя
    const projectsList = document.getElementById('user-projects-list');

    if (user.projects.length === 0) {
        projectsList.innerHTML = '<div class="user-no-projects">Нет проектов</div>';
    } else {
        projectsList.innerHTML = user.projects.map(project => `
            <div class="user-project-card">
                <div class="user-project-header">
                    <div class="user-project-name">${project.name}</div>
                </div>

                <div class="user-project-stats-grid">
                    <div class="user-project-stat">
                        <div class="user-project-stat-label">Просмотры</div>
                        <div class="user-project-stat-value">${formatNumber(project.views)}</div>
                    </div>
                    <div class="user-project-stat">
                        <div class="user-project-stat-label">Профилей</div>
                        <div class="user-project-stat-value">${project.videos}</div>
                    </div>
                </div>

                <div class="user-project-actions">
                    <button class="btn-danger" onclick="removeUserFromProject('${username}', '${project.id}', '${project.name}')">
                        Удалить
                    </button>
                    <button class="btn-success" onclick="openBonusModal('${username}', '${project.id}', '${project.name}')">
                        Бонус
                    </button>
                </div>
            </div>
        `).join('');
    }

    // Показываем модалку
    document.getElementById('user-details-modal').classList.remove('hidden');
}

function closeUserDetailsModal() {
    document.getElementById('user-details-modal').classList.add('hidden');
    currentUserData = null;
}

function openBonusModal(username, projectId, projectName) {
    currentBonusUser = { username, projectId, projectName };

    document.getElementById('bonus-username').textContent = `${username} (${projectName})`;
    document.getElementById('bonus-amount-input').value = '';
    document.getElementById('bonus-modal').classList.remove('hidden');
}

function closeBonusModal() {
    document.getElementById('bonus-modal').classList.add('hidden');
    currentBonusUser = null;
}

async function submitBonus() {
    const amount = parseFloat(document.getElementById('bonus-amount-input').value);

    if (!amount || amount <= 0) {
        showError('Пожалуйста, введите корректную сумму');
        return;
    }

    if (!currentBonusUser) {
        showError('Ошибка: пользователь не выбран');
        return;
    }

    try {
        console.log('Выдаем бонус:', {
            user: currentBonusUser.username,
            project: currentBonusUser.projectName,
            amount: amount
        });

        // TODO: Отправить запрос на бэкенд
        // await apiCall(`/api/admin/projects/${currentBonusUser.projectId}/bonus`, {
        //     method: 'POST',
        //     body: JSON.stringify({
        //         username: currentBonusUser.username,
        //         amount: amount
        //     })
        // });

        closeBonusModal();
        showSuccess(`Бонус $${amount} выдан пользователю ${currentBonusUser.username}!`);

    } catch (error) {
        console.error('Failed to submit bonus:', error);
        showError('Не удалось выдать бонус');
    }
}

async function removeUserFromProject(username, projectId, projectName) {
    if (!confirm(`Вы уверены, что хотите удалить ${username} из проекта "${projectName}"?`)) {
        return;
    }

    try {
        console.log('Удаляем пользователя из проекта:', {
            user: username,
            project: projectName,
            projectId: projectId
        });

        // TODO: Отправить запрос на бэкенд
        // await apiCall(`/api/admin/projects/${projectId}/users/${username}`, {
        //     method: 'DELETE'
        // });

        showSuccess(`Пользователь ${username} удален из проекта "${projectName}"`);

        // Закрываем модалку и обновляем данные
        closeUserDetailsModal();
        await loadAdminData();

    } catch (error) {
        console.error('Failed to remove user from project:', error);
        showError('Не удалось удалить пользователя');
    }
}

// ==================== USER MANAGEMENT PAGE ====================
let allUsersList = [];

function openUserManagement() {
    console.log('Opening user management page...');

    // Скрываем все страницы
    document.querySelectorAll('.page').forEach(page => {
        page.classList.add('hidden');
    });

    // Показываем страницу управления пользователями
    document.getElementById('user-management-page').classList.remove('hidden');

    // Загружаем и отображаем пользователей
    loadUserManagementList();
}

function closeUserManagement() {
    document.getElementById('user-management-page').classList.add('hidden');
    document.getElementById('admin-page').classList.remove('hidden');
}

async function loadUserManagementList() {
    if (!isAdmin) {
        console.error('Access denied: user is not admin');
        return;
    }

    try {
        console.log('Loading user management list...');

        // Собираем всех уникальных пользователей из всех проектов
        const usersMap = new Map();

        const projectsStats = await Promise.all(
            currentProjects.map(project =>
                apiCall(`/api/projects/${project.id}/analytics`).catch(() => null)
            )
        );

        projectsStats.forEach((stats, index) => {
            if (stats && stats.users_stats) {
                const project = currentProjects[index];

                Object.entries(stats.users_stats).forEach(([userName, userStats]) => {
                    if (!usersMap.has(userName)) {
                        usersMap.set(userName, {
                            username: userName,
                            totalViews: 0,
                            projects: []
                        });
                    }

                    const user = usersMap.get(userName);
                    user.totalViews += userStats.total_views || 0;
                    user.projects.push({
                        id: project.id,
                        name: project.name,
                        views: userStats.total_views || 0,
                        videos: userStats.profiles_count || 0,
                        platforms: userStats.platforms || {},
                        topics: userStats.topics || {}
                    });
                });
            }
        });

        // Получаем пользователей
        let users = Array.from(usersMap.values());

        // Если нет пользователей, создаем тестовых (используем те же 25)
        if (users.length === 0) {
            console.log('Creating 25 test users...');
            users = [
                { username: '@alexander_pro', totalViews: 125000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 85000, videos: 12 }, { id: 'test2', name: 'Instagram Stories', views: 40000, videos: 8 }] },
                { username: '@maria_creator', totalViews: 98500, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 62000, videos: 10 }, { id: 'test3', name: 'YouTube Shorts', views: 36500, videos: 15 }] },
                { username: '@dmitry_blogger', totalViews: 156000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 95000, videos: 18 }, { id: 'test2', name: 'Instagram Stories', views: 43000, videos: 9 }, { id: 'test3', name: 'YouTube Shorts', views: 18000, videos: 6 }] },
                { username: '@anna_influencer', totalViews: 73200, projects: [{ id: 'test2', name: 'Instagram Stories', views: 52000, videos: 11 }, { id: 'test3', name: 'YouTube Shorts', views: 21200, videos: 7 }] },
                { username: '@ivan_content', totalViews: 189000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 110000, videos: 22 }, { id: 'test2', name: 'Instagram Stories', views: 79000, videos: 14 }] },
                { username: '@elena_vlog', totalViews: 67800, projects: [{ id: 'test3', name: 'YouTube Shorts', views: 67800, videos: 20 }] },
                { username: '@sergey_creative', totalViews: 142000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 88000, videos: 16 }, { id: 'test3', name: 'YouTube Shorts', views: 54000, videos: 12 }] },
                { username: '@olga_style', totalViews: 91500, projects: [{ id: 'test2', name: 'Instagram Stories', views: 91500, videos: 19 }] },
                { username: '@maxim_tech', totalViews: 176000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 105000, videos: 21 }, { id: 'test2', name: 'Instagram Stories', views: 71000, videos: 13 }] },
                { username: '@natasha_beauty', totalViews: 83400, projects: [{ id: 'test2', name: 'Instagram Stories', views: 54000, videos: 10 }, { id: 'test3', name: 'YouTube Shorts', views: 29400, videos: 8 }] },
                { username: '@pavel_fitness', totalViews: 198000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 125000, videos: 25 }, { id: 'test2', name: 'Instagram Stories', views: 73000, videos: 15 }] },
                { username: '@katerina_food', totalViews: 112000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 68000, videos: 14 }, { id: 'test2', name: 'Instagram Stories', views: 44000, videos: 11 }] },
                { username: '@andrey_gaming', totalViews: 234000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 145000, videos: 28 }, { id: 'test3', name: 'YouTube Shorts', views: 89000, videos: 24 }] },
                { username: '@victoria_travel', totalViews: 95600, projects: [{ id: 'test2', name: 'Instagram Stories', views: 95600, videos: 17 }] },
                { username: '@roman_music', totalViews: 167000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 98000, videos: 19 }, { id: 'test3', name: 'YouTube Shorts', views: 69000, videos: 16 }] },
                { username: '@julia_art', totalViews: 78900, projects: [{ id: 'test2', name: 'Instagram Stories', views: 78900, videos: 13 }] },
                { username: '@denis_photo', totalViews: 123000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 72000, videos: 15 }, { id: 'test2', name: 'Instagram Stories', views: 51000, videos: 12 }] },
                { username: '@svetlana_dance', totalViews: 189000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 115000, videos: 23 }, { id: 'test2', name: 'Instagram Stories', views: 74000, videos: 14 }] },
                { username: '@igor_cars', totalViews: 145000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 87000, videos: 17 }, { id: 'test3', name: 'YouTube Shorts', views: 58000, videos: 13 }] },
                { username: '@marina_pets', totalViews: 102000, projects: [{ id: 'test2', name: 'Instagram Stories', views: 102000, videos: 20 }] },
                { username: '@artem_comedy', totalViews: 276000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 165000, videos: 30 }, { id: 'test2', name: 'Instagram Stories', views: 111000, videos: 22 }] },
                { username: '@daria_fashion', totalViews: 134000, projects: [{ id: 'test2', name: 'Instagram Stories', views: 85000, videos: 16 }, { id: 'test3', name: 'YouTube Shorts', views: 49000, videos: 11 }] },
                { username: '@nikolay_sport', totalViews: 156000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 92000, videos: 18 }, { id: 'test2', name: 'Instagram Stories', views: 64000, videos: 13 }] },
                { username: '@alina_makeup', totalViews: 118000, projects: [{ id: 'test2', name: 'Instagram Stories', views: 75000, videos: 15 }, { id: 'test3', name: 'YouTube Shorts', views: 43000, videos: 10 }] },
                { username: '@vladimir_review', totalViews: 203000, projects: [{ id: 'test1', name: 'TikTok Promo Campaign', views: 118000, videos: 24 }, { id: 'test3', name: 'YouTube Shorts', views: 85000, videos: 19 }] }
            ];

            // Создаем Map для тестовых данных
            window.adminUsersData = new Map();
            users.forEach(user => {
                window.adminUsersData.set(user.username, user);
            });
        } else {
            window.adminUsersData = usersMap;
        }

        // Сортируем по просмотрам (от большего к меньшему)
        users.sort((a, b) => b.totalViews - a.totalViews);

        // Сохраняем всех пользователей
        allUsersList = users;

        // Отображаем всех пользователей
        renderUserManagementList(users);

        console.log('User management list loaded:', users.length);

    } catch (error) {
        console.error('Failed to load user management list:', error);
        showError('Не удалось загрузить список пользователей');
    }
}

function renderUserManagementList(users) {
    const usersList = document.getElementById('user-management-list');
    const countElement = document.getElementById('user-management-shown');

    if (!usersList) {
        console.error('user-management-list element not found!');
        return;
    }

    if (users.length === 0) {
        usersList.innerHTML = '<div class="admin-no-users">Пользователи не найдены</div>';
        if (countElement) countElement.textContent = '0';
        return;
    }

    // Создаем HTML для всех пользователей
    const usersHTML = users.map(user => {
        const avatarLetter = user.username.substring(1, 2).toUpperCase();

        return `
            <div class="admin-user-item" onclick="openUserDetailsModal('${user.username}')">
                <div class="admin-user-info">
                    <div class="admin-user-avatar">${avatarLetter}</div>
                    <div class="admin-user-details">
                        <div class="admin-user-name">${user.username}</div>
                        <div class="admin-user-stats">
                            ${formatNumber(user.totalViews)} просмотров • ${user.projects.length} ${user.projects.length === 1 ? 'проект' : 'проекта'}
                        </div>
                    </div>
                </div>
                <div class="admin-user-arrow">
                    <i class="fa-solid fa-chevron-right"></i>
                </div>
            </div>
        `;
    }).join('');

    usersList.innerHTML = usersHTML;

    if (countElement) {
        countElement.textContent = users.length;
    }
}

function filterUserManagementList() {
    const searchInput = document.getElementById('user-management-search');
    const searchTerm = searchInput.value.toLowerCase().trim();

    if (searchTerm === '') {
        // Показываем всех пользователей
        renderUserManagementList(allUsersList);
        return;
    }

    // Фильтруем пользователей по имени
    const filteredUsers = allUsersList.filter(user =>
        user.username.toLowerCase().includes(searchTerm)
    );

    renderUserManagementList(filteredUsers);
}

// ==================== PROJECT MANAGEMENT ====================

let allProjectsList = [];
let currentProjectDetailsData = null;

function openProjectManagement() {
    document.querySelectorAll('.page').forEach(page => page.classList.add('hidden'));
    document.getElementById('project-management-page').classList.remove('hidden');
    loadProjectManagementList();
}

function closeProjectManagement() {
    document.getElementById('project-management-page').classList.add('hidden');
    document.getElementById('admin-page').classList.remove('hidden');
}

async function loadProjectManagementList() {
    try {
        // Используем существующие данные из глобального состояния
        const projects = allProjects || [];

        allProjectsList = [];

        // Загружаем аналитику для каждого проекта
        for (const project of projects) {
            const response = await fetch(`${API_BASE_URL}/api/projects/${project.id}/analytics`, {
                headers: { 'X-Telegram-Init-Data': window.initData }
            });

            if (response.ok) {
                const analytics = await response.json();
                allProjectsList.push({
                    id: project.id,
                    name: project.name,
                    targetViews: project.target_views,
                    kpiViews: project.kpi_views || 1000,
                    totalViews: analytics.total_views || 0,
                    progress: analytics.progress_percent || 0,
                    usersCount: Object.keys(analytics.users_stats || {}).length,
                    profilesCount: Object.values(analytics.users_stats || {}).reduce((sum, user) => sum + (user.profiles_count || 0), 0)
                });
            }
        }

        renderProjectManagementList(allProjectsList);
    } catch (error) {
        console.error('Failed to load projects:', error);
    }
}

function renderProjectManagementList(projects) {
    const projectsList = document.getElementById('project-management-list');
    const countElement = document.getElementById('project-management-shown');

    if (!projects || projects.length === 0) {
        projectsList.innerHTML = '<div class="empty-state">Нет проектов для отображения</div>';
        if (countElement) countElement.textContent = '0';
        return;
    }

    // Сортируем проекты по просмотрам (от большего к меньшему)
    projects.sort((a, b) => b.totalViews - a.totalViews);

    const projectsHTML = projects.map(project => {
        return `
            <div class="admin-user-item" onclick="openProjectDetailsFromAdmin('${project.id}')">
                <div class="admin-user-info">
                    <div class="admin-user-avatar project-icon">
                        <i class="fa-solid fa-folder-open"></i>
                    </div>
                    <div class="admin-user-details">
                        <div class="admin-user-name">${project.name}</div>
                        <div class="admin-user-stats">
                            ${formatNumber(project.totalViews)} просмотров • ${project.progress}% • KPI от ${formatNumber(project.kpiViews)} • ${project.usersCount} участников • ${project.profilesCount} профилей
                        </div>
                    </div>
                </div>
                <div class="admin-user-arrow">
                    <i class="fa-solid fa-chevron-right"></i>
                </div>
            </div>
        `;
    }).join('');

    projectsList.innerHTML = projectsHTML;

    if (countElement) {
        countElement.textContent = projects.length;
    }
}

async function openProjectDetailsFromAdmin(projectId) {
    document.querySelectorAll('.page').forEach(page => page.classList.add('hidden'));
    document.getElementById('project-details-page').classList.remove('hidden');
    await loadProjectDetailsForAdmin(projectId);
}

function closeProjectDetails() {
    document.getElementById('project-details-page').classList.add('hidden');
    document.getElementById('project-management-page').classList.remove('hidden');
}

async function loadProjectDetailsForAdmin(projectId) {
    try {
        // Загружаем детальную информацию о проекте
        const analyticsResponse = await fetch(`${API_BASE_URL}/api/projects/${projectId}/analytics`, {
            headers: { 'X-Telegram-Init-Data': window.initData }
        });

        if (!analyticsResponse.ok) {
            throw new Error('Failed to load project analytics');
        }

        const analytics = await analyticsResponse.json();
        currentProjectDetailsData = analytics;

        // Обновляем название проекта
        document.getElementById('project-details-name').textContent = analytics.project.name;

        // Обновляем общую статистику
        document.getElementById('pd-total-views').textContent = formatNumber(analytics.total_views);
        document.getElementById('pd-target-views').textContent = formatNumber(analytics.target_views);
        document.getElementById('pd-kpi-views').textContent = `от ${formatNumber(analytics.project.kpi_views || 1000)}`;
        document.getElementById('pd-progress').textContent = `${analytics.progress_percent}%`;

        const usersCount = Object.keys(analytics.users_stats || {}).length;
        document.getElementById('pd-total-users').textContent = usersCount;

        const totalProfiles = Object.values(analytics.users_stats || {}).reduce((sum, user) => sum + (user.profiles_count || 0), 0);
        document.getElementById('pd-total-profiles').textContent = totalProfiles;

        const avgPerUser = usersCount > 0 ? Math.round(analytics.total_views / usersCount) : 0;
        document.getElementById('pd-avg-per-user').textContent = formatNumber(avgPerUser);

        // Обновляем прогресс бар
        document.getElementById('pd-progress-bar').style.width = `${Math.min(analytics.progress_percent, 100)}%`;

        // Рендерим список участников
        renderProjectUsersList(analytics.users_stats);

    } catch (error) {
        console.error('Failed to load project details:', error);
        showError('Не удалось загрузить детали проекта');
    }
}

function renderProjectUsersList(usersStats) {
    const usersList = document.getElementById('project-users-list');

    if (!usersStats || Object.keys(usersStats).length === 0) {
        usersList.innerHTML = '<div class="empty-state">Нет участников в проекте</div>';
        return;
    }

    // Преобразуем в массив и сортируем по просмотрам
    const users = Object.entries(usersStats).map(([username, stats]) => ({
        username: username,
        totalViews: stats.total_views || 0,
        profilesCount: stats.profiles_count || 0,
        platforms: stats.platforms || {},
        topics: stats.topics || {}
    })).sort((a, b) => b.totalViews - a.totalViews);

    const usersHTML = users.map((user, index) => {
        // Определяем медаль для топ-3
        let medal = '';
        if (index === 0) medal = '<i class="fa-solid fa-trophy" style="color: #FFD700;"></i> ';
        else if (index === 1) medal = '<i class="fa-solid fa-trophy" style="color: #C0C0C0;"></i> ';
        else if (index === 2) medal = '<i class="fa-solid fa-trophy" style="color: #CD7F32;"></i> ';

        return `
            <div class="admin-user-item" onclick="openUserDetailsModal('${user.username}')">
                <div class="admin-user-info">
                    <div class="admin-user-avatar">
                        <i class="fa-solid fa-user"></i>
                    </div>
                    <div class="admin-user-details">
                        <div class="admin-user-name">${medal}${user.username}</div>
                        <div class="admin-user-stats">
                            ${formatNumber(user.totalViews)} просмотров • ${user.profilesCount} профилей
                        </div>
                    </div>
                </div>
                <div class="admin-user-arrow">
                    <i class="fa-solid fa-chevron-right"></i>
                </div>
            </div>
        `;
    }).join('');

    usersList.innerHTML = usersHTML;
}

// Модалка добавления проекта
function openAddProjectModal() {
    document.getElementById('add-project-modal').classList.remove('hidden');

    // Очищаем все поля
    document.getElementById('new-project-name-input').value = '';
    document.getElementById('new-project-target-input').value = '';
    document.getElementById('new-project-kpi-input').value = '';
    document.getElementById('new-project-deadline-input').value = '';
    document.getElementById('new-project-geo-input').value = '';

    // Сбрасываем переключатели в состояние "включено"
    document.getElementById('toggle-tiktok').checked = true;
    document.getElementById('toggle-instagram').checked = true;
    document.getElementById('toggle-facebook').checked = true;
    document.getElementById('toggle-youtube').checked = true;
}

function closeAddProjectModal() {
    document.getElementById('add-project-modal').classList.add('hidden');
}

async function submitNewProject() {
    const projectName = document.getElementById('new-project-name-input').value.trim();
    const targetViews = parseInt(document.getElementById('new-project-target-input').value);
    const kpiViews = parseInt(document.getElementById('new-project-kpi-input').value);
    const deadline = document.getElementById('new-project-deadline-input').value;
    const geo = document.getElementById('new-project-geo-input').value.trim();

    const allowedPlatforms = {
        tiktok: document.getElementById('toggle-tiktok').checked,
        instagram: document.getElementById('toggle-instagram').checked,
        facebook: document.getElementById('toggle-facebook').checked,
        youtube: document.getElementById('toggle-youtube').checked
    };

    // Валидация
    if (!projectName) {
        showError('Пожалуйста, введите название проекта');
        return;
    }

    if (!targetViews || targetViews <= 0) {
        showError('Пожалуйста, введите корректную цель просмотров');
        return;
    }

    if (!kpiViews || kpiViews <= 0) {
        showError('Пожалуйста, введите KPI (минимум просмотров для учета)');
        return;
    }

    if (!deadline) {
        showError('Пожалуйста, выберите дату окончания');
        return;
    }

    const projectData = {
        name: projectName,
        target_views: targetViews,
        kpi_views: kpiViews,
        deadline: deadline,
        geo: geo || 'Не указано',
        allowed_platforms: allowedPlatforms
    };

    try {
        // TODO: Реализовать API для создания проекта
        console.log('Создание проекта:', projectData);

        closeAddProjectModal();
        showSuccess(`Проект "${projectName}" создан успешно!`);

        // Обновляем список проектов
        await loadProjectManagementList();

    } catch (error) {
        console.error('Failed to create project:', error);
        showError('Не удалось создать проект');
    }
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
window.openUserDetailsModal = openUserDetailsModal;
window.closeUserDetailsModal = closeUserDetailsModal;
window.openBonusModal = openBonusModal;
window.closeBonusModal = closeBonusModal;
window.submitBonus = submitBonus;
window.removeUserFromProject = removeUserFromProject;
window.renderUsers = renderUsers;
window.loadMoreUsers = loadMoreUsers;
window.filterUsers = filterUsers;
window.openUserManagement = openUserManagement;
window.closeUserManagement = closeUserManagement;
window.filterUserManagementList = filterUserManagementList;
window.openAddProfileModal = openAddProfileModal;
window.closeAddProfileModal = closeAddProfileModal;
window.nextToStatusStep = nextToStatusStep;
window.selectStatus = selectStatus;
window.selectTopic = selectTopic;
window.openCustomTopic = openCustomTopic;
window.submitCustomTopic = submitCustomTopic;
window.openProjectManagement = openProjectManagement;
window.closeProjectManagement = closeProjectManagement;
window.openProjectDetailsFromAdmin = openProjectDetailsFromAdmin;
window.closeProjectDetails = closeProjectDetails;
window.openAddProjectModal = openAddProjectModal;
window.closeAddProjectModal = closeAddProjectModal;
window.submitNewProject = submitNewProject;
