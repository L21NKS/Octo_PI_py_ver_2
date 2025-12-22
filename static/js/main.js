// Ждём полной загрузки DOM
document.addEventListener('DOMContentLoaded', function () {
    console.log('DOM loaded, initializing OCTO CCTV Dashboard...');

    // ========== ТЕМА (ДЕНЬ/НОЧЬ) ==========
    const themeToggle = document.getElementById('themeToggle');
    const savedTheme = localStorage.getItem('theme') || 'dark';

    // Применяем сохранённую тему
    if (savedTheme === 'light') {
        document.documentElement.setAttribute('data-theme', 'light');
        if (themeToggle) themeToggle.textContent = 'День';
    } else {
        document.documentElement.removeAttribute('data-theme');
        if (themeToggle) themeToggle.textContent = 'Ночь';
    }

    // Обработчик переключения темы
    if (themeToggle) {
        themeToggle.addEventListener('click', function () {
            const currentTheme = document.documentElement.getAttribute('data-theme');

            if (currentTheme === 'light') {
                // Переключаем на тёмную (Ночь)
                document.documentElement.removeAttribute('data-theme');
                localStorage.setItem('theme', 'dark');
                this.textContent = 'Ночь';
            } else {
                // Переключаем на светлую (День)
                document.documentElement.setAttribute('data-theme', 'light');
                localStorage.setItem('theme', 'light');
                this.textContent = 'День';
            }
        });
    }

    // ========== НАВИГАЦИЯ ==========
    document.querySelectorAll('.nav-link[data-page]').forEach(link => {
        link.addEventListener('click', function (e) {
            e.preventDefault();
            const pageId = this.getAttribute('data-page');
            showPage(pageId);

            // Обновляем активные ссылки
            document.querySelectorAll('.nav-link').forEach(l => l.classList.remove('active'));
            this.classList.add('active');
        });
    });

    // ========== СИСТЕМА УПРАВЛЕНИЯ ==========
    const startBtn = document.getElementById('startSystem');
    const stopBtn = document.getElementById('stopSystem');

    if (startBtn) {
        startBtn.addEventListener('click', async function () {
            if (!confirm('Запустить систему CCTV с текущими настройками из раздела Settings?')) {
                return;
            }

            // Запускаем анимацию загрузки
            const originalText = this.textContent;
            this.disabled = true;
            startLoadingAnimation(this);

            try {
                const response = await fetch('/api/system/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                const data = await response.json();

                // Останавливаем анимацию и возвращаем текст
                stopLoadingAnimation(this, originalText);

                if (response.ok) {
                    updateSystemStatus(true);
                    alert('Система запущена!\n\nНастройки применены автоматически.');
                } else {
                    this.disabled = false;
                    alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                }
            } catch (error) {
                stopLoadingAnimation(this, originalText);
                this.disabled = false;
                alert('Ошибка соединения: ' + error.message);
            }
        });
    }

    if (stopBtn) {
        stopBtn.addEventListener('click', async function () {
            // Запускаем анимацию загрузки
            const originalText = this.textContent;
            this.disabled = true;
            startLoadingAnimation(this);

            try {
                const response = await fetch('/api/system/stop', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                const data = await response.json();

                // Останавливаем анимацию и возвращаем текст
                stopLoadingAnimation(this, originalText);

                if (response.ok) {
                    updateSystemStatus(false);
                    alert('Система остановлена');
                } else {
                    this.disabled = false;
                    alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                }
            } catch (error) {
                stopLoadingAnimation(this, originalText);
                this.disabled = false;
                alert('Ошибка соединения: ' + error.message);
            }
        });
    }

    // ========== НАСТРОЙКИ КАМЕР ==========
    document.querySelectorAll('.setting-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', async function () {
            const cameraId = parseInt(this.getAttribute('data-camera'));
            const settingType = this.getAttribute('data-setting');
            const value = this.checked;

            try {
                await fetch('/api/settings/cameras', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        camera_id: cameraId,
                        setting_type: settingType,
                        value: value
                    })
                });
                console.log(`Setting ${settingType} for camera ${cameraId} = ${value}`);
            } catch (error) {
                console.error('Error updating setting:', error);
            }
        });
    });

    document.querySelectorAll('.timeout-input').forEach(input => {
        input.addEventListener('change', async function () {
            const cameraId = parseInt(this.getAttribute('data-camera'));
            const timeout = parseInt(this.value);

            try {
                await fetch('/api/settings/cameras', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        camera_id: cameraId,
                        setting_type: 'timeout',
                        timeout: timeout
                    })
                });
            } catch (error) {
                console.error('Error updating timeout:', error);
            }
        });
    });

    document.querySelectorAll('.apply-btn').forEach(btn => {
        btn.addEventListener('click', async function () {
            const cameraId = parseInt(this.getAttribute('data-camera'));

            try {
                const response = await fetch('/api/settings/apply', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ camera_id: cameraId })
                });

                const data = await response.json();

                if (response.ok) {
                    alert(`Настройки для камеры ${cameraId} применены`);
                } else {
                    alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                }
            } catch (error) {
                alert('Ошибка соединения: ' + error.message);
            }
        });
    });

    // ========== ЧУВСТВИТЕЛЬНОСТЬ ДВИЖЕНИЯ (для каждой камеры) ==========
    document.querySelectorAll('.sensitivity-slider').forEach(slider => {
        const cameraId = slider.getAttribute('data-camera');
        const displaySpan = document.querySelector(`.sensitivity-display[data-camera="${cameraId}"]`);

        // Обновление отображения при перемещении ползунка
        slider.addEventListener('input', function () {
            if (displaySpan) {
                displaySpan.textContent = this.value;
            }
        });

        // Отправка значения на сервер при отпускании ползунка
        slider.addEventListener('change', async function () {
            const value = parseInt(this.value);

            try {
                const response = await fetch('/api/settings/sensitivity', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ camera_id: cameraId, sensitivity: value })
                });

                const data = await response.json();

                if (response.ok) {
                    console.log(`Camera ${cameraId} sensitivity updated:`, data.sensitivity);
                } else {
                    console.error('Error updating sensitivity:', data.error);
                }
            } catch (error) {
                console.error('Error:', error);
            }
        });
    });

    // ========== МАСКИ ==========
    // Создание масок доступно только в терминальной версии
    // Здесь только просмотр существующих масок

    // ========== ЛОГИ ==========
    const refreshLogsBtn = document.getElementById('refreshLogs');
    const statusFilter = document.getElementById('statusFilter');
    const dateFilter = document.getElementById('dateFilter');

    if (refreshLogsBtn) refreshLogsBtn.addEventListener('click', loadLogs);
    if (statusFilter) statusFilter.addEventListener('change', loadLogs);
    if (dateFilter) dateFilter.addEventListener('change', loadLogs);

    // ========== БИОМЕТРИЯ ==========
    const trainModelBtn = document.getElementById('trainModelBtn');
    if (trainModelBtn) {
        trainModelBtn.addEventListener('click', async function () {
            const statusDiv = document.getElementById('trainStatus');
            statusDiv.className = '';
            statusDiv.textContent = 'Обучение модели...';
            statusDiv.style.display = 'block';

            try {
                const response = await fetch('/api/biometric/train', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                const data = await response.json();

                if (response.ok) {
                    statusDiv.className = 'success';
                    statusDiv.textContent = 'Модель успешно обучена!';
                } else {
                    statusDiv.className = 'error';
                    statusDiv.textContent = 'Ошибка: ' + (data.error || 'Неизвестная ошибка');
                }
            } catch (error) {
                statusDiv.className = 'error';
                statusDiv.textContent = 'Ошибка соединения: ' + error.message;
            }
        });
    }

    const uploadPhotosBtn = document.getElementById('uploadPhotosBtn');
    if (uploadPhotosBtn) {
        uploadPhotosBtn.addEventListener('click', async function () {
            const fileInput = document.getElementById('photoUpload');
            const userNameInput = document.getElementById('userName');
            const statusDiv = document.getElementById('uploadStatus');

            if (!userNameInput.value.trim()) {
                statusDiv.className = 'error';
                statusDiv.textContent = 'Введите имя пользователя';
                statusDiv.style.display = 'block';
                return;
            }

            if (!fileInput.files || fileInput.files.length === 0) {
                statusDiv.className = 'error';
                statusDiv.textContent = 'Выберите фотографии';
                statusDiv.style.display = 'block';
                return;
            }

            statusDiv.className = '';
            statusDiv.textContent = 'Загрузка фотографий...';
            statusDiv.style.display = 'block';

            const formData = new FormData();
            formData.append('user_name', userNameInput.value.trim());
            for (let i = 0; i < fileInput.files.length; i++) {
                formData.append('files', fileInput.files[i]);
            }

            try {
                const response = await fetch('/api/biometric/upload', {
                    method: 'POST',
                    body: formData
                });

                const data = await response.json();

                if (response.ok) {
                    statusDiv.className = 'success';
                    statusDiv.textContent = data.message || 'Фотографии загружены!';
                    fileInput.value = '';
                    userNameInput.value = '';
                } else {
                    statusDiv.className = 'error';
                    statusDiv.textContent = 'Ошибка: ' + (data.error || 'Неизвестная ошибка');
                }
            } catch (error) {
                statusDiv.className = 'error';
                statusDiv.textContent = 'Ошибка соединения: ' + error.message;
            }
        });
    }

    // ========== ВЫБОР КАМЕРЫ ==========
    const cameraSelect = document.getElementById('cameraSelect');
    if (cameraSelect) {
        cameraSelect.addEventListener('change', function () {
            const selectedCamera = this.value;
            const cameraGrid = document.getElementById('cameraGrid');

            if (selectedCamera === 'all') {
                cameraGrid.querySelectorAll('.camera-item').forEach(item => {
                    item.style.display = 'block';
                });
            } else {
                cameraGrid.querySelectorAll('.camera-item').forEach((item, index) => {
                    item.style.display = (index === parseInt(selectedCamera)) ? 'block' : 'none';
                });
            }
        });
    }

    // ========== ИНИЦИАЛИЗАЦИЯ ==========
    checkSystemStatus();
    loadSettings();
    loadMasks();

    // Периодическое обновление
    setInterval(checkSystemStatus, 5000);
    setInterval(loadMasks, 10000);

    console.log('CCTV Dashboard initialized successfully!');
});

