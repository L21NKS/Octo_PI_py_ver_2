import cv2
import time
import os
import queue
import threading
import datetime
from motion_detection import detect_motion, draw_motion_visualization
from camera_utils import (
    initialize_cameras, release_cameras, create_video_grid,
    get_no_signal_frame, get_waiting_frame,
    MultiMaskCreator, load_mask, overlay_mask,load_lbph_face_recognizer
)
from view_logs import view_logs
from script_save import sv
from camera_utils import detect_and_recognize_faces, detect_faces_only
from logger import motion_logger
from loguru import logger
from config import CAMERA_INDICES, SYSTEM


print(r"""________  ____________________________        /\ __________.___                   
\_____  \ \_   ___ \__    ___/\_____  \      / / \______   \   |    ______ ___.__.
 /   |   \/    \  \/ |    |    /   |   \    / /   |     ___/   |    \____ <   |  |
/    |    \     \____|    |   /    |    \  / /    |    |   |   |    |  |_> >___  |
\_______  /\______  /|____|   \_______  / / /     |____|   |___| /\ |   __// ____|
        \/        \/                  \/  \/                     \/ |__|   \/     """)


class SurveillanceSystem:
    def __init__(self):
        self.camera_indices = CAMERA_INDICES.copy()  # Автоопределение по ОС
        self.caps = []
        self.recognizer = None
        self.label_dict = None
        self.face_cascade = None
        self.masks = {}  # {camera_idx: mask}

        # Состояние камер
        self.motion_detected = {idx: False for idx in self.camera_indices}
        self.prev_frames = {idx: None for idx in self.camera_indices}
        self.last_motion_time = {idx: 0 for idx in self.camera_indices}
        self.last_motion_check = {idx: 0 for idx in self.camera_indices}
        self.motion_start_time = {idx: 0 for idx in self.camera_indices}
        self.motion_contours = {idx: [] for idx in self.camera_indices}
        self.last_check_time = {idx: 0 for idx in self.camera_indices}

        self.camera_triggered = []
        self.camera_faces = []
        self.camera_motion = []
        # --- НОВОЕ ---
        self.camera_recording = [] # Камеры, на которых включена запись по событию
        # --- /НОВОЕ ---
        self.MOTION_TIMEOUT = 10
        self.MOTION_TIMEOUTS = {idx: 10 for idx in self.camera_indices}
        self.CHECK_INTERVAL = 1
        self.MOTION_THRESHOLD = 25  # Значение по умолчанию (для совместимости)
        self.MOTION_THRESHOLDS = {idx: 25 for idx in self.camera_indices}  # Чувствительность для каждой камеры
        self.MOTION_MIN_AREA = 500

        self.active_motion_cameras = set()

        self.mask_creator = MultiMaskCreator()

        # --- НОВОЕ (для записи видео) ---
        self.video_writers = {}
        self.recording_start_time = {}
        self.frame_queues = {}
        self.recording_threads = {}
        self.VIDEO_DURATION = 5  # секунд
        self.FPS = 20
        self.VIDEO_DIR = "recordings"
        os.makedirs(self.VIDEO_DIR, exist_ok=True)
        # --- /НОВОЕ ---

    def main_menu(self):
        logger.info("The main menu is opendos SurveillanceSystem")
        while True:
            print("\nMain Menu")
            print("1. Start Surveillance System")
            print("2. View Logs")
            print("3. Create Biometric Mask")
            print("4. Configure Masks")
            print("5. View Event Videos")  
            print("q. Exit")

            choice = input("  ")

            if choice == "1":
                self.run()  # запуск системы
            elif choice == "2":
                view_logs()  # просмотр логов
            elif choice == "3":
                sv()
            elif choice == "4":
                self.setup_masks()
            elif choice == "5":  # 👈 НОВЫЙ ПУНКТ
                self.view_event_videos()
            elif choice == "q":
                logger.info("Shutting down...")
                logger.info("Exiting SurveillanceSystem")
                break
            else:
                logger.warning("Invalid choice")

    def view_event_videos(self):
        """Просмотр видео событий из папки recordings"""
        if not os.path.exists(self.VIDEO_DIR):
            logger.warning("No recordings folder found")
            logger.warning("No recordings found")
            input("Press Enter to continue")
            return

        print("\nEvent Videos")
        video_files = []
        file_paths = []

        # Собираем все .avi файлы
        for root, dirs, files in os.walk(self.VIDEO_DIR):
            for file in files:
                if file.lower().endswith('.avi'):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, self.VIDEO_DIR)
                    video_files.append(relative_path)
                    file_paths.append(full_path)

        if not video_files:
            logger.warning("No video files found")
            input("Press Enter to continue")
            return

        while True:
            print(f"\nFound {len(video_files)} video(s):")
            for i, vid in enumerate(video_files, 1):
                print(f"{i}. {vid}")

            print("\nEnter number to play video, or 'q' to exit:")
            choice = input("  ").strip()

            if choice == 'q':
                break

            try:
                idx = int(choice) - 1
                if idx < 0 or idx >= len(file_paths):
                    logger.error("Invalid selection")
                    continue

                video_path = file_paths[idx]
                print(f"Playing: {video_path}")

                cap = cv2.VideoCapture(video_path)
                if not cap.isOpened():
                    logger.error("Cannot open video file")
                    continue

                cv2.namedWindow("Event Video Playback", cv2.WINDOW_NORMAL)
                while True:
                    ret, frame = cap.read()
                    if not ret:
                        print("End of video.")
                        break

                    cv2.imshow("Event Video Playback", frame)
                    key = cv2.waitKey(30) & 0xFF
                    if key == ord('q'):
                        break

                cap.release()
                cv2.destroyAllWindows()

            except ValueError:
                print("Please enter a number or 'q'.")
            except Exception as e:
                logger.error(f"Error playing video: {e}")

        print("Exited video viewer")
        
    def initialize(self, skip_settings=False):
        """Инициализация системы"""
        motion_logger.log_system_event("Initializing surveillance system")
        # Загрузка модели детектирования лиц
        try:
            self.recognizer, self.label_dict, self.face_cascade = load_lbph_face_recognizer(
                model_path="face_model.yml", 
                labels_path="labels.npy"
            )
            motion_logger.log_system_event("LBPH Face Recognizer loaded")
        except Exception as e:
            motion_logger.log_system_event(f"Error loading LBPH model: {e}")
            self.recognizer = None
            self.label_dict = None
            self.face_cascade = None


        # Инициализация камер
        self.caps = initialize_cameras(self.camera_indices)

        # Загрузка масок
        self.load_all_masks()

        # Получение настроек (пропускаем если skip_settings=True)
        if not skip_settings:
            self.get_user_settings()
        else:
            # Логируем настройки, которые уже установлены
            settings = {
                'cameras_faces': self.camera_faces,
                'cameras_motion': self.camera_motion,
                'cameras_recording': self.camera_recording,
                'cameras_triggered': self.camera_triggered,
                'timeouts': self.MOTION_TIMEOUTS,
                'threshold': self.MOTION_THRESHOLD,
                'min_area': self.MOTION_MIN_AREA,
                'masks': list(self.masks.keys())
            }
            motion_logger.log_settings(settings)

        motion_logger.log_system_event("System initialized")

    def load_all_masks(self):
        """Загрузка всех масок из папки masks"""
        masks_dir = "masks"
        if not os.path.exists(masks_dir):
            os.makedirs(masks_dir)
            return

        for filename in os.listdir(masks_dir):
            if filename.startswith("camera_") and filename.endswith(".png"):
                try:
                    parts = filename.split('_')
                    camera_idx = int(parts[1])
                    mask_path = os.path.join(masks_dir, filename)
                    mask = load_mask(mask_path)
                    if mask is not None:
                        self.masks[camera_idx] = mask
                        motion_logger.log_system_event(f"Loaded mask for camera {camera_idx}")
                except (ValueError, IndexError):
                    continue

    def get_user_settings(self):
        """Получение настроек от пользователя"""
        logger.info("Configuring system")
        print("=" * 50)

        print("Enter camera numbers for face detection:")
        print("Available cameras:", self.camera_indices)
        try:
            self.camera_faces = list(map(int, input("  ").split()))
        except Exception:
            self.camera_faces = []

        print("\nEnter camera numbers for motion detection:")
        print("Available cameras:", self.camera_indices)
        try:
            self.camera_motion = list(map(int, input("  ").split()))
        except Exception:
            self.camera_motion = []
        
        # --- НОВОЕ ---
        print("\nEnter camera numbers for event recording (on motion):")
        print("Available cameras:", self.camera_indices)
        try:
            self.camera_recording = list(map(int, input("  ").split()))
        except Exception:
            self.camera_recording = []
        # --- /НОВОЕ ---

        print("\nEnter camera numbers that activate only on motion:")
        print("Available cameras:", self.camera_indices)
        try:
            self.camera_triggered = list(map(int, input("  ").split()))
        except Exception:
            self.camera_triggered = []

        print("\nEnter timeouts (seconds) for each camera individually.")
        print("Format: press Enter to keep default (10s).")
        for cam_idx in self.camera_indices:
            try:
                v = input(f"  Cam{cam_idx} timeout (s) [current {self.MOTION_TIMEOUTS.get(cam_idx, 10)}]: ").strip()
                if v == "":
                    # оставить текущее значение
                    continue
                t = int(v)
                if t < 0:
                    logger.warning("Cannot set negative timeout")
                    continue
                self.MOTION_TIMEOUTS[cam_idx] = t
            except Exception:
                logger.warning("Invalid input")

        # Настройка масок

        # Логирование настроек
        settings = {
            'cameras_faces': self.camera_faces,
            'cameras_motion': self.camera_motion,
            # --- НОВОЕ ---
            'cameras_recording': self.camera_recording,
            # --- /НОВОЕ ---
            'cameras_triggered': self.camera_triggered,
            'timeouts': self.MOTION_TIMEOUTS,   # <-- changed
            'threshold': self.MOTION_THRESHOLD,
            'min_area': self.MOTION_MIN_AREA,
            'masks': list(self.masks.keys())
        }
        motion_logger.log_settings(settings)

    # --- НОВОЕ (методы для записи видео) ---
    def start_recording(self, camera_idx, initial_frame, event_name="motion_detected"):
        """Запускает запись видео для указанной камеры."""
        if camera_idx not in self.camera_recording:
            return # Камера не настроена для записи по событию

        # Если запись уже идёт, не запускаем новую
        if camera_idx in self.video_writers:
            # Обновляем время начала, чтобы продлить запись
            self.recording_start_time[camera_idx] = time.time()
            return

        now = datetime.datetime.now()
        # Формируем путь: VIDEO_DIR / дата / событие / камера
        date_dir = os.path.join(self.VIDEO_DIR, now.strftime("%Y-%m-%d"))
        event_dir = os.path.join(date_dir, event_name)
        camera_dir = os.path.join(event_dir, f"cam{camera_idx}")
        
        os.makedirs(camera_dir, exist_ok=True) # Создаем всю структуру папок
        
        filename = f"recording_{now.strftime('%H-%M-%S')}.avi"
        filepath = os.path.join(camera_dir, filename)

        # Подготовка VideoWriter
        fourcc = cv2.VideoWriter_fourcc(*'XVID')
        writer = cv2.VideoWriter(filepath, fourcc, self.FPS, (initial_frame.shape[1], initial_frame.shape[0]))
        
        # Инициализация очереди и добавление первого кадра
        frame_queue = queue.Queue()
        frame_queue.put(initial_frame)

        # Сохранение объектов
        self.video_writers[camera_idx] = writer
        self.recording_start_time[camera_idx] = time.time()
        self.frame_queues[camera_idx] = frame_queue

        # Запуск потока записи
        recording_thread = threading.Thread(target=self._write_video_thread, args=(camera_idx,))
        recording_thread.daemon = True
        recording_thread.start()
        self.recording_threads[camera_idx] = recording_thread

        motion_logger.log_system_event(f"Started recording for camera {camera_idx} on event '{event_name}' -> {filepath}")


    def stop_recording(self, camera_idx):
        """Останавливает запись видео для указанной камеры."""
        if camera_idx in self.video_writers:
            # Добавляем специальный сигнал в очередь для остановки потока
            self.frame_queues[camera_idx].put(None)
            
            # Ждем завершения потока
            if camera_idx in self.recording_threads:
                self.recording_threads[camera_idx].join()
                del self.recording_threads[camera_idx]

            # Освобождаем VideoWriter
            self.video_writers[camera_idx].release()
            del self.video_writers[camera_idx]
            del self.recording_start_time[camera_idx]
            del self.frame_queues[camera_idx]

            motion_logger.log_system_event(f"Recording for camera {camera_idx} stopped")


    def _write_video_thread(self, camera_idx):
        """Поток для записи видео из очереди."""
        writer = self.video_writers[camera_idx]
        frame_queue = self.frame_queues[camera_idx]
        start_time = self.recording_start_time[camera_idx]
        
        while True:
            try:
                frame = frame_queue.get(timeout=1)
                if frame is None: # Сигнал остановки
                    break
                writer.write(frame)
            except queue.Empty:
                # Проверяем, пора ли останавливать запись
                elapsed = time.time() - start_time
                if elapsed >= self.VIDEO_DURATION:
                    break
                continue

        # Запись завершена
        writer.release()
        motion_logger.log_system_event(f"Video file for camera {camera_idx} closed")
    # --- /НОВОЕ ---

    def process_triggered_camera(self, camera_idx, frame, current_time):
        mask = self.masks.get(camera_idx)
        display_frame = frame.copy()

        if self.motion_detected[camera_idx]:
            # Активный режим
            if current_time - self.last_motion_check.get(camera_idx, 0) > 0.5:
                if self.prev_frames[camera_idx] is not None:
                    threshold = self.MOTION_THRESHOLDS.get(camera_idx, self.MOTION_THRESHOLD)
                    motion, contours = detect_motion(
                        self.prev_frames[camera_idx], frame,
                        threshold, self.MOTION_MIN_AREA, mask
                    )
                    if motion:
                        # --- НОВОЕ ---
                        if camera_idx in self.camera_recording:
                            self.start_recording(camera_idx, frame, event_name="motion_detected")
                        # --- /НОВОЕ ---
                        self.last_motion_time[camera_idx] = current_time
                        motion_logger.log_system_event(f"Cam{camera_idx}: Motion continues")
                self.last_motion_check[camera_idx] = current_time
                self.prev_frames[camera_idx] = frame.copy()

            time_since_last_motion = current_time - self.last_motion_time[camera_idx]
            timeout = self.MOTION_TIMEOUTS.get(camera_idx, self.MOTION_TIMEOUT)
            time_left = int(timeout - time_since_last_motion)
            if time_since_last_motion > timeout:
                if camera_idx in self.active_motion_cameras:
                    duration = current_time - self.motion_start_time[camera_idx]
                    motion_logger.log_motion_stopped(camera_idx, duration, 0)
                    self.active_motion_cameras.remove(camera_idx)
                self.motion_detected[camera_idx] = False
                self.last_check_time[camera_idx] = current_time
                motion_logger.log_camera_status(camera_idx, "Transition to standby")
                # --- НОВОЕ ---
                if camera_idx in self.video_writers:
                    self.stop_recording(camera_idx)
                # --- /НОВОЕ ---
                return get_waiting_frame(camera_idx)

            display_frame = draw_motion_visualization(frame, [], camera_idx, mask, time_left)

            # Face recognition / detection
            if camera_idx in self.camera_faces:
                if self.recognizer:
                    # Модель обучена - распознавание лиц
                    display_frame, face_boxes = detect_and_recognize_faces(
                        self.recognizer, self.label_dict, self.face_cascade, display_frame
                    )
                else:
                    # Модель НЕ обучена - только детекция (все лица красные)
                    display_frame, face_boxes = detect_faces_only(display_frame)
                
                if face_boxes:
                    cv2.putText(display_frame, f"Faces: {len(face_boxes)}", (15, 145),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

            # Timestamp
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            cv2.putText(display_frame, timestamp, (10, display_frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            return display_frame

        else:
            # Режим ожидания
            time_since_last_check = current_time - self.last_check_time[camera_idx]
            if time_since_last_check >= self.CHECK_INTERVAL:
                if self.prev_frames[camera_idx] is not None:
                    threshold = self.MOTION_THRESHOLDS.get(camera_idx, self.MOTION_THRESHOLD)
                    motion, _ = detect_motion(
                        self.prev_frames[camera_idx], frame,
                        threshold, self.MOTION_MIN_AREA, mask
                    )
                    if motion:
                        # --- НОВОЕ ---
                        if camera_idx in self.camera_recording:
                            self.start_recording(camera_idx, frame, event_name="motion_detected")
                        # --- /НОВОЕ ---
                        self.motion_detected[camera_idx] = True
                        self.last_motion_time[camera_idx] = current_time
                        self.motion_start_time[camera_idx] = current_time
                        self.last_motion_check[camera_idx] = current_time
                        motion_logger.log_motion_detected(camera_idx, is_triggered=True)
                        self.active_motion_cameras.add(camera_idx)
                        self.prev_frames[camera_idx] = frame.copy()
                        display_frame = draw_motion_visualization(frame, [], camera_idx, mask, self.MOTION_TIMEOUT)
                        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                        cv2.putText(display_frame, timestamp, (10, display_frame.shape[0] - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                        return display_frame
                self.last_check_time[camera_idx] = current_time
                self.prev_frames[camera_idx] = frame.copy()

            waiting_frame = get_waiting_frame(camera_idx)
            if mask is not None:
                waiting_frame = overlay_mask(waiting_frame, mask)

            # Timestamp на кадре ожидания
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            cv2.putText(waiting_frame, timestamp, (10, waiting_frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            return waiting_frame


    def process_motion_camera(self, camera_idx, frame, current_time):
        mask = self.masks.get(camera_idx)
        display_frame = frame.copy()
    
        if self.motion_detected[camera_idx]:
            threshold = self.MOTION_THRESHOLDS.get(camera_idx, self.MOTION_THRESHOLD)
            motion, contours = detect_motion(
                self.prev_frames[camera_idx], frame,
                threshold, self.MOTION_MIN_AREA, mask
            )
            if motion:
                # --- НОВОЕ ---
                if camera_idx in self.camera_recording:
                    self.start_recording(camera_idx, frame, event_name="motion_detected")
                # --- /НОВОЕ ---
                self.last_motion_time[camera_idx] = current_time
                self.motion_contours[camera_idx] = contours
                objects_info = motion_logger.track_objects(camera_idx, contours)
                if objects_info['new_objects']:
                    motion_logger.log_new_objects(camera_idx, objects_info)
                motion_logger.log_motion_summary(camera_idx, objects_info)
    
            time_since_last_motion = current_time - self.last_motion_time[camera_idx]
            timeout = self.MOTION_TIMEOUTS.get(camera_idx, self.MOTION_TIMEOUT)
            time_left = int(timeout - time_since_last_motion)
            if time_since_last_motion > timeout:
                if camera_idx in self.active_motion_cameras:
                    duration = current_time - self.motion_start_time[camera_idx]
                    total_objects = motion_logger.object_counter.get(camera_idx, 0)
                    motion_logger.log_motion_stopped(camera_idx, duration, total_objects)
                    self.active_motion_cameras.remove(camera_idx)
                self.motion_detected[camera_idx] = False
                self.motion_contours[camera_idx] = []
                self.last_check_time[camera_idx] = current_time
                motion_logger.log_camera_status(camera_idx, "Transition to standby")
                # --- НОВОЕ ---
                if camera_idx in self.video_writers:
                    self.stop_recording(camera_idx)
                # --- /НОВОЕ ---
                return get_waiting_frame(camera_idx)
    
            self.prev_frames[camera_idx] = frame.copy()
            display_frame = draw_motion_visualization(frame, self.motion_contours[camera_idx], camera_idx, mask, time_left)
    
            # Face recognition / detection
            if camera_idx in self.camera_faces:
                if self.recognizer:
                    display_frame, face_boxes = detect_and_recognize_faces(
                        self.recognizer, self.label_dict, self.face_cascade, display_frame
                    )
                else:
                    display_frame, face_boxes = detect_faces_only(display_frame)
                
                if face_boxes:
                    cv2.putText(display_frame, f"Faces: {len(face_boxes)}", (15, 145),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    
            # Timestamp
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            cv2.putText(display_frame, timestamp, (10, display_frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
    
            return display_frame

        else:
            # Камера ждёт движения
            time_since_last_check = current_time - self.last_check_time[camera_idx]
            if time_since_last_check >= self.CHECK_INTERVAL:
                if self.prev_frames[camera_idx] is not None:
                    threshold = self.MOTION_THRESHOLDS.get(camera_idx, self.MOTION_THRESHOLD)
                    motion, contours = detect_motion(
                        self.prev_frames[camera_idx], frame,
                        threshold, self.MOTION_MIN_AREA, mask
                    )
                    if motion:
                        # --- НОВОЕ ---
                        if camera_idx in self.camera_recording:
                            self.start_recording(camera_idx, frame, event_name="motion_detected")
                        # --- /НОВОЕ ---
                        self.motion_detected[camera_idx] = True
                        self.last_motion_time[camera_idx] = current_time
                        self.motion_start_time[camera_idx] = current_time
                        self.motion_contours[camera_idx] = contours
                        objects_info = motion_logger.track_objects(camera_idx, contours)
                        if objects_info['new_objects']:
                            motion_logger.log_new_objects(camera_idx, objects_info)
                        motion_logger.log_motion_detected(camera_idx)
                        motion_logger.log_motion_summary(camera_idx, objects_info)
                        self.active_motion_cameras.add(camera_idx)
                        self.prev_frames[camera_idx] = frame.copy()
                        display_frame = draw_motion_visualization(frame, contours, camera_idx, mask, self.MOTION_TIMEOUT)
                        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                        cv2.putText(display_frame, timestamp, (10, display_frame.shape[0] - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)
                        return display_frame

                self.last_check_time[camera_idx] = current_time
                self.prev_frames[camera_idx] = frame.copy()

            waiting_frame = get_waiting_frame(camera_idx)
            if mask is not None:
                waiting_frame = overlay_mask(waiting_frame, mask)

            # Timestamp на кадре ожидания
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            cv2.putText(waiting_frame, timestamp, (10, waiting_frame.shape[0] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

            return waiting_frame


    def process_static_camera(self, camera_idx, frame):
        display_frame = frame.copy()
        mask = self.masks.get(camera_idx)
        if mask is not None:
            display_frame = overlay_mask(display_frame, mask)

        # Face recognition / detection
        if camera_idx in self.camera_faces:
            if self.recognizer is not None:
                display_frame, face_boxes = detect_and_recognize_faces(
                    self.recognizer, self.label_dict, self.face_cascade, display_frame
                )
            else:
                display_frame, face_boxes = detect_faces_only(display_frame)
            
            if face_boxes:
                cv2.putText(display_frame, f"Faces: {len(face_boxes)}",
                            (15, 145), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

        # Добавляем timestamp
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        cv2.putText(display_frame, timestamp, 
                    (10, display_frame.shape[0] - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)

        return display_frame


    def process_camera_frame(self, camera_idx, frame, current_time):
        if frame is None:
            return get_no_signal_frame(camera_idx)

        frame = cv2.resize(frame, (640, 480))

        # --- НОВОЕ ---
        # Проверяем, нужно ли начать запись для статической камеры с детекцией движения
        if (camera_idx not in self.camera_triggered and 
            camera_idx not in self.camera_motion and 
            camera_idx in self.camera_recording and 
            camera_idx in self.camera_motion): # Если камера не в TRIGGERED/MOTION, но в recording и motion
            # Для статической камеры с детекцией: проверяем текущий кадр против предыдущего
            if self.prev_frames[camera_idx] is not None:
                mask = self.masks.get(camera_idx)
                threshold = self.MOTION_THRESHOLDS.get(camera_idx, self.MOTION_THRESHOLD)
                motion, _ = detect_motion(
                    self.prev_frames[camera_idx], frame,
                    threshold, self.MOTION_MIN_AREA, mask
                )
                if motion:
                    self.start_recording(camera_idx, frame, event_name="motion_detected")
            self.prev_frames[camera_idx] = frame.copy()
        # --- /НОВОЕ ---

        # ✅ Камера одновременно в режимах TRIGGERED и MOTION
        if camera_idx in self.camera_triggered and camera_idx in self.camera_motion:
            if self.motion_detected[camera_idx]:
                # Камера уже активирована → работаем как motion-камера
                return self.process_motion_camera(camera_idx, frame, current_time)
            else:
                # Камера ждёт движения → используем поведение triggered
                return self.process_triggered_camera(camera_idx, frame, current_time)

        # Только TRIGGERED
        elif camera_idx in self.camera_triggered:
            return self.process_triggered_camera(camera_idx, frame, current_time)

        # Только MOTION
        elif camera_idx in self.camera_motion:
            return self.process_motion_camera(camera_idx, frame, current_time)

        # Статическая (обычный режим)
        else:
            return self.process_static_camera(camera_idx, frame)


    def setup_masks(self):
        """Подменю для настройки масок"""
        while True:
            print("Configure Masks")
            print("1. View Existing Masks")
            print("2. Create New Masks")
            print("3. Delete Masks")
            print("q. Back to Main Menu")

            choice = input("  ")

            if choice == "1":
                self.view_masks()
            elif choice == "2":
                self.create_masks()
            elif choice == "3":
                self.delete_masks()
            elif choice == "q":
                break
            else:
                logger.warning("Invalid choice")

    def view_masks(self):
        """Просмотр сохранённых масок"""
        masks_dir = "masks"
        if not os.path.exists(masks_dir):
            logger.warning("Folder 'masks' not found")
            return

        mask_files = [f for f in os.listdir(masks_dir) if f.endswith(".png")]
        if not mask_files:
            logger.warning("No masks found")
            return

        while True:
            print("View Masks")
            print("Available masks:")
            for i, mask_file in enumerate(mask_files, 1):
                print(f"{i}. {mask_file}")
            print("q. Exit")
            choice = input(" ").strip()
            if choice == "q":
                print("Exiting mask viewer.")
                break
            try:
                idx = int(choice)
                if idx < 1 or idx > len(mask_files):
                    logger.warning("Invalid mask number")
                    continue

                mask_path = os.path.join(masks_dir, mask_files[idx - 1])
                mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
                if mask is None:
                    logger.error("Failed to load mask")
                    continue

                cv2.imshow(f"View Mask: {mask_files[idx - 1]}", mask)
                print("Close window to continue viewing other masks.")
                cv2.waitKey(0)
                cv2.destroyAllWindows()

            except ValueError:
                print("Enter a valid number or 'q' to exit.")


    def create_masks(self):
        """Создание масок"""
        for cam_idx in self.camera_indices:
            print(f"\nCreate mask for camera {cam_idx} (y/n):")
            if input("  ").lower() == 'y':
                print("Enter mask name (Enter = 'default'):")
                mask_name = input("  ").strip() or "default"
                mask_path = self.mask_creator.create_mask(cam_idx, mask_name)
                if mask_path:
                    mask = load_mask(mask_path)
                    if mask is not None:
                        self.masks[cam_idx] = mask
                        logger.success(f"Created mask for camera {cam_idx}")
    def delete_masks(self):
        """Удаление масок"""
        masks_dir = "masks"
        if not os.path.exists(masks_dir):
            logger.warning("Folder 'masks' not found")
            return

        mask_files = [f for f in os.listdir(masks_dir) if f.endswith(".png")]
        if not mask_files:
            logger.warning("No masks found")
            return

        print("Available masks:")
        for i, mask_file in enumerate(mask_files, 1):
            print(f"{i}. {mask_file}")

        print("\nEnter mask numbers to delete (e.g., '1 3 5'):")
        try:
            choice = input("  ").strip()
            if not choice:
                print("Nothing selected.")
                return

            indices = list(map(int, choice.split()))
            indices = [idx - 1 for idx in indices if 1 <= idx <= len(mask_files)]  # преобразование к индексам списка

            if not indices:
                print("Invalid mask numbers.")
                return

            # Удаление файлов и масок из памяти
            deleted_masks = []
            for idx in sorted(indices, reverse=True):  # удаляем с конца, чтобы не сбить индексы
                mask_file = mask_files[idx]
                mask_path = os.path.join(masks_dir, mask_file)

                try:
                    os.remove(mask_path)
                    deleted_masks.append(mask_file)

                    # Удаляем маску из памяти системы
                    try:
                        # Извлекаем номер камеры из имени файла
                        parts = mask_file.split('_')
                        if len(parts) >= 2:
                            camera_idx_str = parts[1]
                            # Проверяем, является ли следующая часть числом
                            if camera_idx_str.isdigit():
                                camera_idx = int(camera_idx_str)
                                if camera_idx in self.masks:
                                    del self.masks[camera_idx]
                                    logger.success(f"Mask for camera {camera_idx} removed from memory")
                    except Exception:
                        pass  # Игнорируем ошибки при удалении из памяти

                except Exception as e:
                    logger.error(f"Error deleting mask {mask_file}: {e}")

            if deleted_masks:
                print(f"Deleted masks: {', '.join(deleted_masks)}")
                logger.success(f"Deleted masks: {', '.join(deleted_masks)}")
            else:
                logger.warning("Failed to delete selected masks")
        except ValueError:
            print("Invalid format. Enter numbers separated by space.")
        except Exception as e:
            logger.error(f"Error deleting masks: {e}")
    @logger.catch
    def run(self):
        try:
            self.initialize()
            while True:
                frames = []
                current_time = time.time()
                for idx, cap in enumerate(self.caps):
                    camera_idx = self.camera_indices[idx]
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret:
                            processed_frame = self.process_camera_frame(camera_idx, frame, current_time)
                        else:
                            processed_frame = get_no_signal_frame(camera_idx)
                            motion_logger.log_camera_status(camera_idx, "No signal")
                    else:
                        processed_frame = get_no_signal_frame(camera_idx)
                        logger.critical(f"Camera {camera_idx}: not found")
                    
                    # --- НОВОЕ ---
                    # Добавляем кадр в очередь записи, если запись активна
                    if camera_idx in self.video_writers:
                        try:
                            # Копируем кадр, чтобы избежать проблем с изменением в других потоках
                            frame_copy = processed_frame.copy()
                            self.frame_queues[camera_idx].put_nowait(frame_copy)
                        except queue.Full:
                            # Если очередь полна, пропускаем кадр
                            pass
                    # --- /НОВОЕ ---

                    frames.append(cv2.resize(processed_frame, (320, 240)))

                grid = create_video_grid(frames, (2, 2), (640, 480))
                self.add_status_info(grid, current_time)
                cv2.imshow("Multi-Camera Surveillance System", grid)

                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('r'):
                    self.reset_motion_cameras()
                elif key == ord('+'):
                    self.adjust_sensitivity(-5)
                elif key == ord('-'):
                    self.adjust_sensitivity(5)
                elif key == ord('m'):
                    self.setup_masks()
        finally:
            self.cleanup()

    def add_status_info(self, grid, current_time):
        status_lines = []
        for cam_idx in self.camera_indices:
            status_parts = []
            if cam_idx in self.camera_faces:
                status_parts.append("Face Detection")
            if cam_idx in self.camera_motion:
                status_parts.append("Motion Detection")
            # --- НОВОЕ ---
            if cam_idx in self.camera_recording:
                status_parts.append("Record On Event")
            # --- /НОВОЕ ---
            if cam_idx in self.camera_triggered:
                if self.motion_detected[cam_idx]:
                    timeout = self.MOTION_TIMEOUTS.get(cam_idx, self.MOTION_TIMEOUT)
                    time_left = int(timeout - (current_time - self.last_motion_time[cam_idx]))
                    status_parts.append(f"TRIGGERED ({time_left}s)")
                else:
                    next_check = int(self.CHECK_INTERVAL - (current_time - self.last_check_time[cam_idx]))
                    status_parts.append(f"STANDBY ({next_check}s)")
            elif cam_idx in self.camera_motion:
                if self.motion_detected[cam_idx]:
                    timeout = self.MOTION_TIMEOUTS.get(cam_idx, self.MOTION_TIMEOUT)
                    time_left = int(timeout - (current_time - self.last_motion_time[cam_idx]))
                    status_parts.append(f"ACTIVE ({time_left}s)")
                else:
                    next_check = int(self.CHECK_INTERVAL - (current_time - self.last_check_time[cam_idx]))
                    status_parts.append(f"STANDBY ({next_check}s)")
            else:
                status_parts.append("ALWAYS ON")

            if cam_idx in self.masks:
                status_parts.append("MASK")

            status = " + ".join(status_parts)
            status_lines.append(f"Cam{cam_idx}:{status}")

        cv2.putText(grid, " | ".join(status_lines), (10, 20),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        
        controls = "'r': reset | '+/-': sensitivity | 'm': masks | 'q': quit"
        cv2.putText(grid, controls, (10, grid.shape[0] - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

    def reset_motion_cameras(self):
        """Сброс состояния камер с детектированием движения"""
        for cam_idx in list(set(self.camera_motion + self.camera_triggered)):
            if cam_idx in self.active_motion_cameras:
                duration = time.time() - self.motion_start_time[cam_idx]
                total_objects = motion_logger.object_counter.get(cam_idx, 0)
                motion_logger.log_motion_stopped(cam_idx, duration, total_objects)
                self.active_motion_cameras.discard(cam_idx)

            self.motion_detected[cam_idx] = False
            self.prev_frames[cam_idx] = None
            self.last_motion_time[cam_idx] = 0
            self.last_motion_check[cam_idx] = 0
            self.last_check_time[cam_idx] = time.time()
            self.motion_contours[cam_idx] = []

            if cam_idx in self.camera_motion:
                motion_logger.reset_camera_objects(cam_idx)

        motion_logger.log_system_event("All cameras reset to standby mode")

    def adjust_sensitivity(self, delta):
        """Изменение чувствительности детекции"""
        old_threshold = self.MOTION_THRESHOLD
        self.MOTION_THRESHOLD = max(5, min(100, self.MOTION_THRESHOLD + delta))
        if old_threshold != self.MOTION_THRESHOLD:
            sensitivity = "increased" if delta < 0 else "decreased"
            motion_logger.log_system_event(
                f"Sensitivity {sensitivity}: threshold={self.MOTION_THRESHOLD}"
            )

    def cleanup(self):
        """Очистка ресурсов при завершении"""
        # Логирование для активных камер
        for cam_idx in list(self.active_motion_cameras):
            duration = time.time() - self.motion_start_time[cam_idx]
            total_objects = motion_logger.object_counter.get(cam_idx, 0)
            motion_logger.log_motion_stopped(cam_idx, duration, total_objects)

        # --- НОВОЕ ---
        # Остановка всех активных записей
        for cam_idx in list(self.video_writers.keys()):
            self.stop_recording(cam_idx)
        # --- /НОВОЕ ---

        motion_logger.log_system_event("Surveillance system shutdown")

        # Освобождение ресурсов
        release_cameras(self.caps)
        cv2.destroyAllWindows()


if __name__ == "__main__":
    system = SurveillanceSystem()
    system.main_menu()
