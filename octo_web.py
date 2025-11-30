#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import cv2
import time
import os
import queue
import threading
import datetime
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_from_directory, Response
from flask_socketio import SocketIO, emit
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
import numpy as np
from motion_detection import detect_motion, draw_motion_visualization
from camera_utils import (
    initialize_cameras, release_cameras, create_video_grid,
    get_no_signal_frame, get_waiting_frame,
    MultiMaskCreator, load_mask, overlay_mask, load_lbph_face_recognizer
)
from camera_utils import detect_and_recognize_faces, detect_faces_only
from logger import motion_logger
from loguru import logger
from AI_face import learning
from config import CAMERA_INDICES, SYSTEM

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Отключаем кэширование статики
socketio = SocketIO(app, cors_allowed_origins="*")


@app.after_request
def add_header(response):
    """Отключаем кэширование для предотвращения проблем после logout/login"""
    if 'Cache-Control' not in response.headers:
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response

# Простая база данных пользователей (в продакшене использовать реальную БД)
USERS = {
    'admin': {'password': generate_password_hash('admin123'), 'role': 'Admin'},
    'user': {'password': generate_password_hash('user123'), 'role': 'User'}
}

# Глобальное состояние системы (используем индексы камер из config)
system_state = {
    'running': False,
    'system': None,
    'camera_settings': {i: {'faces': False, 'motion': False, 'recording': True, 'triggered': False} for i in CAMERA_INDICES},
    'timeouts': {i: 10 for i in CAMERA_INDICES},
    'motion_sensitivity': {i: 25 for i in CAMERA_INDICES}  # Чувствительность для каждой камеры (5-100)
}

# Буферы для видеопотоков
video_buffers = {i: queue.Queue(maxsize=2) for i in CAMERA_INDICES}

# Презапись для recording режима
pre_record_buffers = {i: queue.Queue(maxsize=80) for i in CAMERA_INDICES}  # 4 секунды при 20 FPS


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session or session.get('role') != 'Admin':
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


@app.route('/')
def index():
    if 'user' not in session:
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and check_password_hash(USERS[username]['password'], password):
            session['user'] = username
            session['role'] = USERS[username]['role']
            return jsonify({'success': True, 'role': USERS[username]['role']})
        else:
            return jsonify({'success': False, 'error': 'Неверный пароль или имя пользователя'}), 401
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', role=session.get('role'), camera_indices=CAMERA_INDICES)