// ========== ФУНКЦИИ ==========

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(page => {
        page.classList.remove('active');
    });

    const targetPage = document.getElementById(`${pageId}-page`);
    if (targetPage) {
        targetPage.classList.add('active');
    }

    if (pageId === 'logs') {
        loadLogs();
    }
}

function updateSystemStatus(running) {
    const startBtn = document.getElementById('startSystem');
    const stopBtn = document.getElementById('stopSystem');
    const statusText = document.getElementById('systemStatus');

    if (startBtn && stopBtn && statusText) {
        if (running) {
            startBtn.disabled = true;
            stopBtn.disabled = false;
            statusText.textContent = 'Запущена';
            statusText.style.color = '#4caf50';
        } else {
            startBtn.disabled = false;
            stopBtn.disabled = true;
            statusText.textContent = 'Остановлена';
            statusText.style.color = '#f44336';
        }
    }
}

async function checkSystemStatus() {
    try {
        const response = await fetch('/api/system/status');
        const data = await response.json();
        updateSystemStatus(data.running);
    } catch (error) {
        console.error('Error checking system status:', error);
    }
}

async function loadSettings() {
    try {
        const response = await fetch('/api/settings/cameras');
        const data = await response.json();

        Object.keys(data.settings).forEach(cameraId => {
            const settings = data.settings[cameraId];
            Object.keys(settings).forEach(settingType => {
                const checkbox = document.querySelector(
                    `.setting-checkbox[data-camera="${cameraId}"][data-setting="${settingType}"]`
                );
                if (checkbox && !checkbox.disabled) {
                    checkbox.checked = settings[settingType];
                }
            });

            const timeoutInput = document.querySelector(`.timeout-input[data-camera="${cameraId}"]`);
            if (timeoutInput) {
                timeoutInput.value = data.timeouts[cameraId] || 10;
            }
        });

        // Загружаем чувствительность детекции движения для каждой камеры
        if (data.motion_sensitivity) {
            Object.keys(data.motion_sensitivity).forEach(cameraId => {
                const slider = document.querySelector(`.sensitivity-slider[data-camera="${cameraId}"]`);
                const display = document.querySelector(`.sensitivity-display[data-camera="${cameraId}"]`);
                const value = data.motion_sensitivity[cameraId];

                if (slider) {
                    slider.value = value;
                }
                if (display) {
                    display.textContent = value;
                }
            });
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

async function loadMasks() {
    try {
        const response = await fetch('/api/masks/list');
        const data = await response.json();

        const masksList = document.getElementById('masksList');
        if (!masksList) return;

        masksList.innerHTML = '';

        Object.keys(data.masks).forEach(cameraId => {
            const masks = data.masks[cameraId];
            masks.forEach(mask => {
                const maskItem = document.createElement('div');
                maskItem.className = 'mask-item';
                maskItem.innerHTML = `
                    <span>Камера ${cameraId}: ${mask.filename}</span>
                    <button onclick="deleteMask('${mask.filename}')">Удалить</button>
                `;
                masksList.appendChild(maskItem);
            });
        });
    } catch (error) {
        console.error('Error loading masks:', error);
    }
}

async function deleteMask(filename) {
    if (!confirm('Удалить эту маску?')) return;

    try {
        const response = await fetch('/api/masks/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename })
        });

        const data = await response.json();

        if (response.ok) {
            loadMasks();
        } else {
            alert('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        alert('Ошибка соединения: ' + error.message);
    }
}

async function loadLogs() {
    const statusFilter = document.getElementById('statusFilter');
    const dateFilter = document.getElementById('dateFilter');
    const logsContent = document.getElementById('logsContent');

    if (!logsContent) return;

    try {
        let url = '/api/logs?';
        if (statusFilter && statusFilter.value) url += `status=${statusFilter.value}&`;
        if (dateFilter && dateFilter.value) url += `date=${dateFilter.value}&`;

        const response = await fetch(url);
        const data = await response.json();

        logsContent.textContent = data.logs.join('\n');
        logsContent.scrollTop = logsContent.scrollHeight;
    } catch (error) {
        console.error('Error loading logs:', error);
    }
}

// ========== COLLAPSIBLE SECTIONS ==========
function toggleCollapsible(header) {
    const section = header.parentElement;
    section.classList.toggle('collapsed');
}

// ========== LOADING ANIMATION ==========
let loadingIntervals = new Map();

function startLoadingAnimation(button) {
    let dotCount = 0;
    const dots = ['', '.', '..', '...'];

    button.textContent = '...';

    const intervalId = setInterval(() => {
        dotCount = (dotCount + 1) % dots.length;
        button.textContent = dots[dotCount] || '...';
    }, 400);

    loadingIntervals.set(button, intervalId);
}

function stopLoadingAnimation(button, originalText) {
    const intervalId = loadingIntervals.get(button);
    if (intervalId) {
        clearInterval(intervalId);
        loadingIntervals.delete(button);
    }
    if (originalText) {
        button.textContent = originalText;
    }
}

// ========== АРХИВ ==========

// Загрузка настроек подключения при переходе на страницу архива
async function loadArchiveSettings() {
    try {
        const response = await fetch('/api/archive/settings');
        const data = await response.json();

        const userInput = document.getElementById('archiveRemoteUser');
        const passwordInput = document.getElementById('archiveRemotePassword');
        const hostInput = document.getElementById('archiveRemoteHost');
        const pathInput = document.getElementById('archiveRemotePath');

        if (userInput && data.remote_user) userInput.value = data.remote_user;
        if (passwordInput && data.remote_password) passwordInput.placeholder = data.remote_password || 'Пароль для SSH';
        if (hostInput && data.remote_host) hostInput.value = data.remote_host;
        if (pathInput && data.remote_path) pathInput.value = data.remote_path;
    } catch (error) {
        console.error('Error loading archive settings:', error);
    }
}

// Сохранение настроек подключения
document.addEventListener('DOMContentLoaded', function () {
    const saveConnectionBtn = document.getElementById('saveConnectionBtn');
    if (saveConnectionBtn) {
        saveConnectionBtn.addEventListener('click', async function () {
            const statusDiv = document.getElementById('connectionStatus');
            const userInput = document.getElementById('archiveRemoteUser');
            const passwordInput = document.getElementById('archiveRemotePassword');
            const hostInput = document.getElementById('archiveRemoteHost');
            const pathInput = document.getElementById('archiveRemotePath');

            if (!hostInput.value.trim()) {
                statusDiv.className = 'error';
                statusDiv.textContent = 'Укажите адрес сервера';
                statusDiv.style.display = 'block';
                return;
            }

            const settingsData = {
                remote_user: userInput.value.trim(),
                remote_host: hostInput.value.trim(),
                remote_path: pathInput.value.trim()
            };

            // Отправляем пароль только если он был введён
            if (passwordInput.value) {
                settingsData.remote_password = passwordInput.value;
            }

            try {
                const response = await fetch('/api/archive/settings', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(settingsData)
                });

                const data = await response.json();

                if (response.ok) {
                    statusDiv.className = 'success';
                    statusDiv.textContent = 'Настройки сохранены!';
                    // Очищаем поле пароля после сохранения
                    passwordInput.value = '';
                    passwordInput.placeholder = '••••••••';
                } else {
                    statusDiv.className = 'error';
                    statusDiv.textContent = 'Ошибка: ' + (data.error || 'Неизвестная ошибка');
                }
                statusDiv.style.display = 'block';

                setTimeout(() => { statusDiv.style.display = 'none'; }, 3000);
            } catch (error) {
                statusDiv.className = 'error';
                statusDiv.textContent = 'Ошибка соединения: ' + error.message;
                statusDiv.style.display = 'block';
            }
        });
    }

    // Поиск в архиве
    const searchArchiveBtn = document.getElementById('searchArchiveBtn');
    if (searchArchiveBtn) {
        searchArchiveBtn.addEventListener('click', searchArchive);
    }

    // Выбрать все файлы
    const selectAllBtn = document.getElementById('selectAllBtn');
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', function () {
            const checkboxes = document.querySelectorAll('.archive-file-checkbox');
            const allChecked = Array.from(checkboxes).every(cb => cb.checked);
            checkboxes.forEach(cb => cb.checked = !allChecked);
            this.textContent = allChecked ? 'Выбрать все' : 'Снять выбор';
        });
    }

    // Скачать выбранные
    const downloadSelectedBtn = document.getElementById('downloadSelectedBtn');
    if (downloadSelectedBtn) {
        downloadSelectedBtn.addEventListener('click', downloadSelectedFiles);
    }

    // Установка текущей даты по умолчанию
    const archiveDate = document.getElementById('archiveDate');
    if (archiveDate) {
        const today = new Date().toISOString().split('T')[0];
        archiveDate.value = today;
    }
});

