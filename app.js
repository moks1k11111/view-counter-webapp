// ==================== CONFIGURATION ====================
// Version: 1.5.0 - Updated 2025-12-05 - Added stats refresh feature with platform selection
const API_BASE_URL = 'https://view-counter-api.onrender.com';
const ADMIN_IDS = [873564841]; // ID администраторов
let currentUser = null;
let currentProjects = [];
let isAdmin = false;
let projectOpenedFrom = 'home-page'; // Stores actual page ID: 'home-page', 'projects-page', 'project-management-page', etc.
let projectManagementOpenedFrom = 'admin-page'; // Stores page ID from which project management was opened

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

        console.log('API Call:', endpoint, 'Init Data length:', (tg.initData || '').length);

        const response = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers
        });

        if (!response.ok) {
            const errorText = await response.text();
            console.error('API Error Response:', response.status, errorText);

            // Пытаемся распарсить JSON ошибку для извлечения detail
            let errorMessage;
            try {
                const errorJson = JSON.parse(errorText);
                errorMessage = errorJson.detail || errorJson.message || errorText;
            } catch (e) {
                errorMessage = errorText || response.statusText;
            }

            throw new Error(errorMessage);
        }

        return await response.json();
    } catch (error) {
        console.error('API Call failed:', error);
        showError(error.message);
        throw error;
    }
}