@app.route('/api/system/start', methods=['POST'])
@admin_required
def start_system():
    """Запуск системы CCTV"""
    if system_state['running']:
        return jsonify({'error': 'System already running'}), 400
    
    try:
        from octo_cli import SurveillanceSystem
        system = SurveillanceSystem()
        
        # Применяем настройки из system_state ПЕРЕД инициализацией
        # Эти настройки были установлены через веб-интерфейс в разделе Settings
        system.camera_faces = [i for i in CAMERA_INDICES if system_state['camera_settings'][i]['faces']]
        system.camera_motion = [i for i in CAMERA_INDICES if system_state['camera_settings'][i]['motion']]
        # Recording всегда включен для всех камер (режим recording обязателен)
        system.camera_recording = CAMERA_INDICES.copy()
        system.camera_triggered = [i for i in CAMERA_INDICES if system_state['camera_settings'][i]['triggered']]
        system.MOTION_TIMEOUTS = system_state['timeouts'].copy()
        system.MOTION_THRESHOLDS = system_state['motion_sensitivity'].copy()
        
        # Логируем применяемые настройки
        logger.info(f"Applying settings: faces={system.camera_faces}, motion={system.camera_motion}, "
                   f"triggered={system.camera_triggered}, recording={system.camera_recording}, "
                   f"sensitivities={system.MOTION_THRESHOLDS}")
        
        # Инициализируем систему БЕЗ запроса настроек через терминал
        # skip_settings=True пропускает get_user_settings(), который запрашивает ввод
        system.initialize(skip_settings=True)
        system_state['system'] = system
        system_state['running'] = True
        
        # Запускаем поток обработки камер
        threading.Thread(target=process_cameras_loop, daemon=True).start()
        
        motion_logger.log_system_event("Web system started with settings from web interface")
        return jsonify({'success': True, 'message': 'System started with web interface settings'})
    except Exception as e:
        logger.error(f"Error starting system: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/stop', methods=['POST'])
@admin_required
def stop_system():
    """Остановка системы CCTV"""
    if not system_state['running']:
        return jsonify({'error': 'System not running'}), 400
    
    try:
        if system_state['system']:
            system_state['system'].cleanup()
            system_state['system'] = None
        system_state['running'] = False
        motion_logger.log_system_event("Web system stopped")
        return jsonify({'success': True, 'message': 'System stopped'})
    except Exception as e:
        logger.error(f"Error stopping system: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/status', methods=['GET'])
@login_required
def system_status():
    """Получение статуса системы"""
    return jsonify({
        'running': system_state['running'],
        'settings': system_state['camera_settings']
    })


@app.route('/api/settings/cameras', methods=['GET', 'POST'])
@admin_required
def camera_settings():
    """Получение/установка настроек камер"""
    if request.method == 'GET':
        return jsonify({
            'settings': system_state['camera_settings'],
            'timeouts': system_state['timeouts'],
            'motion_sensitivity': system_state['motion_sensitivity']
        })
    
    data = request.json
    camera_id = data.get('camera_id')
    setting_type = data.get('setting_type')  # 'faces', 'motion', 'recording', 'triggered'
    value = data.get('value')
    timeout = data.get('timeout')
    
    if camera_id is not None and setting_type:
        if setting_type in ['faces', 'motion', 'recording', 'triggered']:
            system_state['camera_settings'][camera_id][setting_type] = value
        elif setting_type == 'timeout' and timeout is not None:
            system_state['timeouts'][camera_id] = timeout
    
    return jsonify({'success': True, 'settings': system_state['camera_settings']})


@app.route('/api/settings/sensitivity', methods=['POST'])
@admin_required
def set_sensitivity():
    """Установка чувствительности детекции движения для конкретной камеры"""
    data = request.json
    camera_id = data.get('camera_id')
    sensitivity = data.get('sensitivity')
    
    if camera_id is not None and sensitivity is not None:
        camera_id = int(camera_id)
        # Ограничиваем значение от 5 до 100
        sensitivity = max(5, min(100, int(sensitivity)))
        system_state['motion_sensitivity'][camera_id] = sensitivity
        
        # Если система запущена, применяем настройку сразу
        if system_state['running'] and system_state['system']:
            system_state['system'].MOTION_THRESHOLDS[camera_id] = sensitivity
        
        motion_logger.log_settings({f'camera_{camera_id}_sensitivity': sensitivity})
        return jsonify({'success': True, 'camera_id': camera_id, 'sensitivity': sensitivity})
    
    return jsonify({'success': False, 'error': 'No camera_id or sensitivity value provided'})


@app.route('/api/settings/apply', methods=['POST'])
@admin_required
def apply_settings():
    """Применение настроек для камеры"""
    data = request.json
    camera_id = data.get('camera_id')
    
    if camera_id is None:
        return jsonify({'error': 'Camera ID required'}), 400
    
    # Логируем применение настроек
    settings = system_state['camera_settings'][camera_id]
    motion_logger.log_settings({
        f'camera_{camera_id}': settings
    })
    
    return jsonify({'success': True, 'message': f'Settings applied for camera {camera_id}'})


@app.route('/api/masks/list', methods=['GET'])
@admin_required
def list_masks():
    """Список масок для камер"""
    masks_dir = "masks"
    masks = {}
    
    if os.path.exists(masks_dir):
        for filename in os.listdir(masks_dir):
            if filename.startswith("camera_") and filename.endswith(".png"):
                try:
                    parts = filename.split('_')
                    camera_idx = int(parts[1])
                    if camera_idx not in masks:
                        masks[camera_idx] = []
                    masks[camera_idx].append({
                        'filename': filename,
                        'path': os.path.join(masks_dir, filename)
                    })
                except (ValueError, IndexError):
                    continue
    
    return jsonify({'masks': masks})


@app.route('/api/masks/delete', methods=['POST'])
@admin_required
def delete_mask():
    """Удаление маски"""
    data = request.json
    filename = data.get('filename')
    
    if not filename:
        return jsonify({'error': 'Filename required'}), 400
    
    mask_path = os.path.join("masks", filename)
    if os.path.exists(mask_path):
        os.remove(mask_path)
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'Mask not found'}), 404


@app.route('/api/masks/create', methods=['POST'])
@admin_required
def create_mask():
    """Создание маски (запускает процесс создания)"""
    data = request.json
    camera_id = data.get('camera_id')
    mask_name = data.get('mask_name', 'default')
    
    if camera_id is None:
        return jsonify({'error': 'Camera ID required'}), 400
    
    # Запускаем создание маски в отдельном потоке
    threading.Thread(
        target=create_mask_thread,
        args=(camera_id, mask_name),
        daemon=True
    ).start()
    
    return jsonify({'success': True, 'message': 'Mask creation started'})


def create_mask_thread(camera_id, mask_name):
    """Поток для создания маски"""
    try:
        # Создание маски требует интерактивного окна OpenCV
        # Для веб-версии это сложнее, поэтому возвращаем инструкции
        # В реальности нужно использовать WebRTC или другой подход
        logger.info(f"Mask creation requested for camera {camera_id}, name: {mask_name}")
        logger.warning("Mask creation via web interface requires OpenCV window - use terminal version for now")
        socketio.emit('mask_info', {
            'camera_id': camera_id,
            'message': 'Создание маски через веб-интерфейс требует дополнительной реализации. Используйте терминальную версию.'
        })
    except Exception as e:
        logger.error(f"Error creating mask: {e}")
        socketio.emit('mask_error', {'error': str(e)})


