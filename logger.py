# logger.py
import os
import sys
import datetime
from collections import defaultdict

import cv2
from loguru import logger


LOGS_DIR = "logs"
os.makedirs(LOGS_DIR, exist_ok=True)

# Сбрасываем дефолтный sink и настраиваем свои
logger.remove()

# Консоль — цветной, компактный
logger.add(
    sys.stdout,
    colorize=True,
    enqueue=True,
    backtrace=True,
    diagnose=False,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
           "<level>{level:<8}</level> | {message}"
)

# Файл — ротация раз в сутки, хранение 30 дней, сжатие старых
logger.add(
    os.path.join(LOGS_DIR, "{time:YYYY-MM-DD}.log"),
    rotation="00:00",
    retention="30 days",
    compression="zip",
    encoding="utf-8",
    enqueue=True,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
)

class MotionLogger:
    """Фасад поверх loguru + счётчики объектов/ID."""
    def __init__(self):
        self.object_counter = defaultdict(int)
        self.object_tracker = defaultdict(set)

    # ========= Высокоуровневые события =========
    def log_system_event(self, message: str):
        logger.info(message)

    def log_camera_status(self, camera_idx: int, status: str):
        logger.bind(cam=camera_idx).info(f"[CAM{camera_idx}] {status}")

    def log_motion_detected(self, camera_idx: int, is_triggered: bool = False):
        if is_triggered:
            logger.bind(cam=camera_idx).success(f"[CAM{camera_idx}] The camera is turned on by movement")
        else:
            count = self.object_counter[camera_idx]
            logger.bind(cam=camera_idx).info(
                f"[CAM{camera_idx}] Movement detected (of objects: {count})"
            )

    def log_motion_stopped(self, camera_idx: int, duration: float, total_objects: int):
        logger.bind(cam=camera_idx).info(
            f"[CAM{camera_idx}] Movement completed (duration: {duration:.1f}s, objects: {total_objects})"
        )

    def log_new_objects(self, camera_idx: int, objects_info: dict):
        for obj_id, obj_info in objects_info.get('new_objects', {}).items():
            x, y = obj_info['position']
            w, h = obj_info['size']
            logger.bind(cam=camera_idx).info(
                f"[CAM{camera_idx}] New object #{obj_id} (position: {x},{y}, size: {w}x{h})"
            )

    def log_motion_summary(self, camera_idx: int, objects_info: dict):
        logger.bind(cam=camera_idx).debug(
            f"[CAM{camera_idx}] summary: in total: {objects_info['total_objects']}, "
            f"Active: {objects_info['active_objects']}, "
            f"New: {len(objects_info['new_objects'])}, "
            f"The Lost Ones: {len(objects_info['lost_objects'])}"
        )

    def log_settings(self, settings: dict):
        pairs = ", ".join(f"{k}: {v}" for k, v in settings.items())
        logger.success(f"System Settings: {pairs}")

    def log_error(self, message: str):
        logger.error(message)

    # ========= Трекинг объектов =========
    def track_objects(self, camera_idx, contours, grid_size=10):
        current_objects = set()
        objects_info = {
            'new_objects': {},
            'lost_objects': set(),
            'active_objects': len(contours),
            'total_objects': self.object_counter[camera_idx]
        }

        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            cx, cy = x + w // 2, y + h // 2
            object_id = f"{camera_idx}_{cx//grid_size}_{cy//grid_size}"

            current_objects.add(object_id)
            if object_id not in self.object_tracker[camera_idx]:
                self.object_counter[camera_idx] += 1
                objects_info['new_objects'][object_id] = {
                    'position': (x, y),
                    'size': (w, h)
                }

        objects_info['lost_objects'] = self.object_tracker[camera_idx] - current_objects
        self.object_tracker[camera_idx] = current_objects
        return objects_info

    def reset_camera_objects(self, camera_idx):
        self.object_counter[camera_idx] = 0
        self.object_tracker[camera_idx] = set()

    # ========= (Опционально) ручная очистка — обычно не нужна, т.к. есть retention =========
    def cleanup_old_logs(self, days_to_keep=30):
        
        now = datetime.datetime.now()
        try:
            for fname in os.listdir(LOGS_DIR):
                if not (fname.endswith(".log") or fname.endswith(".zip")):
                    continue
                path = os.path.join(LOGS_DIR, fname)
                age_days = (now - datetime.datetime.fromtimestamp(os.path.getmtime(path))).days
                if age_days > days_to_keep:
                    os.remove(path)
                    logger.info(f"The old log file was deleted: {fname}")
        except Exception as e:
            logger.exception(f"Error clearing logs: {e}")

# Глобальный экземпляр (совместим с существующими импортами)
motion_logger = MotionLogger()