// ==================== UI FUNCTIONS ====================
function showNotification(message, type = 'info') {
    console.log(`[${type.toUpperCase()}] ${message}`);

    // Define color schemes for different notification types
    const themes = {
        success: {
            background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
            shadow: 'rgba(102, 126, 234, 0.3)',
            icon: '✅'
        },
        error: {
            background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
            shadow: 'rgba(245, 87, 108, 0.3)',
            icon: '❌'
        },
        info: {
            background: 'linear-gradient(135deg, #4facfe 0%, #00f2fe 100%)',
            shadow: 'rgba(79, 172, 254, 0.3)',
            icon: 'ℹ️'
        },
        warning: {
            background: 'linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%)',
            shadow: 'rgba(253, 203, 110, 0.3)',
            icon: '⚠️'
        }
    };

    const theme = themes[type] || themes.info;

    // Create toast notification
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: ${theme.background};
        color: white;
        padding: 15px 25px;
        border-radius: 12px;
        z-index: 9999;
        font-weight: 600;
        box-shadow: 0 10px 30px ${theme.shadow};
        max-width: 80%;
        text-align: center;
    `;
    notification.textContent = `${theme.icon} ${message}`;
    document.body.appendChild(notification);

    // Remove after 4 seconds
    setTimeout(() => {
        notification.remove();
    }, 4000);
}

function showError(message) {
    // Redirect to showNotification for consistency
    showNotification(message, 'error');
}

function formatNumber(num) {
    // Показываем точное число без округления с разделителями тысяч
    return num.toLocaleString('en-US');
}

function renderPlatformIcons(allowedPlatforms) {
    // Генерирует HTML для иконок социальных сетей на основе allowed_platforms
    if (!allowedPlatforms) {
        // Если не указано, показываем все
        allowedPlatforms = { tiktok: true, instagram: true, facebook: true, youtube: true, threads: true };
    }

    let iconsHTML = '';
    if (allowedPlatforms.tiktok) {
        iconsHTML += '<div class="platform-icon tiktok" title="TikTok"><i class="fa-brands fa-tiktok"></i></div>';
    }
    if (allowedPlatforms.instagram) {
        iconsHTML += '<div class="platform-icon instagram" title="Instagram"><i class="fa-brands fa-instagram"></i></div>';
    }
    if (allowedPlatforms.youtube) {
        iconsHTML += '<div class="platform-icon youtube" title="YouTube"><i class="fa-brands fa-youtube"></i></div>';
    }
    if (allowedPlatforms.facebook) {
        iconsHTML += '<div class="platform-icon facebook" title="Facebook"><i class="fa-brands fa-facebook"></i></div>';
    }
    if (allowedPlatforms.threads) {
        iconsHTML += '<div class="platform-icon threads" title="Threads"><i class="fa-brands fa-threads"></i></div>';
    }

    return iconsHTML;
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
        return 'Не обновлялось';
    }

    const now = new Date();
    const lastUpdate = new Date(lastUpdateTime);
    const diffMs = now - lastUpdate;
    const diffSeconds = Math.floor(diffMs / 1000);
    const diffMinutes = Math.floor(diffMs / (1000 * 60));
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffSeconds < 60) {
        return 'Обновлено только что';
    } else if (diffMinutes < 60) {
        return `Обновлено ${diffMinutes} мин. назад`;
    } else if (diffHours < 24) {
        return `Обновлено ${diffHours} ч. назад`;
    } else {
        const day = String(lastUpdate.getDate()).padStart(2, '0');
        const month = String(lastUpdate.getMonth() + 1).padStart(2, '0');
        const year = lastUpdate.getFullYear();
        return `Обновлено ${day}.${month}.${year}`;
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

    // Fetch analytics ONLY for accessible projects
    const projectsWithStats = await Promise.all(projects.map(async (project) => {
        if (project.has_access === false) {
            // Для недоступных проектов не загружаем аналитику
            return { ...project, total_views: 0 };
        }

        try {
            const analytics = await apiCall(`/api/projects/${project.id}/analytics`);
            return {
                ...project,
                total_views: analytics.total_views || 0,
                progress_percent: analytics.progress_percent || 0  // Сохраняем progress_percent из API
            };
        } catch (error) {
            console.error(`Failed to load analytics for project ${project.id}:`, error);
            return { ...project, total_views: 0, progress_percent: 0 };
        }
    }));

    projectsList.innerHTML = projectsWithStats.map((project, index) => {
        const hasAccess = project.has_access !== false;
        const isFinished = project.is_active === 0 || project.is_active === false;

        // Determine lock icon and styling
        let lockIcon, cardOpacity, clickHandler, cursorStyle, lockedClass, grayscaleFilter;

        if (isFinished) {
            // Finished project: show finish flag, grayscale, read-only
            lockIcon = '🏁';
            cardOpacity = '0.7';
            clickHandler = hasAccess ? `onclick="openProject('${project.id}', 'view')"` : `onclick="showAccessDenied()"`;
            cursorStyle = 'cursor: pointer;';
            lockedClass = 'project-card-finished';
            grayscaleFilter = 'filter: grayscale(100%);';
        } else if (!hasAccess) {
            // No access: show lock, reduced opacity, disabled
            lockIcon = '🔒';
            cardOpacity = '0.6';
            clickHandler = `onclick="showAccessDenied()"`;
            cursorStyle = 'cursor: not-allowed;';
            lockedClass = 'project-card-locked';
            grayscaleFilter = '';
        } else {
            // Active project with access: normal (open in 'view' mode to see total stats without account lists)
            lockIcon = '🔓';
            cardOpacity = '1';
            clickHandler = `onclick="openProject('${project.id}', 'view')"`;
            cursorStyle = 'cursor: pointer;';
            lockedClass = '';
            grayscaleFilter = '';
        }

        // Используем progress_percent из API (уже ограничен до 100%)
        const progress = hasAccess ? (project.progress_percent || 0) : 0;
        const daysRemaining = calculateDaysRemaining(project.end_date);

        // Determine days text based on finish status
        let daysText, daysClass;
        if (isFinished) {
            daysText = '🏁 Завершен';
            daysClass = 'days-finished';
        } else {
            daysText = daysRemaining === 1 ? 'day left' : daysRemaining < 0 ? 'Expired' : `${daysRemaining} days left`;
            daysClass = daysRemaining < 7 ? 'days-urgent' : daysRemaining < 14 ? 'days-warning' : 'days-normal';
        }

        // Display name: backend already masks data for locked projects
        const displayName = project.name;
        const displayGeo = project.geo || 'Global';

        return `
            <div class="project-card ${lockedClass}" ${clickHandler} style="opacity: ${cardOpacity}; ${cursorStyle} ${grayscaleFilter}">
                <div class="project-header">
                    <div class="project-header-left">
                        <span style="font-size: 20px; margin-right: 8px;" title="${isFinished ? 'Проект завершен' : hasAccess ? 'Доступ разрешен' : 'Доступ закрыт'}">${lockIcon}</span>
                        <h3 class="project-name">${displayName}</h3>
                        <span class="project-geo">${displayGeo}</span>
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
                            <div class="chart-percentage">${hasAccess ? progress : 0}%</div>
                            <div class="chart-label">Progress</div>
                        </div>
                    </div>
                    <div class="project-stats-vertical">
                        <div class="stat">
                            <div class="stat-label">Total Views</div>
                            <div class="stat-value">${hasAccess ? formatNumber(project.total_views) : '***'}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">Target</div>
                            <div class="stat-value">${hasAccess ? formatNumber(project.target_views) : '***'}</div>
                        </div>
                        <div class="stat">
                            <div class="stat-label">KPI</div>
                            <div class="stat-value">${hasAccess ? 'от ' + formatNumber(project.kpi_views || 1000) : '***'}</div>
                        </div>
                    </div>
                    <div class="last-update-text" data-project-id="${project.id}">${getProjectTimestampText(project.id, project.last_admin_update)}</div>
                    <div class="project-platforms">
                        ${renderPlatformIcons(project.allowed_platforms)}
                    </div>
                </div>
            </div>
        `;
    }).join('');

    // Render charts after DOM update
    setTimeout(() => {
        projectsWithStats.forEach((project, index) => {
            const hasAccess = project.has_access !== false;
            // Используем progress_percent из API (уже ограничен до 100%)
            const progress = hasAccess ? (project.progress_percent || 0) : 0;
            createProgressChart(`chart-total-${index}`, progress);
        });
    }, 0);
}

// Функция для показа сообщения о запрете доступа
function showAccessDenied() {
    alert('Доступ к этому проекту закрыт. Обратитесь к администратору.');
}

// Render projects with MY PERSONAL stats
async function renderMyProjects(projects) {
    const myProjectsList = document.getElementById('my-projects-list');

    if (!myProjectsList) {
        console.error('my-projects-list element not found');
        return;
    }

    // Фильтруем только проекты с доступом для "Мои проекты"
    const accessibleProjects = projects.filter(p => p.has_access !== false);

    if (accessibleProjects.length === 0) {
        myProjectsList.innerHTML = '<div class="no-projects">No projects yet</div>';
        return;
    }

    // Fetch MY analytics for each accessible project
    const projectsWithMyStats = await Promise.all(accessibleProjects.map(async (project) => {
        try {
            const myAnalytics = await apiCall(`/api/my-analytics?project_id=${project.id}`);
            return {
                ...project,
                my_views: myAnalytics.total_views || 0,
                chart_data: myAnalytics.chart_data || []  // Реальные данные для графика
            };
        } catch (error) {
            console.error(`Failed to load my analytics for project ${project.id}:`, error);
            return { ...project, my_views: 0, chart_data: [] };
        }
    }));

    myProjectsList.innerHTML = projectsWithMyStats.map((project, index) => {
        const isFinished = project.is_active === 0 || project.is_active === false;
        const cardOpacity = isFinished ? '0.7' : '1';
        const grayscaleFilter = isFinished ? 'filter: grayscale(100%);' : '';
        const finishedBadge = isFinished ? '<span style="color: #4CAF50; margin-left: 8px; font-size: 14px;">🏁 Завершен</span>' : '';

        return `
        <div class="project-card-detailed" onclick="openProject('${project.id}', 'user')" style="opacity: ${cardOpacity}; ${grayscaleFilter}">
            <div class="project-header">
                <h3 class="project-name">${project.name}${finishedBadge}</h3>
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
                <div class="last-update-text" data-project-id="${project.id}">${getProjectTimestampText(project.id, project.last_admin_update)}</div>
                <div class="project-platforms">
                    ${renderPlatformIcons(project.allowed_platforms)}
                </div>
            </div>
        </div>
    `;
    }).join('');

    // Render bar charts after DOM update
    setTimeout(() => {
        projectsWithMyStats.forEach((project, index) => {
            // Используем реальные данные chart_data из API (ежедневный прирост)
            // chart_data = [{ date: "2025-12-08", growth: 50000 }, ...]
            if (project.chart_data && project.chart_data.length > 0) {
                // Берем последние 7 дней
                const last7Days = project.chart_data.slice(-7).map(item => ({
                    date: item.date,
                    views: item.growth || 0  // growth переименовываем в views для совместимости с createBarChart
                }));
                createBarChart(`chart-bar-${index}`, last7Days);
            } else {
                // Если нет данных - не показываем график (или можно показать пустой)
                console.warn(`No chart_data for project ${project.id}`);
            }
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

async function openProject(projectId, mode = 'user') {
    console.log('Opening project:', projectId, 'mode:', mode);

    // Set global project ID and mode for use in modals/wizards and date filtering
    window.currentProjectId = projectId;
    currentProjectId = projectId;
    currentProjectMode = mode;

    // Запоминаем откуда открыли проект для правильной навигации "Назад"
    // Определяем какая страница сейчас активна
    const currentPage = document.querySelector('.page:not(.hidden)');
    const currentPageId = currentPage ? currentPage.id : 'home-page';
    projectOpenedFrom = currentPageId;
    console.log('🔍 [Navigation] Opening project:', projectId, 'mode:', mode, 'from page:', currentPageId, '→ projectOpenedFrom:', projectOpenedFrom);

    try {
        // Загружаем данные проекта в зависимости от режима
        let analytics;
        if (mode === 'user') {
            // Пользовательский режим: показываем только статистику пользователя
            analytics = await apiCall(`/api/my-analytics?project_id=${projectId}`);
            console.log('🔍 DEBUG FRONTEND openProject (user mode): My analytics =', JSON.stringify(analytics, null, 2));
        } else if (mode === 'view') {
            // Режим просмотра: показываем общую статистику всех, но БЕЗ списков аккаунтов
            analytics = await apiCall(`/api/projects/${projectId}/analytics`);
            console.log('🔍 DEBUG FRONTEND openProject (view mode): Total analytics =', JSON.stringify(analytics, null, 2));
        } else {
            // Админ режим: показываем статистику всех + полный доступ
            analytics = await apiCall(`/api/projects/${projectId}/analytics`);
            console.log('🔍 DEBUG FRONTEND openProject (admin mode): Full analytics =', JSON.stringify(analytics, null, 2));
        }
        currentProjectData = analytics;

        // Показываем страницу детальной аналитики
        document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
        document.getElementById('project-details-page').classList.remove('hidden');

        // Обновляем заголовок
        const isFinished = analytics.project.is_active === 0 || analytics.project.is_active === false;
        const projectTitle = isFinished
            ? `${analytics.project.name} 🏁`
            : analytics.project.name;
        document.getElementById('project-details-name').textContent = projectTitle;

        // Динамически рендерим кнопки в зависимости от режима и статуса проекта
        const actionsContainer = document.getElementById('project-header-actions');
        if (actionsContainer) {
            if (isFinished) {
                // Завершенный проект: показываем только индикатор "Только для чтения"
                actionsContainer.innerHTML = `
                    <div style="padding: 8px 16px; font-size: 14px; color: #999; background: rgba(96, 125, 139, 0.1); border-radius: 8px; display: flex; align-items: center; gap: 8px;">
                        <i class="fa-solid fa-lock"></i>
                        <span>Только для чтения</span>
                    </div>
                `;
            } else if (mode === 'view') {
                // Режим просмотра: без кнопок управления
                actionsContainer.innerHTML = '';
            } else if (mode === 'admin') {
                // Админ режим (активный проект): кнопка "Добавить участника"
                // Примечание: "Импорт из Google" убран - синхронизация происходит автоматически
                actionsContainer.innerHTML = `
                    <button class="btn-primary" onclick="openAddUserToProjectModal()" style="padding: 8px 16px; font-size: 14px;">
                        <i class="fa-solid fa-user-plus"></i> Добавить участника
                    </button>
                `;
            } else {
                // Пользовательский режим (активный проект): кнопка "Добавить аккаунт"
                actionsContainer.innerHTML = `
                    <button class="btn-primary" onclick="openAddSocialAccountModal()" style="padding: 8px 16px; font-size: 14px;">
                        <i class="fa-solid fa-plus"></i> Добавить аккаунт
                    </button>
                `;
            }
        }

        // Показать/скрыть контроллы администратора проекта
        // Показываем ТОЛЬКО в режиме 'admin'
        const adminProjectControls = document.getElementById('admin-project-controls');
        if (adminProjectControls) {
            if (mode === 'admin' && currentUser && ADMIN_IDS.includes(currentUser.id)) {
                adminProjectControls.classList.remove('hidden');
                // Скрыть кнопку "Завершить" если проект уже завершен
                const finishButton = adminProjectControls.querySelector('button[onclick*="finishProject"]');
                if (finishButton) {
                    if (isFinished) {
                        finishButton.style.display = 'none';
                    } else {
                        finishButton.style.display = '';
                    }
                }
            } else {
                adminProjectControls.classList.add('hidden');
            }
        }

        // Показать/скрыть секции участников в зависимости от режима
        const participantsCard = document.getElementById('participants-card');
        const participantsSection = document.getElementById('participants-section');

        if (mode === 'user') {
            // В пользовательском режиме скрываем информацию об участниках
            if (participantsCard) participantsCard.style.display = 'none';
            if (participantsSection) participantsSection.style.display = 'none';
        } else if (mode === 'view') {
            // В режиме просмотра показываем только количество участников (карточка), но скрываем список
            if (participantsCard) participantsCard.style.display = '';
            if (participantsSection) participantsSection.style.display = 'none';
        } else {
            // В админском режиме показываем и карточку и список участников
            if (participantsCard) participantsCard.style.display = '';
            if (participantsSection) participantsSection.style.display = '';
        }

        // Отображаем суммарную статистику
        displaySummaryStats(analytics);

        // Создаем слайды с диаграммами (передаем режим для скрытия топ аккаунтов в режиме 'view')
        createChartSlides(analytics, mode);

        // Загружаем и отображаем социальные аккаунты в аккордеоне
        // В режиме user передаем флаг для фильтрации только своих аккаунтов
        // В режиме view скрываем аккордеон с аккаунтами
        const profilesAccordion = document.querySelector('.profiles-accordion');
        if (mode === 'view') {
            if (profilesAccordion) profilesAccordion.style.display = 'none';
        } else {
            if (profilesAccordion) profilesAccordion.style.display = '';
            await loadProjectSocialAccounts(projectId, mode);
        }

        // Инициализируем таймер обновления, передаем данные проекта для загрузки timestamp из API
        initProjectTimestamp(projectId, analytics.project);

    } catch (error) {
        console.error('Failed to load project details:', error);
        showError('Не удалось загрузить детали проекта');
    }
}

function closeProjectDetails() {
    console.log('🔙 [Navigation] Closing project details, projectOpenedFrom:', projectOpenedFrom);
    document.getElementById('project-details-page').classList.add('hidden');

    // Возвращаемся на ту страницу откуда пришли
    // Поддерживаем все возможные страницы: home-page, projects-page, project-management-page
    const pageToShow = document.getElementById(projectOpenedFrom);

    if (pageToShow) {
        console.log('🔙 [Navigation] Returning to page:', projectOpenedFrom);
        pageToShow.classList.remove('hidden');
    } else {
        // Fallback на home-page если страница не найдена
        console.log('🔙 [Navigation] Page not found, returning to home-page');
        document.getElementById('home-page').classList.remove('hidden');
    }
}

// ==================== ADMIN PROJECT CONTROLS ====================

async function deleteProject(id) {
    const projectId = id || window.currentProjectId;
    if (!projectId) {
        showError('Проект не выбран');
        return;
    }

    // Подтверждение удаления
    if (!confirm('Вы точно хотите удалить проект и все данные? Это действие нельзя отменить.')) {
        return;
    }

    try {
        const response = await apiCall(`/api/projects/${projectId}`, {
            method: 'DELETE'
        });

        if (response.success) {
            showSuccess('Проект удален');
            closeProjectDetails();
            // Reload page to refresh project list
            setTimeout(() => window.location.reload(), 1000);
        } else {
            showError(response.message || 'Не удалось удалить проект');
        }
    } catch (error) {
        console.error('Error deleting project:', error);
        showError('Ошибка при удалении проекта');
    }
}

async function finishProject(id) {
    const projectId = id || window.currentProjectId;
    if (!projectId) {
        showError('Проект не выбран');
        return;
    }

    // Подтверждение завершения
    if (!confirm('Завершить проект? Он станет недоступен для редактирования.')) {
        return;
    }

    try {
        const response = await apiCall(`/api/projects/${projectId}/finish`, {
            method: 'POST'
        });

        if (response.success) {
            showSuccess('Проект завершен');
            // Reload project details
            if (isAdmin) {
                await loadProjectDetailsForAdmin(projectId);
            } else {
                await openProject(projectId, 'user');
            }
        } else {
            showError(response.message || 'Не удалось завершить проект');
        }
    } catch (error) {
        console.error('Error finishing project:', error);
        showError('Ошибка при завершении проекта');
    }
}

async function resetProjectTimestamp() {
    const projectId = window.currentProjectId;
    if (!projectId) {
        showError('Проект не выбран');
        return;
    }

    try {
        console.log('🔄 [Timestamp] Вызываем API update-timestamp для проекта:', projectId);

        // Вызываем API для сохранения времени в базе данных
        const response = await apiCall(`/api/admin/projects/${projectId}/update-timestamp`, {
            method: 'POST'
        });

        console.log('✅ [Timestamp] Ответ от API:', response);

        if (response.success) {
            // Сохраняем время в localStorage для мгновенного отображения
            const timestamp = response.timestamp || new Date().toISOString();
            console.log('💾 [Timestamp] Сохраняем timestamp в localStorage:', timestamp);
            localStorage.setItem(`project_${projectId}_last_update`, timestamp);

            // Обновляем отображение на детальной странице
            const lastUpdateElement = document.getElementById('detail-last-update');
            console.log('🎯 [Timestamp] Элемент detail-last-update:', lastUpdateElement);
            if (lastUpdateElement) {
                lastUpdateElement.textContent = 'Только что';
                console.log('✅ [Timestamp] Обновили текст на "Только что"');
            }

            // Обновляем все карточки проектов на всех страницах
            console.log('🔄 [Timestamp] Обновляем карточки проектов...');
            updateAllProjectCardsTimestamp(projectId);

            showSuccess('Таймер сброшен!');

            // Запускаем обновление каждую минуту
            startTimestampUpdater(projectId);
        } else {
            console.error('❌ [Timestamp] response.success = false');
            throw new Error('Failed to update timestamp');
        }
    } catch (error) {
        console.error('Failed to reset timestamp:', error);
        showError('Не удалось сбросить таймер');
    }
}

// Обновить timestamp на всех карточках проектов
function updateAllProjectCardsTimestamp(projectId) {
    // Находим все элементы с классом last-update-text для этого проекта
    const timestampElements = document.querySelectorAll(`.last-update-text[data-project-id="${projectId}"]`);
    console.log(`🔍 [Timestamp] Найдено карточек для обновления:`, timestampElements.length);

    const newText = getProjectTimestampText(projectId);
    console.log(`📝 [Timestamp] Новый текст для карточек:`, newText);

    timestampElements.forEach((element, index) => {
        console.log(`✏️ [Timestamp] Обновляем карточку ${index + 1}:`, element);
        element.textContent = newText;
    });

    console.log(`✅ [Timestamp] Обновлено ${timestampElements.length} карточек`);
}

// Функция для обновления отображения времени
function startTimestampUpdater(projectId) {
    // Очищаем предыдущий интервал если был
    if (window.timestampInterval) {
        clearInterval(window.timestampInterval);
    }

    // Обновляем каждую минуту
    window.timestampInterval = setInterval(() => {
        const savedTime = localStorage.getItem(`project_${projectId}_last_update`);
        if (!savedTime) return;

        // Парсим время (может быть с "Z" или без)
        const timeString = savedTime.endsWith('Z') ? savedTime : savedTime + 'Z';
        const lastUpdate = new Date(timeString);
        const now = new Date();
        const diff = Math.floor((now - lastUpdate) / 1000); // секунды

        let text;
        if (diff < 60) {
            text = 'Только что';
        } else if (diff < 3600) {
            const minutes = Math.floor(diff / 60);
            text = `${minutes} мин. назад`;
        } else {
            const hours = Math.floor(diff / 3600);
            text = `${hours} ч. назад`;
        }

        const lastUpdateElement = document.getElementById('detail-last-update');
        if (lastUpdateElement) {
            lastUpdateElement.textContent = text;
        }
    }, 60000); // каждую минуту
}

// Получить текст timestamp для отображения на карточке проекта
function getProjectTimestampText(projectId, apiTimestamp) {
    console.log(`🕐 [getProjectTimestampText] projectId=${projectId}, apiTimestamp=${apiTimestamp}`);

    // Приоритет: сначала проверяем API данные, затем localStorage
    let savedTime = null;

    if (apiTimestamp) {
        // Используем timestamp из API
        savedTime = apiTimestamp;
        console.log(`📡 [getProjectTimestampText] Используем API timestamp: ${savedTime}`);
        // Синхронизируем с localStorage
        localStorage.setItem(`project_${projectId}_last_update`, savedTime);
    } else {
        // Fallback на localStorage
        savedTime = localStorage.getItem(`project_${projectId}_last_update`);
        console.log(`💾 [getProjectTimestampText] Читаем из localStorage: ${savedTime}`);
    }

    if (!savedTime) {
        console.log(`⚠️ [getProjectTimestampText] Нет сохраненного времени`);
        return '—';
    }

    // Парсим время (может быть с "Z" или без)
    // Если без "Z" - это UTC время, добавляем "Z" для правильного парсинга
    const timeString = savedTime.endsWith('Z') ? savedTime : savedTime + 'Z';
    const lastUpdate = new Date(timeString);
    const now = new Date();
    const diff = Math.floor((now - lastUpdate) / 1000); // секунды
    console.log(`⏱️ [getProjectTimestampText] savedTime: ${savedTime}, parsed: ${timeString}, diff: ${diff} секунд`);

    if (diff < 60) {
        console.log(`✅ [getProjectTimestampText] Возвращаем: "Обновлено только что"`);
        return 'Обновлено только что';
    } else if (diff < 3600) {
        const minutes = Math.floor(diff / 60);
        console.log(`✅ [getProjectTimestampText] Возвращаем: "Обновлено ${minutes} мин. назад"`);
        return `Обновлено ${minutes} мин. назад`;
    } else {
        const hours = Math.floor(diff / 3600);
        console.log(`✅ [getProjectTimestampText] Возвращаем: "Обновлено ${hours} ч. назад"`);
        return `Обновлено ${hours} ч. назад`;
    }
}

// Вызываем при загрузке проекта чтобы восстановить таймер
function initProjectTimestamp(projectId, projectData) {
    const lastUpdateElement = document.getElementById('detail-last-update');

    if (!lastUpdateElement) return;

    // Проверяем есть ли timestamp в данных проекта из API
    let savedTime = null;
    if (projectData && projectData.last_admin_update) {
        savedTime = projectData.last_admin_update;
        // Сохраняем в localStorage для синхронизации
        localStorage.setItem(`project_${projectId}_last_update`, savedTime);
    } else {
        // Fallback на localStorage если нет данных из API
        savedTime = localStorage.getItem(`project_${projectId}_last_update`);
    }

    if (savedTime) {
        // Вычисляем и показываем текущее время
        // Парсим время (может быть с "Z" или без)
        const timeString = savedTime.endsWith('Z') ? savedTime : savedTime + 'Z';
        const lastUpdate = new Date(timeString);
        const now = new Date();
        const diff = Math.floor((now - lastUpdate) / 1000); // секунды

        let text;
        if (diff < 60) {
            text = 'Только что';
        } else if (diff < 3600) {
            const minutes = Math.floor(diff / 60);
            text = `${minutes} мин. назад`;
        } else {
            const hours = Math.floor(diff / 3600);
            text = `${hours} ч. назад`;
        }

        lastUpdateElement.textContent = text;

        // Запускаем обновление каждую минуту
        startTimestampUpdater(projectId);
    } else {
        // Если нет сохраненного времени, показываем "—"
        lastUpdateElement.textContent = '—';
    }
}

async function refreshProjectStats() {
    console.log('🎯🎯🎯 refreshProjectStats CALLED');
    // Открываем модальное окно выбора платформ
    openRefreshStatsModal();
}

// ==================== REFRESH STATS MODAL ====================

function openRefreshStatsModal() {
    console.log('🚪 Opening refresh stats modal');
    const modal = document.getElementById('refresh-stats-modal');
    console.log('Modal element:', modal);
    modal.classList.remove('hidden');
    console.log('Modal classList after remove hidden:', modal.classList);

    // Автоматически заполняем даты
    const dateFromInput = document.getElementById('refresh-date-from');
    const dateToInput = document.getElementById('refresh-date-to');

    // Дата "По" = сегодня
    const today = new Date();
    const todayFormatted = today.toISOString().split('T')[0]; // YYYY-MM-DD
    dateToInput.value = todayFormatted;

    // Дата "С" = дата создания проекта или 30 дней назад
    let projectCreatedDate = null;
    if (currentProjectData && currentProjectData.project) {
        const createdAt = currentProjectData.project.created_at;
        if (createdAt) {
            // Формат может быть "YYYY-MM-DD HH:MM:SS" или "YYYY-MM-DD"
            projectCreatedDate = createdAt.split(' ')[0]; // Берем только дату
        }
    }

    if (projectCreatedDate) {
        dateFromInput.value = projectCreatedDate;
    } else {
        // Если нет даты создания проекта - ставим 30 дней назад
        const thirtyDaysAgo = new Date();
        thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
        dateFromInput.value = thirtyDaysAgo.toISOString().split('T')[0];
    }

    console.log('📅 Date range set:', dateFromInput.value, 'to', dateToInput.value);
}

function closeRefreshStatsModal() {
    document.getElementById('refresh-stats-modal').classList.add('hidden');

    // Останавливаем polling если он запущен
    if (window.currentProgressPoll) {
        clearInterval(window.currentProgressPoll);
        window.currentProgressPoll = null;
    }

    // Сбрасываем модальное окно к первому шагу
    setTimeout(() => {
        document.getElementById('refresh-step-1').classList.remove('hidden');
        document.getElementById('refresh-step-2').classList.add('hidden');
        document.getElementById('close-progress-btn').style.display = 'none';
        document.getElementById('platform-progress-bars').innerHTML = '';
    }, 300);
}

async function submitRefreshStats() {
    console.log('🚀🚀🚀 submitRefreshStats FUNCTION CALLED!!! 🚀🚀🚀');
    console.log('Version check: POLLING-v1');
    const projectId = window.currentProjectId;
    console.log('Project ID:', projectId);

    if (!projectId) {
        showError('Проект не выбран');
        return;
    }

    // Собираем выбранные платформы
    const platforms = {
        tiktok: document.getElementById('refresh-tiktok').checked,
        instagram: document.getElementById('refresh-instagram').checked,
        facebook: document.getElementById('refresh-facebook').checked,
        youtube: document.getElementById('refresh-youtube').checked,
        threads: document.getElementById('refresh-threads').checked
    };

    // Проверяем что хотя бы одна платформа выбрана
    if (!Object.values(platforms).some(v => v)) {
        showError('Выберите хотя бы одну платформу');
        return;
    }

    // Собираем даты фильтрации
    const dateFrom = document.getElementById('refresh-date-from').value;
    const dateTo = document.getElementById('refresh-date-to').value;

    console.log('🚀 Starting stats refresh for project:', projectId);
    console.log('📋 Selected platforms:', platforms);
    console.log('📅 Date range:', dateFrom, 'to', dateTo);

    // Переключаем на второй шаг - показываем прогресс
    document.getElementById('refresh-step-1').classList.add('hidden');
    document.getElementById('refresh-step-2').classList.remove('hidden');
    console.log('✅ Switched to progress view');

    // Создаем прогресс-бары для выбранных платформ
    console.log('🎨 Creating progress bars...');
    createProgressBars(platforms);

    // Подключаемся к SSE для получения прогресса
    console.log('📡 Connecting to SSE stream...');
    connectToProgressStream(projectId);

    // Запускаем обновление статистики (не ждем завершения)
    console.log('🔄 Starting API call to refresh stats...');
    apiCall(`/api/projects/${projectId}/refresh_stats`, {
        method: 'POST',
        body: JSON.stringify({
            platforms,
            date_from: dateFrom,
            date_to: dateTo
        })
    }).then(async (response) => {
        console.log('✅ Stats refresh started in background:', response);
        // Не показываем уведомление, так как у нас есть финальный экран
    }).catch(error => {
        console.error('Failed to start stats refresh:', error);
        showError('Не удалось запустить обновление статистики: ' + error.message);
    });
}

function createProgressBars(platforms) {
    console.log('🎨🎨🎨 createProgressBars CALLED!!! 🎨🎨🎨');
    console.log('Platforms to create:', platforms);
    const container = document.getElementById('platform-progress-bars');
    console.log('Container found:', container);
    container.innerHTML = '';

    const platformIcons = {
        tiktok: '📱',
        instagram: '📷',
        facebook: '👤',
        youtube: '🎬',
        threads: '🧵'
    };

    const platformNames = {
        tiktok: 'TikTok',
        instagram: 'Instagram',
        facebook: 'Facebook',
        youtube: 'YouTube',
        threads: 'Threads'
    };

    // Создаем прогресс-бар для каждой выбранной платформы
    for (const [platform, enabled] of Object.entries(platforms)) {
        if (!enabled) continue;

        const progressDiv = document.createElement('div');
        progressDiv.id = `progress-${platform}`;
        progressDiv.style.cssText = 'background: rgba(255,255,255,0.05); border-radius: 12px; padding: 16px;';

        progressDiv.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <span style="font-weight: 600; font-size: 14px;">
                    ${platformIcons[platform]} ${platformNames[platform]}
                </span>
                <span id="progress-text-${platform}" style="font-size: 13px; color: #aaa;">
                    0/0 (0%)
                </span>
            </div>
            <div style="background: rgba(255,255,255,0.1); border-radius: 8px; height: 8px; overflow: hidden;">
                <div id="progress-bar-${platform}" style="background: linear-gradient(90deg, #a78bfa 0%, #c084fc 100%); height: 100%; width: 0%; transition: width 0.3s ease;"></div>
            </div>
            <div style="display: flex; gap: 16px; margin-top: 8px; font-size: 12px; color: #aaa;">
                <span>✅ <span id="progress-success-${platform}">0</span></span>
                <span>❌ <span id="progress-failed-${platform}">0</span></span>
            </div>
        `;

        container.appendChild(progressDiv);
        console.log(`✅ Created progress bar for ${platform}`);
    }
    console.log('✅✅✅ All progress bars created! ✅✅✅');
}