@app.route('/api/logs', methods=['GET'])
@login_required
def get_logs():
    """Получение логов с фильтрацией"""
    status_filter = request.args.get('status')
    date_filter = request.args.get('date')
    
    logs_dir = "logs"
    logs = []
    
    if os.path.exists(logs_dir):
        log_files = sorted([f for f in os.listdir(logs_dir) if f.endswith('.log')], reverse=True)
        
        for log_file in log_files[:1]:  # Берем последний лог-файл
            log_path = os.path.join(logs_dir, log_file)
            try:
                with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if status_filter and status_filter.lower() not in line.lower():
                            continue
                        if date_filter and date_filter not in line:
                            continue
                        logs.append(line.strip())
            except Exception as e:
                logger.error(f"Error reading log file: {e}")
    
    return jsonify({'logs': logs[-100:]})  # Последние 100 строк


@app.route('/api/biometric/train', methods=['POST'])
@admin_required
def train_model():
    """Обучение модели распознавания лиц"""
    try:
        learning()
        return jsonify({'success': True, 'message': 'Model trained successfully'})
    except Exception as e:
        logger.error(f"Error training model: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/biometric/upload', methods=['POST'])
@admin_required
def upload_photos():
    """Загрузка фотографий пользователей"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files selected'}), 400
    
    files = request.files.getlist('files')
    user_name = request.form.get('user_name', 'unknown')
    
    if not files:
        return jsonify({'error': 'No files provided'}), 400
    
    # Создаем папку для пользователя
    user_dir = os.path.join('dataset', user_name)
    os.makedirs(user_dir, exist_ok=True)
    
    saved_count = 0
    for file in files:
        if file.filename:
            # Проверяем расширение файла
            if file.filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                filename = file.filename
                filepath = os.path.join(user_dir, filename)
                file.save(filepath)
                saved_count += 1
    
    return jsonify({
        'success': True,
        'message': f'Uploaded {saved_count} photos for {user_name}'
    })


@app.route('/video_feed/<int:camera_id>')
@login_required
def video_feed(camera_id):
    """Видеопоток для камеры"""
    return Response(
        generate_video_stream(camera_id),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


def generate_video_stream(camera_id):
    """Генератор видеопотока"""
    while True:
        try:
            if camera_id in video_buffers:
                try:
                    frame = video_buffers[camera_id].get(timeout=1)
                    ret, buffer = cv2.imencode('.jpg', frame)
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                except queue.Empty:
                    # Отправляем черный кадр если нет данных
                    black_frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    ret, buffer = cv2.imencode('.jpg', black_frame)
                    if ret:
                        frame_bytes = buffer.tobytes()
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            logger.error(f"Error in video stream: {e}")
            time.sleep(0.1)


def process_cameras_loop():
    """Основной цикл обработки камер"""
    system = system_state['system']
    if not system:
        return
    
    # Буферы для презаписи (4 секунды при 20 FPS = 80 кадров)
    pre_record_frames = {i: queue.Queue(maxsize=80) for i in CAMERA_INDICES}
    last_motion_state = {i: False for i in CAMERA_INDICES}
    motion_stop_time = {i: 0 for i in CAMERA_INDICES}
    POST_MOTION_DURATION = 5  # 5 секунд после прекращения движения
    
    while system_state['running']:
        try:
            frames = []
            current_time = time.time()
            
            for idx, cap in enumerate(system.caps):
                camera_idx = system.camera_indices[idx]
                
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        # Всегда добавляем кадр в буфер презаписи для recording режима
                        if camera_idx in system.camera_recording:
                            frame_copy = frame.copy()
                            try:
                                pre_record_frames[camera_idx].put_nowait(frame_copy)
                            except queue.Full:
                                try:
                                    pre_record_frames[camera_idx].get_nowait()
                                    pre_record_frames[camera_idx].put_nowait(frame_copy)
                                except queue.Empty:
                                    pass
                        
                        processed_frame = system.process_camera_frame(camera_idx, frame, current_time)
                        
                        # Проверяем состояние движения для recording
                        if camera_idx in system.camera_recording:
                            motion_detected_now = system.motion_detected.get(camera_idx, False)
                            
                            # Если движение обнаружено и запись еще не началась
                            if motion_detected_now and camera_idx not in system.video_writers:
                                # Запускаем запись с презаписью
                                prerecord_list = []
                                while not pre_record_frames[camera_idx].empty():
                                    prerecord_list.append(pre_record_frames[camera_idx].get())
                                if prerecord_list:
                                    start_recording_with_prerecord(system, camera_idx, prerecord_list)
                            
                            # Если запись активна, обновляем время последнего движения
                            if camera_idx in system.video_writers:
                                if motion_detected_now:
                                    motion_stop_time[camera_idx] = current_time + POST_MOTION_DURATION
                                    last_motion_state[camera_idx] = True
                                else:
                                    # Движение прекратилось, но продолжаем запись еще 5 секунд
                                    if last_motion_state[camera_idx]:
                                        motion_stop_time[camera_idx] = current_time + POST_MOTION_DURATION
                                        last_motion_state[camera_idx] = False
                                    
                                    # Если прошло 5 секунд после последнего движения, останавливаем запись
                                    if current_time >= motion_stop_time[camera_idx]:
                                        system.stop_recording(camera_idx)
                                        motion_stop_time[camera_idx] = 0
                            
                            # Добавляем текущий кадр в очередь записи, если запись активна
                            if camera_idx in system.video_writers:
                                try:
                                    system.frame_queues[camera_idx].put_nowait(frame.copy())
                                except queue.Full:
                                    pass
                        
                        # Добавляем кадр в очередь для веб-потока
                        try:
                            video_buffers[camera_idx].put_nowait(processed_frame)
                        except queue.Full:
                            try:
                                video_buffers[camera_idx].get_nowait()
                                video_buffers[camera_idx].put_nowait(processed_frame)
                            except queue.Empty:
                                pass
                    else:
                        processed_frame = get_no_signal_frame(camera_idx)
                        try:
                            video_buffers[camera_idx].put_nowait(processed_frame)
                        except queue.Full:
                            pass
                else:
                    processed_frame = get_no_signal_frame(camera_idx)
                    try:
                        video_buffers[camera_idx].put_nowait(processed_frame)
                    except queue.Full:
                        pass
                
                frames.append(cv2.resize(processed_frame, (320, 240)))
            
            time.sleep(0.05)  # ~20 FPS
            
        except Exception as e:
            logger.error(f"Error in camera loop: {e}")
            time.sleep(1)


def start_recording_with_prerecord(system, camera_idx, pre_record_frames):
    """Запуск записи с презаписью 4 секунды"""
    if camera_idx not in system.camera_recording:
        return
    
    if camera_idx in system.video_writers:
        # Обновляем время начала, чтобы продлить запись
        system.recording_start_time[camera_idx] = time.time()
        return
    
    if not pre_record_frames:
        # Если нет презаписи, используем стандартный метод
        if hasattr(system, 'start_recording'):
            system.start_recording(camera_idx, pre_record_frames[0] if pre_record_frames else None)
        return
    
    now = datetime.datetime.now()
    date_dir = os.path.join(system.VIDEO_DIR, now.strftime("%Y-%m-%d"))
    event_dir = os.path.join(date_dir, "motion_detected")
    camera_dir = os.path.join(event_dir, f"cam{camera_idx}")
    
    os.makedirs(camera_dir, exist_ok=True)
    
    filename = f"recording_{now.strftime('%H-%M-%S')}.avi"
    filepath = os.path.join(camera_dir, filename)
    
    # Определяем размер кадра из первого кадра презаписи
    frame_height, frame_width = pre_record_frames[0].shape[:2]
    
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    writer = cv2.VideoWriter(filepath, fourcc, system.FPS, (frame_width, frame_height))
    
    # Записываем презаписанные кадры
    for pre_frame in pre_record_frames:
        writer.write(pre_frame)
    
    # Используем последний кадр для инициализации очереди
    frame_queue = queue.Queue()
    frame_queue.put(pre_record_frames[-1].copy())
    
    system.video_writers[camera_idx] = writer
    system.recording_start_time[camera_idx] = time.time()
    system.frame_queues[camera_idx] = frame_queue
    
    recording_thread = threading.Thread(target=system._write_video_thread, args=(camera_idx,))
    recording_thread.daemon = True
    recording_thread.start()
    system.recording_threads[camera_idx] = recording_thread
    
    motion_logger.log_system_event(f"Started recording with prerecord for camera {camera_idx} -> {filepath}")


def main():
    """Главная функция для запуска веб-сервера"""
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs('masks', exist_ok=True)
    os.makedirs('dataset', exist_ok=True)
    os.makedirs('recordings', exist_ok=True)
    
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting web server on http://localhost:{port}")
    logger.info(f"Login page: http://localhost:{port}/login")
    logger.info(f"Dashboard: http://localhost:{port}/dashboard")
    
    # Используем стандартный Flask сервер вместо socketio (более стабильно на Windows)
    try:
        app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
    except Exception as e:
        logger.error(f"Server error: {e}")
        raise


if __name__ == '__main__':
    main()