// Поиск файлов в архиве
async function searchArchive() {
    const dateInput = document.getElementById('archiveDate');
    const timeFromInput = document.getElementById('archiveTimeFrom');
    const timeToInput = document.getElementById('archiveTimeTo');
    const resultsDiv = document.getElementById('archiveResults');
    const statusDiv = document.getElementById('archiveSearchStatus');
    const actionsDiv = document.getElementById('archiveActions');
    const searchBtn = document.getElementById('searchArchiveBtn');

    if (!dateInput.value) {
        statusDiv.className = 'error';
        statusDiv.textContent = 'Выберите дату';
        statusDiv.style.display = 'block';
        return;
    }

    // Показываем загрузку
    const originalText = searchBtn.textContent;
    searchBtn.disabled = true;
    startLoadingAnimation(searchBtn);
    statusDiv.textContent = 'Поиск...';
    statusDiv.className = '';
    statusDiv.style.display = 'block';
    resultsDiv.innerHTML = '<p class="loading">Поиск файлов на сервере...</p>';
    actionsDiv.style.display = 'none';

    try {
        const response = await fetch('/api/archive/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                date: dateInput.value,
                time_from: timeFromInput.value,
                time_to: timeToInput.value
            })
        });

        const data = await response.json();

        stopLoadingAnimation(searchBtn, originalText);
        searchBtn.disabled = false;

        if (response.ok) {
            if (data.files && data.files.length > 0) {
                statusDiv.className = 'success';
                statusDiv.textContent = `Найдено файлов: ${data.count}`;

                resultsDiv.innerHTML = data.files.map((file, index) => `
                    <div class="archive-file-item">
                        <input type="checkbox" class="archive-file-checkbox" 
                               data-path="${file.path}" 
                               data-filename="${file.filename}" 
                               id="file-${index}">
                        <label for="file-${index}">
                            <span class="file-icon">🎬</span>
                            <span class="file-name">${file.filename}</span>
                            <span class="file-time">${file.time}</span>
                        </label>
                    </div>
                `).join('');

                actionsDiv.style.display = 'flex';
            } else {
                statusDiv.className = 'warning';
                statusDiv.textContent = 'Файлы не найдены';
                resultsDiv.innerHTML = '<p class="no-results">На указанную дату записей не найдено</p>';
            }
        } else {
            statusDiv.className = 'error';
            statusDiv.textContent = 'Ошибка: ' + (data.error || 'Неизвестная ошибка');
            resultsDiv.innerHTML = '<p class="error-text">Ошибка при поиске</p>';
        }
    } catch (error) {
        stopLoadingAnimation(searchBtn, originalText);
        searchBtn.disabled = false;
        statusDiv.className = 'error';
        statusDiv.textContent = 'Ошибка соединения: ' + error.message;
        resultsDiv.innerHTML = '<p class="error-text">Не удалось подключиться к серверу</p>';
    }
}