function connectToProgressStream(projectId) {
    console.log('🔌🔌🔌 Starting progress polling for project:', projectId);
    console.log('Will poll immediately and then every 500ms');

    let pollCount = 0;
    let pollInterval = null;

    // Функция для выполнения одного poll
    const doPoll = async () => {
        pollCount++;
        try {
            console.log(`📡 [Poll #${pollCount}] Fetching progress...`);
            const response = await apiCall(`/api/projects/${projectId}/refresh_progress`);
            console.log(`📊 [Poll #${pollCount}] Response:`, JSON.stringify(response));

            if (response && response.progress) {
                const progressKeys = Object.keys(response.progress);
                console.log(`✅ [Poll #${pollCount}] Got progress for platforms:`, progressKeys);

                // Обновляем прогресс-бары
                for (const [platform, stats] of Object.entries(response.progress)) {
                    console.log(`🔄 [Poll #${pollCount}] Updating ${platform}:`, stats);
                    updateProgressBar(platform, stats);
                }

                // Проверяем завершение
                const allDone = Object.values(response.progress).every(
                    stats => stats.processed >= stats.total && stats.total > 0
                );

                console.log(`🎯 [Poll #${pollCount}] All done check:`, allDone);

                if (allDone && progressKeys.length > 0) {
                    console.log('✅✅✅ All platforms completed! Stopping polling.');
                    if (pollInterval) clearInterval(pollInterval);

                    // Показываем финальный экран с результатами
                    showCompletionScreen(projectId, response.progress);
                }
            } else {
                console.warn(`⚠️ [Poll #${pollCount}] No progress data yet`);
            }
        } catch (error) {
            console.error(`❌ [Poll #${pollCount}] Error:`, error);
        }
    };

    // Первый poll сразу!
    doPoll();

    // Используем простой polling каждые 500ms (вместо 1000ms для быстрых обновлений)
    pollInterval = setInterval(doPoll, 500);

    // Сохраняем ID интервала для остановки
    window.currentProgressPoll = pollInterval;
    console.log('✅ Polling started with interval ID:', pollInterval);
}

function updateProgressBar(platform, stats) {
    const { total, processed, updated, failed } = stats;
    const percent = total > 0 ? Math.round((processed / total) * 100) : 0;

    console.log(`📊 Updating UI for ${platform}: ${processed}/${total} (${percent}%)`);

    // Обновляем текст прогресса
    const textEl = document.getElementById(`progress-text-${platform}`);
    if (textEl) {
        textEl.textContent = `${processed}/${total} (${percent}%)`;
        console.log(`✅ Updated text for ${platform}`);
    } else {
        console.error(`❌ Element not found: progress-text-${platform}`);
    }

    // Обновляем ширину прогресс-бара
    const barEl = document.getElementById(`progress-bar-${platform}`);
    if (barEl) {
        barEl.style.width = `${percent}%`;
        console.log(`✅ Updated bar width for ${platform}: ${percent}%`);
    } else {
        console.error(`❌ Element not found: progress-bar-${platform}`);
    }

    // Обновляем счетчики успеха/ошибок
    const successEl = document.getElementById(`progress-success-${platform}`);
    if (successEl) {
        successEl.textContent = updated;
        console.log(`✅ Updated success count for ${platform}: ${updated}`);
    } else {
        console.error(`❌ Element not found: progress-success-${platform}`);
    }

    const failedEl = document.getElementById(`progress-failed-${platform}`);
    if (failedEl) {
        failedEl.textContent = failed;
        console.log(`✅ Updated failed count for ${platform}: ${failed}`);
    } else {
        console.error(`❌ Element not found: progress-failed-${platform}`);
    }
}

