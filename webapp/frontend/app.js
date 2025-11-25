// ==================== CONFIGURATION ====================
const API_BASE_URL = 'https://view-counter-webapp-production.up.railway.app'; // Backend URL на Railway
let currentUser = null;
let currentProjectId = null;
let platformChart = null;
let topicChart = null;
let myPlatformChart = null;
let myTopicChart = null;

// ==================== TELEGRAM WEBAPP INITIALIZATION ====================
const tg = window.Telegram.WebApp;

// Инициализация Telegram WebApp
function initTelegramApp() {
    tg.ready();
    tg.expand();

    // Применяем тему Telegram
    document.body.style.backgroundColor = tg.themeParams.bg_color || '#ffffff';

    if (tg.colorScheme === 'dark') {
        document.body.classList.add('theme-dark');
    }

    // Показываем главную кнопку если нужно
    tg.MainButton.setText('Обновить').hide();
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

// ==================== INITIALIZATION ====================
async function init() {
    try {
        initTelegramApp();

        // Получаем данные пользователя
        const data = await apiCall('/api/me');
        currentUser = data.user;

        // Устанавливаем информацию о пользователе
        document.getElementById('user-name').textContent =
            currentUser.first_name + (currentUser.last_name ? ' ' + currentUser.last_name : '');

        // Аватар с первой буквой имени
        const avatar = document.getElementById('user-avatar');
        avatar.textContent = currentUser.first_name[0].toUpperCase();

        // Загружаем проекты
        await loadProjects(data.projects);

        // Устанавливаем текущий проект если есть
        if (data.current_project_id) {
            currentProjectId = data.current_project_id;
            document.getElementById('project-select').value = currentProjectId;
            await loadProjectAnalytics(currentProjectId);
        }

        // Загружаем личную статистику
        await loadMyAnalytics();

        // Скрываем загрузку, показываем контент
        document.getElementById('loading').classList.add('hidden');
        document.getElementById('main-page').classList.remove('hidden');

    } catch (error) {
        console.error('Initialization failed:', error);
        showError('Ошибка загрузки данных');
    }
}

// ==================== PROJECTS ====================
async function loadProjects(projects) {
    const projectSelect = document.getElementById('project-select');
    const projectsList = document.getElementById('projects-list');

    // Очищаем
    projectSelect.innerHTML = '<option value="">Выберите проект...</option>';
    projectsList.innerHTML = '';

    if (projects.length === 0) {
        projectsList.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📂</div>
                <div class="empty-state-text">У вас пока нет проектов</div>
            </div>
        `;
        return;
    }

    projects.forEach(project => {
        // Добавляем в select
        const option = document.createElement('option');
        option.value = project.id;
        option.textContent = project.name;
        projectSelect.appendChild(option);

        // Добавляем в список проектов
        const projectItem = document.createElement('div');
        projectItem.className = 'project-item';
        projectItem.innerHTML = `
            <div class="project-name">${project.name}</div>
            <div class="project-meta">
                <div class="project-meta-item">
                    <span>🎯</span>
                    <span>${formatNumber(project.target_views)} просмотров</span>
                </div>
                <div class="project-meta-item">
                    <span>🌍</span>
                    <span>${project.geo || 'Не указано'}</span>
                </div>
                <div class="project-meta-item">
                    <span>📅</span>
                    <span>${formatDate(project.start_date)} — ${formatDate(project.end_date)}</span>
                </div>
            </div>
        `;
        projectItem.onclick = () => {
            currentProjectId = project.id;
            document.getElementById('project-select').value = project.id;
            loadProjectAnalytics(project.id);
            switchTab('stats');
        };
        projectsList.appendChild(projectItem);
    });
}

// ==================== PROJECT ANALYTICS ====================
async function loadProjectAnalytics(projectId) {
    try {
        const data = await apiCall(`/api/projects/${projectId}/analytics`);

        // Обновляем статистику
        document.getElementById('total-views').textContent = formatNumber(data.total_views);
        document.getElementById('target-views').textContent = formatNumber(data.target_views);
        document.getElementById('progress').textContent = data.progress_percent.toFixed(1) + '%';

        // Обновляем прогресс бар
        const progressFill = document.getElementById('progress-fill');
        progressFill.style.width = Math.min(data.progress_percent, 100) + '%';
        document.getElementById('progress-text').textContent =
            `${formatNumber(data.total_views)} из ${formatNumber(data.target_views)}`;

        // График по платформам
        updatePlatformChart(data.platform_stats);

        // График по тематикам
        updateTopicChart(data.topic_stats);

        // Топ участников
        updateLeaderboard(data.users_stats);

    } catch (error) {
        console.error('Failed to load project analytics:', error);
    }
}

// ==================== MY ANALYTICS ====================
async function loadMyAnalytics(projectId = null) {
    try {
        const endpoint = projectId
            ? `/api/my-analytics?project_id=${projectId}`
            : '/api/my-analytics';

        const data = await apiCall(endpoint);

        document.getElementById('my-total-views').textContent = formatNumber(data.total_views);
        document.getElementById('my-profiles').textContent = data.profiles_count;

        // Мои графики
        updateMyPlatformChart(data.platform_stats);
        updateMyTopicChart(data.topic_stats);

    } catch (error) {
        console.error('Failed to load my analytics:', error);
    }
}

// ==================== CHARTS ====================
function updatePlatformChart(platformStats) {
    const ctx = document.getElementById('platformChart');

    const data = {
        labels: ['TikTok', 'Instagram', 'Facebook', 'YouTube'],
        datasets: [{
            label: 'Просмотры',
            data: [
                platformStats.tiktok || 0,
                platformStats.instagram || 0,
                platformStats.facebook || 0,
                platformStats.youtube || 0
            ],
            backgroundColor: [
                'rgba(255, 0, 80, 0.8)',
                'rgba(131, 58, 180, 0.8)',
                'rgba(24, 119, 242, 0.8)',
                'rgba(255, 0, 0, 0.8)'
            ],
            borderColor: [
                'rgb(255, 0, 80)',
                'rgb(131, 58, 180)',
                'rgb(24, 119, 242)',
                'rgb(255, 0, 0)'
            ],
            borderWidth: 2
        }]
    };

    if (platformChart) {
        platformChart.data = data;
        platformChart.update();
    } else {
        platformChart = new Chart(ctx, {
            type: 'doughnut',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 15,
                            font: {
                                size: 13,
                                weight: '500'
                            }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.label + ': ' + formatNumber(context.parsed);
                            }
                        }
                    }
                }
            }
        });
    }
}

function updateTopicChart(topicStats) {
    const ctx = document.getElementById('topicChart');

    const sortedTopics = Object.entries(topicStats)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 10); // Топ 10 тематик

    const labels = sortedTopics.map(([topic]) => topic);
    const values = sortedTopics.map(([, views]) => views);

    const data = {
        labels: labels,
        datasets: [{
            label: 'Просмотры',
            data: values,
            backgroundColor: 'rgba(102, 126, 234, 0.8)',
            borderColor: 'rgb(102, 126, 234)',
            borderWidth: 2
        }]
    };

    if (topicChart) {
        topicChart.data = data;
        topicChart.update();
    } else {
        topicChart = new Chart(ctx, {
            type: 'bar',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: true,
                indexAxis: 'y',
                plugins: {
                    legend: {
                        display: false
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return formatNumber(context.parsed.x) + ' просмотров';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: {
                            callback: function(value) {
                                return formatNumber(value);
                            }
                        }
                    }
                }
            }
        });
    }
}

function updateMyPlatformChart(platformStats) {
    const ctx = document.getElementById('myPlatformChart');

    const data = {
        labels: ['TikTok', 'Instagram', 'Facebook', 'YouTube'],
        datasets: [{
            label: 'Просмотры',
            data: [
                platformStats.tiktok || 0,
                platformStats.instagram || 0,
                platformStats.facebook || 0,
                platformStats.youtube || 0
            ],
            backgroundColor: [
                'rgba(255, 0, 80, 0.8)',
                'rgba(131, 58, 180, 0.8)',
                'rgba(24, 119, 242, 0.8)',
                'rgba(255, 0, 0, 0.8)'
            ]
        }]
    };

    if (myPlatformChart) {
        myPlatformChart.data = data;
        myPlatformChart.update();
    } else {
        myPlatformChart = new Chart(ctx, {
            type: 'pie',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }
}

function updateMyTopicChart(topicStats) {
    const ctx = document.getElementById('myTopicChart');

    const sortedTopics = Object.entries(topicStats)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5);

    const labels = sortedTopics.map(([topic]) => topic);
    const values = sortedTopics.map(([, views]) => views);

    const data = {
        labels: labels,
        datasets: [{
            label: 'Просмотры',
            data: values,
            backgroundColor: 'rgba(17, 153, 142, 0.8)',
            borderColor: 'rgb(17, 153, 142)',
            borderWidth: 2
        }]
    };

    if (myTopicChart) {
        myTopicChart.data = data;
        myTopicChart.update();
    } else {
        myTopicChart = new Chart(ctx, {
            type: 'bar',
            data: data,
            options: {
                responsive: true,
                maintainAspectRatio: true,
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
}

// ==================== LEADERBOARD ====================
function updateLeaderboard(usersStats) {
    const leaderboard = document.getElementById('leaderboard');
    leaderboard.innerHTML = '';

    // Сортируем пользователей по просмотрам
    const sortedUsers = Object.entries(usersStats)
        .sort((a, b) => b[1].total_views - a[1].total_views)
        .slice(0, 10); // Топ 10

    if (sortedUsers.length === 0) {
        leaderboard.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">🏆</div>
                <div class="empty-state-text">Нет данных</div>
            </div>
        `;
        return;
    }

    sortedUsers.forEach(([username, stats], index) => {
        const medals = ['🥇', '🥈', '🥉'];
        const rankEmoji = index < 3 ? medals[index] : `${index + 1}.`;

        const item = document.createElement('div');
        item.className = 'leader-item';
        item.innerHTML = `
            <div class="leader-rank">${rankEmoji}</div>
            <div class="leader-info">
                <div class="leader-name">${username}</div>
                <div class="leader-stats">
                    ${Object.entries(stats.platforms)
                        .filter(([, views]) => views > 0)
                        .map(([platform, views]) => {
                            const icons = {
                                tiktok: '🎵',
                                instagram: '📷',
                                facebook: '📘',
                                youtube: '▶️'
                            };
                            return `${icons[platform]} ${formatNumber(views)}`;
                        })
                        .join(' • ')}
                </div>
            </div>
            <div class="leader-views">${formatNumber(stats.total_views)}</div>
        `;
        leaderboard.appendChild(item);
    });
}

// ==================== TAB NAVIGATION ====================
function switchTab(tabName) {
    // Убираем active со всех табов и контента
    document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    // Добавляем active к выбранному табу
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');
    document.getElementById(`${tabName}-tab`).classList.add('active');
}

// ==================== EVENT LISTENERS ====================
document.addEventListener('DOMContentLoaded', () => {
    // Навигация по табам
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchTab(tabName);
        });
    });

    // Выбор проекта
    document.getElementById('project-select').addEventListener('change', (e) => {
        const projectId = e.target.value;
        if (projectId) {
            currentProjectId = projectId;
            loadProjectAnalytics(projectId);
            loadMyAnalytics(projectId);
        }
    });

    // Инициализация
    init();
});

// ==================== UTILITY FUNCTIONS ====================
function formatNumber(num) {
    if (!num) return '0';
    if (num >= 1000000) {
        return (num / 1000000).toFixed(1) + 'M';
    }
    if (num >= 1000) {
        return (num / 1000).toFixed(1) + 'K';
    }
    return num.toLocaleString('ru-RU');
}

function formatDate(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function showError(message) {
    tg.showAlert(message);
}

// ==================== HAPTIC FEEDBACK ====================
function hapticFeedback() {
    if (tg.HapticFeedback) {
        tg.HapticFeedback.impactOccurred('light');
    }
}

// Добавляем haptic feedback к кнопкам
document.addEventListener('click', (e) => {
    if (e.target.matches('button, .nav-tab, .project-item, .leader-item')) {
        hapticFeedback();
    }
});