// Скачивание выбранных файлов
async function downloadSelectedFiles() {
    const checkboxes = document.querySelectorAll('.archive-file-checkbox:checked');
    const progressDiv = document.getElementById('downloadProgress');
    const progressFill = document.getElementById('progressFill');
    const statusText = document.getElementById('downloadStatusText');
    const downloadBtn = document.getElementById('downloadSelectedBtn');

    if (checkboxes.length === 0) {
        alert('Выберите файлы для скачивания');
        return;
    }

    const files = Array.from(checkboxes).map(cb => ({
        path: cb.dataset.path,
        filename: cb.dataset.filename
    }));

    // Показываем прогресс
    progressDiv.style.display = 'block';
    progressFill.style.width = '0%';
    statusText.textContent = `Подготовка ${files.length} файлов...`;

    const originalText = downloadBtn.textContent;
    downloadBtn.disabled = true;
    startLoadingAnimation(downloadBtn);

    try {
        const response = await fetch('/api/archive/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ files: files })
        });

        const data = await response.json();

        stopLoadingAnimation(downloadBtn, originalText);
        downloadBtn.disabled = false;

        if (response.ok && data.download_url) {
            progressFill.style.width = '100%';
            statusText.textContent = `Готово! Скачивание ${data.count} файлов...`;

            if (data.errors && data.errors.length > 0) {
                statusText.textContent += ` (${data.errors.length} ошибок)`;
            }

            // Запускаем скачивание через браузер
            const link = document.createElement('a');
            link.href = data.download_url;
            link.download = data.filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            setTimeout(() => {
                progressDiv.style.display = 'none';
            }, 3000);
        } else {
            progressFill.style.width = '0%';
            statusText.textContent = 'Ошибка: ' + (data.error || 'Неизвестная ошибка');
            alert('Ошибка скачивания: ' + (data.error || 'Неизвестная ошибка'));
        }
    } catch (error) {
        stopLoadingAnimation(downloadBtn, originalText);
        downloadBtn.disabled = false;
        progressFill.style.width = '0%';
        statusText.textContent = 'Ошибка соединения';
        alert('Ошибка соединения: ' + error.message);
    }
}

// Обновляем функцию showPage для загрузки настроек архива
const originalShowPage = showPage;
showPage = function (pageId) {
    originalShowPage(pageId);
    if (pageId === 'archive') {
        loadArchiveSettings();
    }
};