function showCompletionScreen(projectId, progressData) {
    console.log('🎉 Showing completion screen with data:', progressData);

    // Скрываем заголовок и описание
    const titleEl = document.getElementById('progress-title');
    const descEl = document.getElementById('progress-description');
    if (titleEl) titleEl.style.display = 'none';
    if (descEl) descEl.style.display = 'none';

    // Находим контейнер прогресса
    const progressContainer = document.getElementById('platform-progress-bars');
    if (!progressContainer) {
        console.error('❌ Progress container not found');
        return;
    }

    // Перезагружаем данные проекта в фоне
    console.log('🔄 Reloading project data...');
    openProject(projectId, currentProjectMode).then(() => {
        console.log('✅ Project data reloaded');
    }).catch(err => {
        console.error('❌ Failed to reload project data:', err);
    });

    // Подсчитываем общую статистику
    let totalAccounts = 0;
    let totalSuccess = 0;
    let totalFailed = 0;

    for (const [platform, stats] of Object.entries(progressData)) {
        totalAccounts += stats.total || 0;
        totalSuccess += stats.updated || 0;
        totalFailed += stats.failed || 0;
    }

    // Создаём HTML для финального экрана
    let platformsHTML = '';
    const platformNames = {
        'tiktok': 'TikTok',
        'instagram': 'Instagram'
    };

    for (const [platform, stats] of Object.entries(progressData)) {
        const platformName = platformNames[platform] || platform;
        platformsHTML += `
            <div style="background: rgba(255, 255, 255, 0.05); border-radius: 12px; padding: 16px; margin-bottom: 12px;">
                <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 8px;">
                    <span style="font-size: 24px;">${platform === 'tiktok' ? '📱' : '📸'}</span>
                    <span style="font-size: 18px; font-weight: 500; color: #ffffff;">${platformName}</span>
                </div>
                <div style="display: flex; gap: 20px; margin-top: 12px;">
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 20px;">✅</span>
                        <span style="color: #4ade80; font-size: 16px; font-weight: 500;">${stats.updated || 0}</span>
                        <span style="color: rgba(255, 255, 255, 0.6); font-size: 14px;">успешно</span>
                    </div>
                    ${stats.failed > 0 ? `
                    <div style="display: flex; align-items: center; gap: 6px;">
                        <span style="font-size: 20px;">❌</span>
                        <span style="color: #f87171; font-size: 16px; font-weight: 500;">${stats.failed}</span>
                        <span style="color: rgba(255, 255, 255, 0.6); font-size: 14px;">ошибок</span>
                    </div>
                    ` : ''}
                </div>
            </div>
        `;
    }

    const completionHTML = `
        <div style="text-align: center; padding: 20px 0;">
            <div style="font-size: 48px; margin-bottom: 16px;">🎉</div>
            <h3 style="color: #ffffff; font-size: 24px; font-weight: 600; margin-bottom: 8px;">
                Обновление завершено!
            </h3>
            <p style="color: rgba(255, 255, 255, 0.7); font-size: 16px; margin-bottom: 24px;">
                Обработано ${totalAccounts} ${totalAccounts === 1 ? 'аккаунт' : totalAccounts < 5 ? 'аккаунта' : 'аккаунтов'}
            </p>
        </div>

        <div style="margin-bottom: 24px;">
            ${platformsHTML}
        </div>

        <div style="background: rgba(74, 222, 128, 0.1); border: 1px solid rgba(74, 222, 128, 0.3); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
            <div style="display: flex; align-items: center; justify-content: center; gap: 12px;">
                <span style="font-size: 20px;">✨</span>
                <span style="color: #4ade80; font-size: 16px; font-weight: 500;">
                    ${totalSuccess} из ${totalAccounts} аккаунтов обновлены успешно
                </span>
            </div>
        </div>

        <button onclick="closeRefreshStatsModal()"
                style="width: 100%; padding: 14px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                       color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: 500;
                       cursor: pointer; transition: all 0.2s;">
            Закрыть
        </button>
    `;

    // Заменяем содержимое
    progressContainer.innerHTML = completionHTML;
    console.log('✅ Completion screen displayed');
}

// ==================== END ADMIN PROJECT CONTROLS ====================

function displaySummaryStats(analytics) {
    const { project, total_views, total_videos, total_profiles, users_stats, topic_stats, growth_24h } = analytics;

    // Используем данные из API
    const profilesCount = total_profiles || Object.keys(users_stats || {}).length;
    const videosCount = total_videos || 0;

    // Рассчитываем количество тематик
    const totalTopics = Object.keys(topic_stats || {}).length;

    // Рассчитываем количество участников
    const totalParticipants = Object.keys(users_stats || {}).length;

    // Процент выполнения - используем значение из бэкенда (уже ограничено до 100)
    const progress = analytics.progress_percent || 0;

    console.log('🔍 DEBUG displaySummaryStats: total_videos =', total_videos, 'videosCount =', videosCount);
    console.log('🔍 DEBUG displaySummaryStats: total_profiles =', total_profiles, 'profilesCount =', profilesCount);
    console.log('🔍 DEBUG displaySummaryStats: progress from backend =', analytics.progress_percent, 'using =', progress);

    document.getElementById('detail-total-views').textContent = formatNumber(total_views);
    document.getElementById('detail-progress').textContent = `${progress}%`;
    document.getElementById('detail-total-videos').textContent = videosCount;
    document.getElementById('detail-total-profiles').textContent = profilesCount;
    document.getElementById('detail-total-topics').textContent = totalTopics;
    document.getElementById('detail-total-participants').textContent = totalParticipants;

    // Прирост за 24 часа
    const growth24hValue = growth_24h || 0;
    const growth24hElement = document.getElementById('pd-growth-24h');
    growth24hElement.textContent = formatNumber(growth24hValue);
    // Зеленый цвет если прирост > 0
    growth24hElement.style.color = growth24hValue > 0 ? '#4CAF50' : '#fff';

    // Время последнего обновления НЕ устанавливаем здесь
    // Это контролируется frontend localStorage в initProjectTimestamp()
}

