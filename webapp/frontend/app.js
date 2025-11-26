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

function openAddProfileModal() {
    const modal = document.getElementById('add-profile-modal');
    modal.classList.remove('hidden');
    // Очищаем поле ввода
    document.getElementById('profile-url-input').value = '';
}

function closeAddProfileModal() {
    const modal = document.getElementById('add-profile-modal');
    modal.classList.add('hidden');
}

async function submitProfile() {
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

    try {
        // TODO: Отправить запрос на бэкенд для добавления профиля
        // Пока просто показываем успешное сообщение и закрываем модалку

        console.log('Добавляем профиль:', profileUrl);

        // Закрываем модалку
        closeAddProfileModal();

        // Показываем успешное сообщение
        showSuccess('Профиль отправлен на обработку!');

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
        loadAdminData();
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
        let totalUsers = 0;
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
                const usersCount = Object.keys(stats.users_stats || {}).length;
                totalProfiles += usersCount;
                totalUsers = Math.max(totalUsers, usersCount); // Приблизительная оценка
            }
        });

        // Обновляем UI
        document.getElementById('admin-total-users').textContent = totalUsers;
        document.getElementById('admin-total-projects').textContent = totalProjects;
        document.getElementById('admin-total-profiles').textContent = totalProfiles;
        document.getElementById('admin-total-views').textContent = formatNumber(totalViews);

        console.log('Admin data loaded successfully');

    } catch (error) {
        console.error('Failed to load admin data:', error);
        showError('Не удалось загрузить данные админ панели');
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