function createChartSlides(analytics, mode = 'user') {
    const swiperContainer = document.getElementById('charts-swiper');
    const dotsContainer = document.getElementById('swiper-dots');

    // Очищаем предыдущие слайды
    swiperContainer.innerHTML = '';
    dotsContainer.innerHTML = '';

    const slides = [];

    // Слайд 1: Линейная диаграмма просмотров по дням
    slides.push(createDailyViewsSlide(analytics));

    // Слайд 2: Круговая диаграмма тематик
    slides.push(createTopicsSlide(analytics));

    // Слайд 3: Круговая диаграмма платформ
    slides.push(createPlatformsSlide(analytics));

    // Слайд 4: Круговая диаграмма профилей (только для режимов 'user' и 'admin', скрыт в режиме 'view')
    if (mode !== 'view') {
        slides.push(createProfilesSlide(analytics));
    }

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

function createDailyViewsSlide(analytics) {
    return `
        <div class="chart-slide">
            <h4>Просмотры по дням</h4>
            <canvas id="daily-chart" width="300" height="200"></canvas>
        </div>
    `;
}

// Date filter function
async function applyDateFilter() {
    if (!currentProjectId) return;

    const startDate = document.getElementById('analytics-start-date').value;
    const endDate = document.getElementById('analytics-end-date').value;

    try {
        // Build URL with date parameters
        let url;
        if (currentProjectMode === 'user') {
            url = `/api/my-analytics?project_id=${currentProjectId}`;
        } else {
            url = `/api/projects/${currentProjectId}/analytics`;
        }

        // Add date parameters if set
        const params = [];
        if (startDate) params.push(`start_date=${startDate}`);
        if (endDate) params.push(`end_date=${endDate}`);

        if (params.length > 0) {
            url += (url.includes('?') ? '&' : '?') + params.join('&');
        }

        const analytics = await apiCall(url);
        currentProjectData = analytics;

        // Re-render stats and charts
        displaySummaryStats(analytics);
        createChartSlides(analytics, currentProjectMode);

        // Reload accounts list
        loadProjectSocialAccounts(currentProjectId, currentProjectMode);
    } catch (error) {
        console.error('Error applying date filter:', error);
        showToast('Ошибка применения фильтра дат');
    }
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
            <h4>Топ аккаунтов по просмотрам</h4>
            <div id="profiles-leaderboard" style="padding: 5px 10px; max-height: 280px; overflow-y: auto;"></div>
        </div>
    `;
}

function renderAllCharts(analytics) {
    // Используем chart_data (ежедневный прирост) вместо history (нарастающий итог)
    const chartData = analytics.chart_data || analytics.history || [];
    const profiles = analytics.profiles || [];

    createDailyChart(chartData);
    createTopicsChart(analytics.topic_stats);
    createPlatformsChart(analytics.platform_stats);
    createProfilesChart(profiles);
}

function createDailyChart(chartData) {
    const canvas = document.getElementById('daily-chart');
    if (!canvas) return;

    // Используем данные прироста (chart_data) вместо нарастающего итога (history)
    // chartData = [{ date: "2025-12-08", growth: 50000 }, ...] или старый формат [{ date: "2025-12-08", views: 50000 }]

    // Форматируем даты в короткий вид (ДД.ММ)
    const labels = chartData.map(item => {
        const date = new Date(item.date);
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        return `${day}.${month}`;
    });
    // Используем growth (новый формат) или views (старый формат для обратной совместимости)
    const data = chartData.map(item => item.growth !== undefined ? item.growth : item.views || 0);

    new Chart(canvas, {
        type: 'line',  // ЛИНИЯ для главного графика внутри проекта
        data: {
            labels: labels,
            datasets: [{
                label: 'Ежедневный прирост',
                data: data,
                backgroundColor: 'rgba(167, 139, 250, 0.3)', // Purple gradient fill
                borderColor: 'rgba(167, 139, 250, 1)', // Purple line
                borderWidth: 2,
                fill: true,
                tension: 0.4  // Smooth curve
            }]
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            return 'Прирост: ' + context.parsed.y.toLocaleString('ru-RU');
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        color: '#fff',
                        callback: function(value) {
                            // Показываем полные числа с разделителями
                            return value.toLocaleString('ru-RU');
                        }
                    },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                },
                x: {
                    ticks: {
                        color: '#fff',
                        maxRotation: 0,
                        minRotation: 0
                    },
                    grid: { display: false }
                }
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

    // Определяем цвета для каждой платформы
    const platformColors = {
        'tiktok': '#00F876',      // Bright Green
        'instagram': '#d62976',   // Pink/Purple
        'facebook': '#1877f2',    // Blue
        'youtube': '#ff0000',     // Red
        'threads': '#000000'      // Black
    };

    const labels = Object.keys(platformStats);
    const data = Object.values(platformStats);
    const colors = labels.map(platform => platformColors[platform] || '#888888');

    new Chart(canvas, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors
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

function createProfilesChart(profiles) {
    const leaderboard = document.getElementById('profiles-leaderboard');
    if (!leaderboard) return;

    // Фильтруем только профили с username соц сети (не telegram_user)
    // и сортируем по просмотрам, берем топ 10
    console.log('🔍 DEBUG: All profiles for leaderboard:', profiles);

    const sortedProfiles = profiles
        .filter(profile => {
            // Исключаем только telegram usernames (начинаются с @)
            // Показываем Unknown и все остальные
            const isValid = profile.username && !profile.username.startsWith('@');
            if (!isValid) {
                console.log('🔍 Filtered out profile:', profile);
            }
            return isValid;
        })
        .map(profile => ({
            username: profile.username,
            views: profile.total_views || 0,
            platform: profile.platform || 'unknown'
        }))
        .sort((a, b) => b.views - a.views)
        .slice(0, 10);

    console.log('🔍 DEBUG: Sorted profiles for leaderboard:', sortedProfiles);

    if (sortedProfiles.length === 0) {
        leaderboard.innerHTML = '<p style="text-align: center; color: rgba(255,255,255,0.5);">Нет данных</p>';
        return;
    }

    // Иконки для позиций
    const medals = ['🥇', '🥈', '🥉'];

    // Цвета для платформ
    const platformColors = {
        'tiktok': '#00F876',
        'instagram': '#d62976',
        'facebook': '#1877f2',
        'youtube': '#ff0000',
        'threads': '#000000'
    };

    // Размеры текста для каждой позиции (уменьшаются)
    const fontSizes = [15, 14, 13, 12, 11, 10, 10, 9, 9, 9];

    let html = '<div style="display: flex; flex-direction: column; gap: 3px;">';

    sortedProfiles.forEach((profile, index) => {
        const position = index + 1;
        const medal = medals[index] || `${position}.`;
        const fontSize = fontSizes[index] || 10;
        const platformColor = platformColors[profile.platform] || '#888';
        const formattedViews = profile.views.toLocaleString('ru-RU');

        html += `
            <div style="
                display: flex;
                align-items: center;
                gap: 5px;
                padding: 4px 6px;
                background: rgba(255,255,255,0.05);
                border-radius: 6px;
                border-left: 3px solid ${platformColor};
            ">
                <span style="font-size: ${fontSize + 2}px; min-width: 20px;">${medal}</span>
                <div style="flex: 1; display: flex; flex-direction: column; gap: 1px;">
                    <span style="font-size: ${fontSize}px; font-weight: 600; color: #fff;">@${profile.username}</span>
                    <span style="font-size: ${fontSize - 2}px; color: rgba(255,255,255,0.6);">
                        <i class="fa-solid fa-eye"></i> ${formattedViews}
                    </span>
                </div>
            </div>
        `;
    });

    html += '</div>';
    leaderboard.innerHTML = html;
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

function showWarning(message) {
    // Create warning notification (yellow/blue)
    const notification = document.createElement('div');
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        left: 50%;
        transform: translateX(-50%);
        background: linear-gradient(135deg, #ffd89b 0%, #19547b 100%);
        color: white;
        padding: 15px 25px;
        border-radius: 12px;
        z-index: 9999;
        font-weight: 600;
        box-shadow: 0 10px 30px rgba(255, 216, 155, 0.3);
        max-width: 80%;
        text-align: center;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);

    // Remove after 3 seconds
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
    } else if (pageName === 'emails') {
        // Загружаем список почт
        loadMyEmails();
    }

    closeSidebar();
}

// ==================== INITIALIZATION ====================
async function init() {
    try {
        console.log('Initializing app...');

        // Check if opened in Telegram
        if (!window.Telegram || !window.Telegram.WebApp || !tg.initData) {
            console.error('⚠️ App opened outside Telegram WebApp context');
            const loadingElement = document.getElementById('loading');
            if (loadingElement) {
                loadingElement.innerHTML = `
                    <div style="text-align: center; padding: 40px 20px;">
                        <h2>⚠️ Ошибка доступа</h2>
                        <p style="margin: 20px 0;">Это приложение работает только внутри Telegram.</p>
                        <p>Пожалуйста, откройте бота в Telegram и нажмите кнопку "📊 Открыть Analytics"</p>
                    </div>
                `;
            }
            return;
        }

        // Initialize Telegram
        initTelegramApp();

        // Load user data
        const data = await apiCall('/api/me');
        currentUser = data.user;

        console.log('User:', currentUser);

        // Load ALL projects (including those without access, for display on home page)
        const projectsData = await apiCall('/api/projects');
        currentProjects = projectsData.projects || [];

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

        // Render projects (includes locked projects with masked data)
        renderProjects(currentProjects);

        // Load analytics in background (non-blocking)
        apiCall('/api/my-analytics').then(statsData => {
            const totalViewsElement = document.getElementById('total-views');
            const totalProjectsElement = document.getElementById('total-projects');

            if (totalViewsElement) {
                totalViewsElement.textContent = formatNumber(statsData.total_views || 0);
            }
            if (totalProjectsElement) {
                // Показываем только проекты с доступом
                const accessibleProjectsCount = currentProjects.filter(p => p.has_access !== false).length;
                totalProjectsElement.textContent = accessibleProjectsCount;
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

        // Загружаем статистику Email Farm
        loadEmailFarmStats();

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

        // Сохраняем всех пользователей
        allUsers = users;

        // Сохраняем данные пользователей
        if (usersMap.size > 0) {
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
    // Запоминаем откуда открыли управление проектами для правильной навигации "Назад"
    const currentPage = document.querySelector('.page:not(.hidden)');
    const currentPageId = currentPage ? currentPage.id : 'admin-page';
    projectManagementOpenedFrom = currentPageId;
    console.log('🔍 [Navigation] Opening project management from page:', currentPageId, '→ projectManagementOpenedFrom:', projectManagementOpenedFrom);

    document.querySelectorAll('.page').forEach(page => page.classList.add('hidden'));
    document.getElementById('project-management-page').classList.remove('hidden');
    loadProjectManagementList();
}

function closeProjectManagement() {
    console.log('🔙 [Navigation] Closing project management, projectManagementOpenedFrom:', projectManagementOpenedFrom);
    document.getElementById('project-management-page').classList.add('hidden');

    // Возвращаемся на ту страницу откуда пришли
    const pageToShow = document.getElementById(projectManagementOpenedFrom);

    if (pageToShow) {
        console.log('🔙 [Navigation] Returning to page:', projectManagementOpenedFrom);
        pageToShow.classList.remove('hidden');
    } else {
        // Fallback на admin-page если страница не найдена
        console.log('🔙 [Navigation] Page not found, returning to admin-page');
        document.getElementById('admin-page').classList.remove('hidden');
    }
}

async function clearAllSnapshots() {
    // Подтверждение
    const confirmed = confirm('⚠️ ВНИМАНИЕ!\n\nЭто удалит ВСЕ исторические данные snapshots и daily stats из базы данных.\n\n"ПРИРОСТ 24Ч" будет = 0 до накопления новой истории.\n\nПродолжить?');

    if (!confirmed) {
        return;
    }

    try {
        const result = await apiCall('/api/admin/clear-snapshots', {
            method: 'POST'
        });

        console.log('✅ Snapshots cleared:', result);

        alert(`✅ Очистка завершена!\n\nУдалено snapshots: ${result.deleted_snapshots}\nУдалено daily stats: ${result.deleted_daily_stats}\n\nТеперь "ПРИРОСТ 24Ч" будет показывать 0 до накопления новой истории.`);
    } catch (error) {
        console.error('❌ Error clearing snapshots:', error);
        alert('❌ Ошибка при очистке: ' + error.message);
    }
}

// Debug logger
function debugLog(message, data = null) {
    console.log(message, data);
}

async function loadProjectManagementList() {
    const VERSION = 'v1764342999';
    debugLog(`🔄 НОВАЯ ВЕРСИЯ ${VERSION} - Начало загрузки`);

    const projectsList = document.getElementById('project-management-list');
    const countElement = document.getElementById('project-management-shown');

    try {
        debugLog('📊 currentProjects глобальная переменная', { count: currentProjects ? currentProjects.length : 0, currentProjects });

        // ПОКАЗЫВАЕМ DEBUG ИНФОРМАЦИЮ ПРЯМО В UI
        projectsList.innerHTML = `<div class="empty-state">
            DEBUG ${VERSION}<br>
            currentProjects.length = ${currentProjects ? currentProjects.length : 0}<br>
            Загрузка проектов...
        </div>`;
        if (countElement) countElement.textContent = '...';

        // Если currentProjects пуст, загружаем из API
        let projects = currentProjects || [];
        if (projects.length === 0) {
            debugLog('📥 currentProjects пуст, загружаем из API');
            projects = await apiCall('/api/projects');
            currentProjects = projects;
            debugLog('✅ Проекты загружены из API', { count: projects.length });
        }

        debugLog('✅ Используем проекты из currentProjects', { count: projects.length, projects });

        // Показываем количество загруженных проектов
        projectsList.innerHTML = `<div class="empty-state">Найдено ${projects.length} проектов. Загрузка аналитики...</div>`;

        // Обновляем глобальное состояние
        currentProjects = projects;

        allProjectsList = [];

        // Загружаем аналитику для каждого проекта
        for (let i = 0; i < projects.length; i++) {
            const project = projects[i];
            console.log(`📈 Loading analytics for project: ${project.name} (ID: ${project.id})`);

            // Обновляем индикатор загрузки
            projectsList.innerHTML = `<div class="empty-state">Загрузка аналитики... (${i + 1}/${projects.length})</div>`;

            try {
                const response = await fetch(`${API_BASE_URL}/api/projects/${project.id}/analytics`, {
                    headers: { 'X-Telegram-Init-Data': tg.initData }
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
                        profilesCount: Object.values(analytics.users_stats || {}).reduce((sum, user) => sum + (user.profiles_count || 0), 0),
                        isFinished: project.is_finished || false
                    });
                } else {
                    // Если analytics не загрузился, добавляем проект с нулевыми данными
                    console.warn(`Failed to load analytics for project ${project.id}: ${response.status}`);
                    allProjectsList.push({
                        id: project.id,
                        name: project.name,
                        targetViews: project.target_views,
                        kpiViews: project.kpi_views || 1000,
                        totalViews: 0,
                        progress: 0,
                        usersCount: 0,
                        profilesCount: 0,
                        isFinished: project.is_finished || false
                    });
                }
            } catch (error) {
                // В случае ошибки также добавляем проект с нулевыми данными
                console.error(`Error loading analytics for project ${project.id}:`, error);
                allProjectsList.push({
                    id: project.id,
                    name: project.name,
                    targetViews: project.target_views,
                    kpiViews: project.kpi_views || 1000,
                    totalViews: 0,
                    progress: 0,
                    usersCount: 0,
                    profilesCount: 0,
                    isFinished: project.is_finished || false
                });
            }
        }

        console.log('✅ Final allProjectsList:', allProjectsList.length, allProjectsList);
        renderProjectManagementList(allProjectsList);
    } catch (error) {
        console.error('❌ Failed to load projects:', error);
        const projectsList = document.getElementById('project-management-list');
        const countElement = document.getElementById('project-management-shown');
        projectsList.innerHTML = `<div class="empty-state">❌ Ошибка загрузки: ${error.message || error}</div>`;
        if (countElement) countElement.textContent = '0';
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
        // Определяем статус завершенности проекта
        const finishedBadge = project.isFinished ? '<span style="color: #4CAF50; margin-left: 8px;">🏁 Завершен</span>' : '';

        return `
            <div class="admin-user-item" onclick="openProjectDetailsFromAdmin('${project.id}')">
                <div class="admin-user-info">
                    <div class="admin-user-avatar project-icon">
                        <i class="fa-solid fa-folder-open"></i>
                    </div>
                    <div class="admin-user-details">
                        <div class="admin-user-name">${project.name}${finishedBadge}</div>
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
    // Use openProject with 'admin' mode for dynamic button rendering
    await openProject(projectId, 'admin');

    // Load additional admin-specific data
    await loadProjectDetailsForAdmin(projectId);
}

// closeProjectDetails() - moved to common functions section (line 650)
// Navigation now handled dynamically based on projectOpenedFrom variable

async function loadProjectDetailsForAdmin(projectId) {
    try {
        // Сохраняем ID текущего проекта
        window.currentProjectId = projectId;
        currentProjectId = projectId;

        // Загружаем детальную информацию о проекте (используем apiCall для избежания кэширования)
        const analytics = await apiCall(`/api/projects/${projectId}/analytics`);
        console.log('✅ Analytics loaded successfully:', analytics);
        console.log('🔍 DEBUG: analytics.total_videos =', analytics.total_videos);
        console.log('🔍 DEBUG: analytics.total_profiles =', analytics.total_profiles);
        console.log('🔍 DEBUG: Backend version =', analytics.backend_version || 'OLD VERSION');
        console.log('🔍 DEBUG: progress_percent from backend =', analytics.progress_percent);
        console.log('🔍 DEBUG: total_views =', analytics.total_views, 'target_views =', analytics.target_views);
        currentProjectDetailsData = analytics;

        // Обновляем название проекта
        document.getElementById('project-details-name').textContent = analytics.project.name;

        // Обновляем общую статистику
        document.getElementById('pd-total-views').textContent = formatNumber(analytics.total_views);
        document.getElementById('pd-target-views').textContent = formatNumber(analytics.target_views);
        document.getElementById('pd-progress').textContent = `${analytics.progress_percent}%`;

        const usersCount = Object.keys(analytics.users_stats || {}).length;
        document.getElementById('pd-total-users').textContent = usersCount;

        // Используем total_profiles из API вместо подсчета из users_stats
        const totalProfiles = analytics.total_profiles || Object.values(analytics.users_stats || {}).reduce((sum, user) => sum + (user.profiles_count || 0), 0);
        console.log('🔍 DEBUG: totalProfiles =', totalProfiles);
        document.getElementById('pd-total-profiles').textContent = totalProfiles;

        // Подсчитываем количество уникальных тематик
        const allTopics = new Set();
        Object.values(analytics.users_stats || {}).forEach(user => {
            if (user.topics) {
                Object.keys(user.topics).forEach(topic => allTopics.add(topic));
            }
        });
        document.getElementById('pd-total-topics').textContent = allTopics.size;

        // Подсчитываем общее количество видео (если есть в аналитике)
        const totalVideos = analytics.total_videos || 0;
        console.log('🔍 DEBUG FRONTEND: analytics.total_videos =', analytics.total_videos);
        console.log('🔍 DEBUG FRONTEND: totalVideos =', totalVideos);
        document.getElementById('pd-total-videos').textContent = totalVideos;

        // Обновляем прогресс бар
        document.getElementById('pd-progress-bar').style.width = `${Math.min(analytics.progress_percent, 100)}%`;

        // Рендерим список участников
        renderProjectUsersList(analytics.users_stats);

        // Загружаем социальные аккаунты в режиме admin
        await loadProjectSocialAccounts(projectId, 'admin');

    } catch (error) {
        console.error('Failed to load project details:', error);
        showError(`Не удалось загрузить детали проекта: ${error.message}`);
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

// Импорт данных из Google Sheets в БД
async function importFromSheets() {
    if (!currentProjectId) {
        showError('Проект не выбран');
        return;
    }

    try {
        // Показываем индикатор загрузки
        const importButton = event.target.closest('button');
        const originalText = importButton.innerHTML;
        importButton.disabled = true;
        importButton.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Импорт...';

        // Вызываем API
        const response = await apiCall(`/api/projects/${currentProjectId}/import_from_sheets`, {
            method: 'POST'
        });

        if (response.success) {
            showSuccess(`Импортировано: ${response.updated} обновлено, ${response.skipped} пропущено из ${response.total}`);

            // Обновляем данные проекта
            await loadProjectDetailsForAdmin(currentProjectId);
        } else {
            showError(response.message || 'Не удалось импортировать данные');
        }

        // Восстанавливаем кнопку
        importButton.disabled = false;
        importButton.innerHTML = originalText;

    } catch (error) {
        console.error('Failed to import from sheets:', error);

        // Восстанавливаем кнопку
        if (event && event.target) {
            const importButton = event.target.closest('button');
            if (importButton) {
                importButton.disabled = false;
                importButton.innerHTML = '<i class="fa-solid fa-download"></i> Импорт из Google';
            }
        }

        const errorMessage = error.message || '';
        if (errorMessage.includes('503')) {
            showError('Google Sheets не подключен');
        } else if (errorMessage.includes('403')) {
            showError('У вас нет доступа к этому проекту');
        } else if (errorMessage.includes('404')) {
            showError('Проект не найден');
        } else {
            showError('Ошибка при импорте данных');
        }
    }
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
    document.getElementById('toggle-threads').checked = true;
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
        youtube: document.getElementById('toggle-youtube').checked,
        threads: document.getElementById('toggle-threads').checked
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
        // Создаём проект через API
        const response = await apiCall('/api/admin/projects', {
            method: 'POST',
            body: JSON.stringify(projectData)
        });

        if (response.success) {
            closeAddProjectModal();
            showSuccess(`Проект "${projectName}" создан успешно!`);

            // Перезагружаем все проекты (включая недоступные)
            const projectsData = await apiCall('/api/projects');
            currentProjects = projectsData.projects || [];

            // Обновляем UI
            renderProjects(currentProjects);

            // Обновляем список проектов в управлении
            await loadProjectManagementList();
        } else {
            showError('Не удалось создать проект');
        }

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
// ==================== SOCIAL ACCOUNTS MANAGEMENT ====================
let currentProjectId = null;
let currentProjectMode = 'user'; // Track current project viewing mode

// Wizard state
let wizardData = {
    platform: '',
    username: '',
    profileLink: '',
    status: '',
    topic: ''
};

function openAddSocialAccountModal() {
    document.getElementById('add-social-account-modal').classList.remove('hidden');

    // Reset wizard to step 1
    document.getElementById('profile-step-1').classList.remove('hidden');
    document.getElementById('profile-step-2').classList.add('hidden');
    document.getElementById('profile-step-3').classList.add('hidden');
    document.getElementById('profile-step-4').classList.add('hidden');

    // Clear input
    document.getElementById('profile-url-input').value = '';

    // Reset wizard data
    wizardData = {
        platform: '',
        username: '',
        profileLink: '',
        status: '',
        topic: ''
    };
}

function closeAddSocialAccountModal() {
    document.getElementById('add-social-account-modal').classList.add('hidden');
}

// Step 1 -> Step 2: Auto-detect platform and username from URL
function goToStep2() {
    const urlInput = document.getElementById('profile-url-input').value.trim();

    if (!urlInput) {
        showError('Пожалуйста, введите ссылку');
        return;
    }

    // Auto-detection logic
    let platform = '';
    let username = '';
    let profileLink = urlInput;

    try {
        const url = new URL(urlInput);
        const hostname = url.hostname.toLowerCase();

        // Detect platform
        if (hostname.includes('tiktok.com')) {
            platform = 'tiktok';
            // Extract username: tiktok.com/@username
            const match = url.pathname.match(/@([^/?]+)/);
            username = match ? match[1] : '';
        } else if (hostname.includes('instagram.com')) {
            platform = 'instagram';
            // Extract username: instagram.com/username or instagram.com/username/
            const match = url.pathname.match(/^\/([^/?]+)/);
            username = match ? match[1] : '';
        } else if (hostname.includes('youtube.com') || hostname.includes('youtu.be')) {
            platform = 'youtube';
            // Extract channel name from various YouTube URL formats
            // Supports: youtube.com/@username, youtube.com/c/username, youtube.com/channel/ID, youtube.com/user/username
            let channelMatch = url.pathname.match(/@([^/?]+)/);  // youtube.com/@username
            if (!channelMatch) {
                channelMatch = url.pathname.match(/\/(c|channel|user)\/([^/?]+)/);  // youtube.com/c/username
            }
            username = channelMatch ? (channelMatch[2] || channelMatch[1]) : '';
        } else if (hostname.includes('facebook.com') || hostname.includes('fb.com')) {
            platform = 'facebook';
            // Extract username
            const match = url.pathname.match(/^\/([^/?]+)/);
            username = match ? match[1] : '';
        } else {
            showError('Неподдерживаемая платформа. Используйте TikTok, Instagram, YouTube или Facebook');
            return;
        }

        if (!username) {
            showError('Не удалось извлечь username из ссылки');
            return;
        }

        // Save to wizard data
        wizardData.platform = platform;
        wizardData.username = username;
        wizardData.profileLink = profileLink;

        // Update username display in Step 2
        document.getElementById('profile-ready-username').textContent = `@${username}`;

        // Move to step 2
        document.getElementById('profile-step-1').classList.add('hidden');
        document.getElementById('profile-step-2').classList.remove('hidden');

    } catch (error) {
        showError('Некорректная ссылка. Введите полный URL (например: https://tiktok.com/@username)');
        return;
    }
}

// Step 2 -> Step 3: Select status
function selectStatus(status) {
    wizardData.status = status;

    // Move to step 3
    document.getElementById('profile-step-2').classList.add('hidden');
    document.getElementById('profile-step-3').classList.remove('hidden');
}

// Step 3 -> Submit: Select topic and submit
function selectTopic(topic) {
    wizardData.topic = topic;

    // Submit the account
    submitSocialAccount();
}

// Step 3 -> Step 4: Open custom topic input
function openCustomTopic() {
    document.getElementById('profile-step-3').classList.add('hidden');
    document.getElementById('profile-step-4').classList.remove('hidden');
    document.getElementById('profile-custom-topic-input').value = '';
    document.getElementById('profile-custom-topic-input').focus();
}

// Step 4 -> Submit: Custom topic
function submitCustomTopic() {
    const customTopic = document.getElementById('profile-custom-topic-input').value.trim();

    if (!customTopic) {
        showError('Пожалуйста, введите название тематики');
        return;
    }

    wizardData.topic = customTopic;

    // Submit the account
    submitSocialAccount();
}

// Final submission
async function submitSocialAccount() {
    // Use global currentProjectId (set by openProject)
    const projectId = window.currentProjectId || currentProjectId;

    if (!projectId) {
        console.error('Internal Error: No Project ID set');
        showError('Internal Error: No Project ID. Please reopen the project.');
        return;
    }

    // Автоматически определяем telegram_user из текущего пользователя
    let telegramUser = 'Unknown'; // Default fallback
    if (currentUser) {
        if (currentUser.username) {
            telegramUser = `@${currentUser.username}`;
        } else if (currentUser.first_name) {
            telegramUser = currentUser.first_name;
        } else if (currentUser.id) {
            telegramUser = `ID:${currentUser.id}`;
        }
    }

    console.log('🔍 FRONTEND DEBUG: Auto-detected telegram_user =', telegramUser);
    console.log('🔍 FRONTEND DEBUG: Profile username (from link) =', wizardData.username);

    const requestBody = {
        platform: wizardData.platform,
        username: wizardData.username,  // Username профиля соц. сети (извлечен из ссылки)
        profile_link: wizardData.profileLink,
        status: wizardData.status,
        topic: wizardData.topic || '',
        telegram_user: telegramUser  // Telegram username текущего пользователя
    };

    console.log('🔍 FRONTEND DEBUG: Full request body =', requestBody);

    try {
        const response = await apiCall(`/api/projects/${projectId}/accounts`, {
            method: 'POST',
            body: JSON.stringify(requestBody)
        });

        if (response.success) {
            showSuccess('Аккаунт добавлен');
            closeAddSocialAccountModal();

            // Обновляем список с текущим режимом
            await loadProjectSocialAccounts(projectId, currentProjectMode);
        } else {
            showError('Не удалось добавить аккаунт');
        }
    } catch (error) {
        console.error('Failed to add social account:', error);
        // Проверяем, если это ошибка дубликата
        if (error.message && error.message.includes('уже добавлен')) {
            showSuccess('Такой аккаунт уже добавлен');
            closeAddSocialAccountModal();
        } else {
            showError(error.message || 'Ошибка при добавлении аккаунта');
        }
    }
}

// Функции для добавления пользователя в проект
function openAddUserToProjectModal() {
    if (!currentProjectId) {
        showError('Проект не выбран');
        return;
    }

    document.getElementById('add-user-to-project-modal').classList.remove('hidden');
    document.getElementById('add-user-username').value = '';
}

function closeAddUserToProjectModal() {
    document.getElementById('add-user-to-project-modal').classList.add('hidden');
}

async function submitUserToProject() {
    const usernameInput = document.getElementById('add-user-username').value.trim();

    // Валидация
    if (!usernameInput) {
        showError('Пожалуйста, введите username');
        return;
    }

    if (!currentProjectId) {
        showError('Проект не выбран');
        return;
    }

    // Strip @ from username if present
    const username = usernameInput.startsWith('@') ? usernameInput.substring(1) : usernameInput;

    try {
        const response = await apiCall(`/api/projects/${currentProjectId}/users`, {
            method: 'POST',
            body: JSON.stringify({
                username: username
            })
        });

        // Success: user was added successfully
        if (response.success) {
            showSuccess('Пользователь добавлен');
            closeAddUserToProjectModal();

            // Обновляем детали проекта
            await loadProjectDetailsForAdmin(currentProjectId);
        } else {
            showError(response.error || 'Не удалось добавить пользователя');
        }
    } catch (error) {
        console.error('Failed to add user to project:', error);

        // Handle specific error cases
        const errorMessage = error.message || '';

        // Try to parse the error detail from FastAPI JSON response
        let errorDetail = '';
        try {
            const match = errorMessage.match(/API Error \(\d+\): (.+)/);
            if (match && match[1]) {
                const parsedError = JSON.parse(match[1]);
                errorDetail = parsedError.detail || '';
            }
        } catch (e) {
            errorDetail = errorMessage;
        }

        // User already in project - show success/info notification and close modal (success behavior)
        if (errorMessage.includes('400') || errorMessage.includes('409') ||
            errorDetail.toLowerCase().includes('already in this project') ||
            errorDetail.toLowerCase().includes('already in project') ||
            errorDetail.toLowerCase().includes('user already in project')) {
            showSuccess('Пользователь уже добавлен');
            closeAddUserToProjectModal();
            // Reload project data to ensure UI is in sync
            await loadProjectDetailsForAdmin(currentProjectId);
            return;
        }

        // Other error cases
        if (errorMessage.includes('404') || errorDetail.toLowerCase().includes('not found')) {
            showError('Пользователь не найден. Попросите их запустить бота командой /start');
        } else if (errorMessage.includes('403') || errorDetail.toLowerCase().includes('access denied')) {
            showError('У вас нет доступа к этому проекту');
        } else {
            showError(errorDetail || 'Ошибка при добавлении пользователя');
        }
    }
}

// Regular user view - Add user modal functions
function openAddUserModal() {
    document.getElementById('add-user-modal').classList.remove('hidden');
    document.getElementById('add-user-username-regular').value = '';
    document.getElementById('add-user-username-regular').focus();
}

function closeAddUserModal() {
    document.getElementById('add-user-modal').classList.add('hidden');
}

async function submitUserToProjectRegular() {
    const usernameInput = document.getElementById('add-user-username-regular').value.trim();

    // Валидация
    if (!usernameInput) {
        showError('Пожалуйста, введите username');
        return;
    }

    if (!currentProjectId) {
        showError('Проект не выбран');
        return;
    }

    // Strip @ from username if present
    const username = usernameInput.startsWith('@') ? usernameInput.substring(1) : usernameInput;

    try {
        const response = await apiCall(`/api/projects/${currentProjectId}/users`, {
            method: 'POST',
            body: JSON.stringify({
                username: username
            })
        });

        // Success: user was added successfully
        if (response.success) {
            showSuccess('Пользователь добавлен');
            closeAddUserModal();

            // Обновляем детали проекта
            await loadProjectDetails(currentProjectId);
        } else {
            showError(response.error || 'Не удалось добавить пользователя');
        }
    } catch (error) {
        console.error('Failed to add user to project:', error);

        // Handle specific error cases
        const errorMessage = error.message || '';

        // Try to parse the error detail from FastAPI JSON response
        let errorDetail = '';
        try {
            const match = errorMessage.match(/API Error \(\d+\): (.+)/);
            if (match && match[1]) {
                const parsedError = JSON.parse(match[1]);
                errorDetail = parsedError.detail || '';
            }
        } catch (e) {
            errorDetail = errorMessage;
        }

        // User already in project - show success/info notification and close modal (success behavior)
        if (errorDetail.toLowerCase().includes('already in this project') ||
            errorDetail.toLowerCase().includes('already in project')) {
            showSuccess('Пользователь уже в проекте');
            closeAddUserModal();
            // Reload project data to ensure UI is in sync
            await loadProjectDetails(currentProjectId);
            return;
        }

        // Other error cases
        if (errorMessage.includes('404') || errorDetail.toLowerCase().includes('not found')) {
            showError('Пользователь не найден. Попросите их запустить бота командой /start');
        } else if (errorMessage.includes('403') || errorDetail.toLowerCase().includes('access denied')) {
            showError('У вас нет доступа к этому проекту');
        } else {
            showError(errorDetail || 'Ошибка при добавлении пользователя');
        }
    }
}

async function loadProjectSocialAccounts(projectId, mode = 'user') {
    try {
        const response = await apiCall(`/api/projects/${projectId}/accounts`);

        if (response.success) {
            let accounts = response.accounts;
            console.log('🔍 DEBUG: Total accounts from API:', accounts.length);
            console.log('🔍 DEBUG: All accounts:', accounts);

            // В режиме user фильтруем только аккаунты текущего пользователя
            if (mode === 'user' && currentUser) {
                const myTelegramUser = currentUser.username
                    ? `@${currentUser.username}`
                    : currentUser.first_name || `ID:${currentUser.id}`;

                console.log('🔍 DEBUG: My telegram_user:', myTelegramUser);

                // Показываем аккаунты где telegram_user совпадает ИЛИ пустой (для обратной совместимости)
                accounts = accounts.filter(account => {
                    const accountTgUser = account.telegram_user || '';
                    const match = accountTgUser === myTelegramUser || accountTgUser === '';
                    console.log(`🔍 Account ${account.username}: telegram_user="${accountTgUser}" -> ${match ? 'SHOW' : 'HIDE'}`);
                    return match;
                });
                console.log('🔍 Filtered accounts for user:', myTelegramUser, 'Count:', accounts.length);
            }

            renderProjectSocialAccountsList(accounts, mode);
        }
    } catch (error) {
        console.error('Failed to load social accounts:', error);
    }
}

function renderProjectSocialAccountsList(accounts, mode = 'user') {
    const accountsList = document.getElementById('profiles-list');
    const profilesCount = document.getElementById('profiles-count');

    if (!accounts || accounts.length === 0) {
        accountsList.innerHTML = '<p class="no-profiles">Нет социальных аккаунтов</p>';
        profilesCount.textContent = '0';
        return;
    }

    // Обновляем счетчик
    profilesCount.textContent = accounts.length;

    // Группируем по платформам
    const groupedAccounts = {};
    accounts.forEach(account => {
        if (!groupedAccounts[account.platform]) {
            groupedAccounts[account.platform] = [];
        }
        groupedAccounts[account.platform].push(account);
    });

    // Иконки платформ
    const platformIcons = {
        tiktok: '📱',
        instagram: '📷',
        youtube: '🎬',
        facebook: '👤'
    };

    const platformNames = {
        tiktok: 'TikTok',
        instagram: 'Instagram',
        youtube: 'YouTube',
        facebook: 'Facebook'
    };

    // Цвета статусов
    const statusColors = {
        NEW: '#4CAF50',
        OLD: '#FF9800',
        Ban: '#F44336'
    };

    let html = '';

    Object.keys(groupedAccounts).forEach(platform => {
        const platformAccounts = groupedAccounts[platform];

        html += `
            <div style="margin-bottom: 20px;">
                <h4 style="margin: 10px 0; color: rgba(255,255,255,0.9);">
                    ${platformIcons[platform]} ${platformNames[platform]} (${platformAccounts.length})
                </h4>
        `;

        platformAccounts.forEach(account => {
            // Извлекаем username из URL
            let displayUsername = account.username;
            const url = account.profile_link || '';

            if (url.includes('/@')) {
                // TikTok, Instagram: https://www.tiktok.com/@username
                const parts = url.split('/@');
                if (parts[1]) {
                    displayUsername = parts[1].split('?')[0].split('/')[0];
                }
            } else if (url.includes('facebook.com/share/') || url.includes('facebook.com/')) {
                // Facebook: извлекаем ID или username
                const urlParts = url.split('/');
                const shareIndex = urlParts.indexOf('share');
                if (shareIndex !== -1 && urlParts[shareIndex + 1]) {
                    displayUsername = urlParts[shareIndex + 1].split('?')[0];
                } else {
                    const lastPart = urlParts[urlParts.length - 1].split('?')[0];
                    if (lastPart && lastPart !== '') {
                        displayUsername = lastPart;
                    } else if (urlParts[urlParts.length - 2]) {
                        displayUsername = urlParts[urlParts.length - 2];
                    }
                }
            }

            // Форматируем числа с разделителями тысяч
            const formatNumber = (num) => {
                return num ? num.toLocaleString('ru-RU') : '0';
            };

            html += `
                <div class="admin-user-item" style="margin-bottom: 10px;">
                    <div class="admin-user-info">
                        <div class="admin-user-details">
                            <div class="admin-user-name">${displayUsername}</div>
                            <div class="admin-user-stats" style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                                <span style="background: ${statusColors[account.status]}; padding: 2px 8px; border-radius: 4px; font-size: 11px;">
                                    ${account.status}
                                </span>
                                ${account.topic ? `<span style="color: rgba(255,255,255,0.6);">${account.topic}</span>` : ''}
                                <span style="color: rgba(255,255,255,0.8); font-size: 12px;">
                                    <i class="fa-solid fa-video" style="color: #2196F3;"></i> ${formatNumber(account.videos || 0)}
                                </span>
                                <span style="color: rgba(255,255,255,0.8); font-size: 12px;">
                                    <i class="fa-solid fa-eye" style="color: #4CAF50;"></i> ${formatNumber(account.views || 0)}
                                </span>
                                <a href="${account.profile_link}" target="_blank" style="color: #2196F3; text-decoration: none;">
                                    <i class="fa-solid fa-external-link"></i>
                                </a>
                            </div>
                        </div>
                    </div>
                    ${mode === 'admin' ? `
                    <button
                        onclick="deleteSocialAccount('${account.id}')"
                        style="background: #F44336; border: none; padding: 8px 12px; border-radius: 8px; color: white; cursor: pointer;"
                    >
                        <i class="fa-solid fa-trash"></i>
                    </button>
                    ` : ''}
                </div>
            `;
        });

        html += '</div>';
    });

    accountsList.innerHTML = html;
}

async function deleteSocialAccount(accountId) {
    if (!confirm('Вы уверены, что хотите удалить этот аккаунт?')) {
        return;
    }

    try {
        const response = await apiCall(`/api/accounts/${accountId}`, {
            method: 'DELETE'
        });

        if (response.success) {
            showSuccess('Аккаунт успешно удален');

            // Обновляем список с текущим режимом
            await loadProjectSocialAccounts(currentProjectId, currentProjectMode);
        } else {
            showError('Не удалось удалить аккаунт');
        }
    } catch (error) {
        console.error('Failed to delete social account:', error);
        showError('Ошибка при удалении аккаунта');
    }
}

// Обработчик для показа custom topic поля
document.addEventListener('DOMContentLoaded', () => {
    const topicSelect = document.getElementById('social-account-topic');
    const customTopicInput = document.getElementById('social-account-custom-topic');

    if (topicSelect) {
        topicSelect.addEventListener('change', (e) => {
            if (e.target.value === 'custom') {
                customTopicInput.classList.remove('hidden');
            } else {
                customTopicInput.classList.add('hidden');
            }
        });
    }
});

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
window.deleteProject = deleteProject;
window.finishProject = finishProject;
window.refreshProjectStats = refreshProjectStats;
window.openAddProjectModal = openAddProjectModal;
window.closeAddProjectModal = closeAddProjectModal;
window.submitNewProject = submitNewProject;
window.openAddSocialAccountModal = openAddSocialAccountModal;
window.closeAddSocialAccountModal = closeAddSocialAccountModal;
window.goToStep2 = goToStep2;
window.selectStatus = selectStatus;
window.selectTopic = selectTopic;
window.openCustomTopic = openCustomTopic;
window.submitCustomTopic = submitCustomTopic;
window.submitSocialAccount = submitSocialAccount;
window.deleteSocialAccount = deleteSocialAccount;

// ============ EMAIL FARM FUNCTIONS ============

// Загрузка списка моих почт
async function loadMyEmails() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/emails/my_list`, {
            headers: {
                'x-telegram-init-data': window.Telegram.WebApp.initData
            }
        });

        if (!response.ok) {
            throw new Error('Failed to load emails');
        }

        const data = await response.json();

        // Обновляем лимиты
        document.getElementById('user-active-emails').textContent = data.emails.filter(e => e.status === 'active').length;
        document.getElementById('user-max-emails').textContent = data.limit.max_active_emails;
        document.getElementById('user-email-access').textContent = data.limit.can_access_emails ? '✅' : '❌';

        // Отображаем список почт
        const listContainer = document.getElementById('my-emails-list');

        if (data.emails.length === 0) {
            listContainer.innerHTML = '<p style="text-align: center; color: #888;">У вас пока нет почт</p>';
            return;
        }

        listContainer.innerHTML = data.emails.map(email => `
            <div class="email-item" id="email-item-${email.id}">
                <div class="email-info">
                    <span class="email-address">📧 ${email.email}</span>
                    <div class="email-code-display" id="email-code-${email.id}" style="display: none; margin: 8px 0; padding: 10px; background: linear-gradient(135deg, rgba(74, 222, 128, 0.15) 0%, rgba(34, 197, 94, 0.15) 100%); border: 1px solid rgba(74, 222, 128, 0.3); border-radius: 8px;">
                        <div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 4px;">Код верификации:</div>
                        <div style="font-size: 20px; font-weight: 700; color: #4ade80; letter-spacing: 2px; font-family: 'Courier New', monospace;"></div>
                    </div>
                    <span class="email-status status-${email.status.toLowerCase()}">${email.status}</span>
                </div>
                <div class="email-actions">
                    ${email.status === 'active' ? `
                        <button class="btn-secondary" onclick="checkEmailCode(${email.id})">
                            🔍 Проверить код
                        </button>
                        <button class="btn-danger" onclick="markEmailBanned(${email.id})">
                            🚫 Забанена
                        </button>
                    ` : ''}
                </div>
            </div>
        `).join('');

    } catch (error) {
        console.error('Error loading emails:', error);
        showNotification('Ошибка загрузки почт: ' + error.message, 'error');
    }
}

// Получить новую почту
async function allocateEmail() {
    const button = document.getElementById('allocate-email-btn');
    button.disabled = true;
    button.textContent = 'Загрузка...';

    try {
        const response = await fetch(`${API_BASE_URL}/api/emails/allocate`, {
            method: 'POST',
            headers: {
                'x-telegram-init-data': window.Telegram.WebApp.initData
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to allocate email');
        }

        showNotification(`✅ Получена почта: ${data.email}`, 'success');
        loadMyEmails(); // Перезагружаем список

    } catch (error) {
        console.error('Error allocating email:', error);
        showNotification('Ошибка: ' + error.message, 'error');
    } finally {
        button.disabled = false;
        button.textContent = '📧 Получить новую почту';
    }
}

// Проверить код в почте
async function checkEmailCode(emailId) {
    // Находим кнопку проверки
    const checkButton = document.querySelector(`#email-item-${emailId} .btn-secondary`);

    // Проверяем, не была ли уже получена почта (кнопка изменена)
    if (checkButton && checkButton.textContent.includes('Аккаунт создан')) {
        showNotification('Код уже был получен для этой почты', 'info');
        return;
    }

    try {
        // Меняем текст кнопки на индикатор загрузки
        if (checkButton) {
            checkButton.disabled = true;
            checkButton.textContent = '🔍 Ищу код...';
        }

        showNotification('🔍 Проверяем почту...', 'info');

        const response = await fetch(`${API_BASE_URL}/api/emails/${emailId}/check_code`, {
            method: 'POST',
            headers: {
                'x-telegram-init-data': window.Telegram.WebApp.initData
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to check email');
        }

        if (!data.is_safe) {
            // Возвращаем кнопку в исходное состояние при ошибке
            if (checkButton) {
                checkButton.disabled = false;
                checkButton.textContent = '🔍 Проверить код';
            }
            showNotification(`⚠️ ВНИМАНИЕ! Подозрительное письмо!\n\nПричина: ${data.reason}\n\nТема: ${data.subject}\n\nАлерт отправлен администраторам.`, 'error');
            return;
        }

        if (data.verification_code) {
            showNotification(`✅ Код получен: ${data.verification_code}\n\nТема: ${data.subject}\nОт: ${data.from}`, 'success');

            // Отображаем код в UI
            const codeDisplay = document.getElementById(`email-code-${emailId}`);
            if (codeDisplay) {
                codeDisplay.style.display = 'block';
                const codeValueElement = codeDisplay.querySelector('div:last-child');
                if (codeValueElement) {
                    codeValueElement.textContent = data.verification_code;
                }
            }

            // Меняем кнопку на "Аккаунт создан" (но оставляем кликабельной для показа уведомления)
            if (checkButton) {
                checkButton.textContent = '✅ Аккаунт создан';
                checkButton.disabled = false;
                checkButton.style.background = 'linear-gradient(135deg, #4ade80 0%, #22c55e 100%)';
                checkButton.style.cursor = 'pointer';
                checkButton.style.opacity = '1';
            }

            // Копируем код в буфер обмена
            if (navigator.clipboard) {
                navigator.clipboard.writeText(data.verification_code);
                setTimeout(() => {
                    showNotification('📋 Код скопирован в буфер обмена', 'info');
                }, 1500);
            }
        } else {
            // Возвращаем кнопку в исходное состояние если код не найден
            if (checkButton) {
                checkButton.disabled = false;
                checkButton.textContent = '🔍 Проверить код';
            }
            showNotification(`📨 Письмо безопасно\n\nТема: ${data.subject}\nОт: ${data.from}\n\nНо код не найден.`, 'info');
        }

    } catch (error) {
        console.error('Error checking email code:', error);
        // Возвращаем кнопку в исходное состояние при ошибке
        if (checkButton) {
            checkButton.disabled = false;
            checkButton.textContent = '🔍 Проверить код';
        }
        showNotification('Ошибка проверки почты: ' + error.message, 'error');
    }
}

// Пометить почту как забаненную
async function markEmailBanned(emailId) {
    if (!confirm('Вы уверены, что хотите пометить эту почту как забаненную?')) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/emails/${emailId}/mark_banned`, {
            method: 'POST',
            headers: {
                'x-telegram-init-data': window.Telegram.WebApp.initData
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to mark email as banned');
        }

        showNotification('✅ Почта помечена как забаненная', 'success');
        loadMyEmails(); // Перезагружаем список

    } catch (error) {
        console.error('Error marking email as banned:', error);
        showNotification('Ошибка: ' + error.message, 'error');
    }
}

// Экспортируем функции в window
window.loadMyEmails = loadMyEmails;
window.allocateEmail = allocateEmail;
window.checkEmailCode = checkEmailCode;
window.markEmailBanned = markEmailBanned;

// ============ EMAIL FARM ADMIN FUNCTIONS ============

// Открыть управление Email Farm
function openEmailFarmManagement() {
    showPage('email-farm-management');
    loadEmailFarmStats();
}

// Закрыть управление Email Farm
function closeEmailFarmManagement() {
    showPage('admin');
}

// Загрузить статистику Email Farm
async function loadEmailFarmStats() {
    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/emails/stats`, {
            headers: {
                'x-telegram-init-data': window.Telegram.WebApp.initData
            }
        });

        if (!response.ok) {
            throw new Error('Failed to load email farm stats');
        }

        const stats = await response.json();

        document.getElementById('email-farm-total').textContent = stats.total_emails || 0;
        document.getElementById('email-farm-free').textContent = stats.free || 0;
        document.getElementById('email-farm-active').textContent = stats.active || 0;
        document.getElementById('email-farm-banned').textContent = stats.banned || 0;

        // Обновляем счетчик в админке
        document.getElementById('admin-total-emails-display').textContent = stats.total_emails || 0;

    } catch (error) {
        console.error('Error loading email farm stats:', error);
        showNotification('Ошибка загрузки статистики Email Farm', 'error');
    }
}

// Массовая загрузка почт
async function bulkUploadEmails() {
    const textarea = document.getElementById('email-bulk-upload-textarea');
    const button = document.getElementById('bulk-upload-btn');
    const text = textarea.value.trim();

    if (!text) {
        showNotification('Введите почты для загрузки', 'error');
        return;
    }

    // Определяем выбранный тип аутентификации
    const authTypeRadios = document.getElementsByName('auth-type');
    let authType = 'password';
    for (const radio of authTypeRadios) {
        if (radio.checked) {
            authType = radio.value;
            break;
        }
    }

    button.disabled = true;
    button.textContent = 'Загрузка...';

    try {
        // Парсим строки
        const lines = text.split('\n').filter(line => line.trim());
        const accounts = [];

        // Получаем список прокси из localStorage (если есть)
        const savedProxies = JSON.parse(localStorage.getItem('email_farm_proxies') || '[]');
        let proxyIndex = 0;

        for (const line of lines) {
            const parts = line.trim().split(':');

            if (authType === 'oauth2') {
                // Формат OAuth2: email:password:refresh_token:client_id
                if (parts.length < 4) {
                    showNotification(`Неверный формат OAuth2 (нужно 4 части): ${line}`, 'error');
                    continue;
                }

                const email = parts[0].trim();
                const password = parts[1].trim();
                const refresh_token = parts[2].trim();
                const client_id = parts[3].trim();

                // Присваиваем прокси из списка (если есть)
                const proxy = savedProxies[proxyIndex] || null;
                if (savedProxies.length > 0) {
                    proxyIndex = (proxyIndex + 1) % savedProxies.length; // Циклически
                }

                accounts.push({
                    email,
                    password,
                    proxy,
                    refresh_token,
                    client_id,
                    auth_type: 'oauth2'
                });

            } else {
                // Формат Password: email:password:proxy (опционально)
                if (parts.length < 2) {
                    showNotification(`Неверный формат строки: ${line}`, 'error');
                    continue;
                }

                const email = parts[0].trim();
                const password = parts[1].trim();

                // Если есть 3+ части - это прокси
                let proxy = null;
                if (parts.length >= 3) {
                    proxy = parts.slice(2).join(':').trim();
                } else if (savedProxies.length > 0) {
                    // Иначе берем из списка прокси
                    proxy = savedProxies[proxyIndex];
                    proxyIndex = (proxyIndex + 1) % savedProxies.length;
                }

                accounts.push({
                    email,
                    password,
                    proxy,
                    auth_type: 'password'
                });
            }
        }

        if (accounts.length === 0) {
            showNotification('Нет валидных почт для загрузки', 'error');
            return;
        }

        console.log('Загружаем почты:', accounts.length, 'шт.');
        console.log('Auth type:', authType);
        console.log('Первый аккаунт:', accounts[0]);

        // Отправляем на сервер
        const response = await fetch(`${API_BASE_URL}/api/admin/emails/bulk_upload`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-telegram-init-data': window.Telegram.WebApp.initData
            },
            body: JSON.stringify({ accounts })
        });

        console.log('Response status:', response.status);

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to upload emails');
        }

        showNotification(`✅ Загружено: ${data.success}\n❌ Ошибок: ${data.failed}`, 'success');

        // Очищаем текстареа и обновляем статистику
        textarea.value = '';
        loadEmailFarmStats();

        // Показываем ошибки если есть
        if (data.errors && data.errors.length > 0) {
            console.log('Upload errors:', data.errors);
        }

    } catch (error) {
        console.error('Error uploading emails:', error);
        showNotification('Ошибка загрузки почт: ' + error.message, 'error');
    } finally {
        button.disabled = false;
        button.textContent = '📤 Загрузить почты';
    }
}

// Установить лимит пользователю
async function setUserEmailLimit() {
    const userIdInput = document.getElementById('email-limit-user-id');
    const maxEmailsInput = document.getElementById('email-limit-max');
    const accessCheckbox = document.getElementById('email-limit-access');

    const userId = parseInt(userIdInput.value);
    const maxEmails = parseInt(maxEmailsInput.value);
    const canAccess = accessCheckbox.checked;

    if (!userId || isNaN(userId)) {
        showNotification('Введите корректный Telegram User ID', 'error');
        return;
    }

    if (!maxEmails || isNaN(maxEmails) || maxEmails < 0) {
        showNotification('Введите корректное количество почт', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/emails/set_limit`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'x-telegram-init-data': window.Telegram.WebApp.initData
            },
            body: JSON.stringify({
                user_id: userId,
                max_emails: maxEmails,
                can_access: canAccess
            })
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to set limit');
        }

        showNotification(`✅ Лимит установлен для user ${userId}: ${maxEmails} почт`, 'success');

        // Очищаем поле user_id
        userIdInput.value = '';

    } catch (error) {
        console.error('Error setting email limit:', error);
        showNotification('Ошибка установки лимита: ' + error.message, 'error');
    }
}

// Очистить все почты из Email Farm базы
async function clearAllEmails() {
    // Подтверждение
    const confirmed = confirm('⚠️ ВНИМАНИЕ!\n\nЭто удалит ВСЕ почты из Email Farm базы данных!\n\nВы уверены?');

    if (!confirmed) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/admin/emails/clear_all`, {
            method: 'DELETE',
            headers: {
                'x-telegram-init-data': window.Telegram.WebApp.initData
            }
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to clear emails');
        }

        showNotification(`🗑️ Удалено почт: ${data.deleted_emails}, записей истории: ${data.deleted_history}`, 'success');

        // Обновляем статистику
        loadEmailFarmStats();

    } catch (error) {
        console.error('Error clearing emails:', error);
        showNotification('Ошибка очистки Email Farm: ' + error.message, 'error');
    }
}

// ============ Proxy Management ============

function openProxySettings() {
    const modal = document.getElementById('proxy-settings-modal');
    const textarea = document.getElementById('proxy-list-textarea');

    // Загружаем сохраненные прокси
    const savedProxies = JSON.parse(localStorage.getItem('email_farm_proxies') || '[]');
    textarea.value = savedProxies.join('\n');

    modal.classList.remove('hidden');
}

function closeProxySettings() {
    const modal = document.getElementById('proxy-settings-modal');
    modal.classList.add('hidden');
}

function saveProxyList() {
    const textarea = document.getElementById('proxy-list-textarea');
    const text = textarea.value.trim();

    if (!text) {
        showNotification('⚠️ Список прокси пуст. Прокси очищены.', 'info');
        localStorage.setItem('email_farm_proxies', JSON.stringify([]));
        closeProxySettings();
        return;
    }

    // Парсим и валидируем прокси
    const lines = text.split('\n').filter(line => line.trim());
    const validProxies = [];

    for (const line of lines) {
        const proxy = line.trim();

        // Проверяем формат socks5:// или socks5h://
        // Разрешаем любые символы в user:pass, включая дефисы, подчеркивания
        if (/^socks5h?:\/\/.+@.+:\d+$/.test(proxy)) {
            validProxies.push(proxy);
            console.log(`✅ Прокси валиден: ${proxy.substring(0, 30)}...`);
        } else {
            console.warn(`❌ Неверный формат прокси (пропущено): ${proxy}`);
            // Не показываем ошибку - просто пропускаем
        }
    }

    if (validProxies.length === 0) {
        showNotification('❌ Нет валидных прокси для сохранения', 'error');
        console.log('Введенный текст:', text);
        return;
    }

    // Сохраняем в localStorage
    localStorage.setItem('email_farm_proxies', JSON.stringify(validProxies));
    console.log('Сохранено прокси в localStorage:', validProxies);
    showNotification(`✅ Сохранено ${validProxies.length} прокси`, 'success');

    closeProxySettings();
}

// ============ Auth Type Switch ============

// Переключение формата при смене типа auth
document.addEventListener('DOMContentLoaded', () => {
    const authTypeRadios = document.getElementsByName('auth-type');

    authTypeRadios.forEach(radio => {
        radio.addEventListener('change', () => {
            const formatHint = document.getElementById('email-format-hint');
            const formatCode = document.getElementById('email-format-code');
            const textarea = document.getElementById('email-bulk-upload-textarea');

            if (radio.value === 'oauth2') {
                formatHint.textContent = 'Формат OAuth2:';
                formatCode.textContent = 'email:password:refresh_token:client_id';
                textarea.placeholder = 'test1@outlook.com:Pass123!:refresh_token_here:client_id_here';
            } else {
                formatHint.textContent = 'Формат Password:';
                formatCode.textContent = 'email:password:proxy (proxy опционально)';
                textarea.placeholder = 'test1@outlook.com:Pass123!:socks5://user:pass@ip:port\ntest2@outlook.com:Pass456!:';
            }
        });
    });
});

// Экспортируем admin функции
window.openEmailFarmManagement = openEmailFarmManagement;
window.closeEmailFarmManagement = closeEmailFarmManagement;
window.loadEmailFarmStats = loadEmailFarmStats;
window.bulkUploadEmails = bulkUploadEmails;
window.setUserEmailLimit = setUserEmailLimit;
window.clearAllEmails = clearAllEmails;
window.openProxySettings = openProxySettings;
window.closeProxySettings = closeProxySettings;
window.saveProxyList = saveProxyList;
