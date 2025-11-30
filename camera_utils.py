import cv2
import numpy as np
import os
from logger import logger

def initialize_cameras(camera_indices):
    """Инициализация камер"""
    caps = []
    for idx in camera_indices:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            logger.success(f"Camera initialized {idx}")
        else:
            logger.error(f"Failed to initialize the camera {idx}")
        caps.append(cap)
    return caps

def release_cameras(caps):
    """Освобождение ресурсов камер"""
    for cap in caps:
        if cap.isOpened():
            cap.release()
    logger.info("Camera resources have been released")

def create_video_grid(frames, grid_size=(2, 2), output_size=(640, 480)):
    """Создание сетки из кадров"""
    if not frames:
        return np.zeros((output_size[1], output_size[0], 3), dtype=np.uint8)
    
    resized_frames = [cv2.resize(frame, (output_size[0] // grid_size[1], 
                                       output_size[1] // grid_size[0])) 
                     for frame in frames]
    
    rows = []
    for i in range(0, len(resized_frames), grid_size[1]):
        row_frames = resized_frames[i:i + grid_size[1]]
        if len(row_frames) < grid_size[1]:
            empty_frames = [np.zeros_like(row_frames[0]) for _ in range(grid_size[1] - len(row_frames))]
            row_frames.extend(empty_frames)
        row = np.hstack(row_frames)
        rows.append(row)
    
    grid = np.vstack(rows[:grid_size[0]])
    return grid

def get_no_signal_frame(camera_idx, size=(640, 480)):
    """Создание кадра 'Нет сигнала'"""
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    cv2.putText(frame, f"No signal {camera_idx}", 
               (240, size[1] // 2), cv2.FONT_HERSHEY_SIMPLEX, 
               1, (0, 0, 255), 2)
    return frame

def get_waiting_frame(camera_idx, time_left=None, size=(640, 480)):
    """Создание кадра 'Ожидание движения'"""
    frame = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    cv2.putText(frame, f"CAMERA {camera_idx}", 
               (240, size[1] // 2 - 60), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    cv2.putText(frame, "WAITING FOR MOTION", 
               (size[0] // 2 - 120, size[1] // 2), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    if time_left is not None:
        cv2.putText(frame, f"Next check: {time_left}s", 
                   (240, size[1] // 2 + 40), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    cv2.putText(frame, "Standby mode", 
               (240, size[1] - 20), 
               cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
    return frame

class MultiMaskCreator:
    def create_mask(self, camera_index, mask_name="default"):
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            logger.error(f"Couldn't open camera {camera_index}")

        print(f"Creating masks for the camera {camera_index}")
        print("Instructions:")
        print("1. 's' - start/finish drawing the polygon")
        print("2. LMB - add polygon point")
        print("3. PCM - delete the last point")
        print("4. 'c' - clear the current polygon")
        print("5. 'n' - add the current polygon to the mask and start a new one")
        print("6. 'q' - save all masks and exit")
        print("7. ESC - exit without saving")

        os.makedirs("masks", exist_ok=True)
        mask_path = f"masks/camera_{camera_index}_{mask_name}.png"

        polygons = []  # Список всех полигонов
        current_polygon = []
        drawing = False

        def mouse_callback(event, x, y, flags, param):
            nonlocal current_polygon, drawing
            if event == cv2.EVENT_LBUTTONDOWN and drawing:
                current_polygon.append((x, y))
            elif event == cv2.EVENT_RBUTTONDOWN and drawing and current_polygon:
                current_polygon.pop()

        cv2.namedWindow("Create MultiMask")
        cv2.setMouseCallback("Create MultiMask", mouse_callback)

        while True:
            ret, frame = cap.read()
            if not ret:
                logger.critical("Couldn't get a frame")
                break

            display_frame = frame.copy()

            # Рисуем уже сохраненные полигоны
            for poly in polygons:
                cv2.polylines(display_frame, [np.array(poly)], isClosed=True, color=(0,255,0), thickness=2)
                for pt in poly:
                    cv2.circle(display_frame, pt, 5, (0,0,255), -1)

            # Рисуем текущий полигон
            if len(current_polygon) > 1:
                for i in range(len(current_polygon)-1):
                    cv2.line(display_frame, current_polygon[i], current_polygon[i+1], (0,255,255), 2)
            for pt in current_polygon:
                cv2.circle(display_frame, pt, 5, (255,0,0), -1)

            cv2.imshow("Create MultiMask", display_frame)
            key = cv2.waitKey(30) & 0xFF

            if key == ord('s'):
                drawing = not drawing
                print(f"Drawing {'started' if drawing else 'finished'}")
            elif key == ord('c'):
                current_polygon = []
                print("Clearing the current polygon")
            elif key == ord('n'):
                if len(current_polygon) >= 3:
                    polygons.append(current_polygon.copy())
                    current_polygon = []
                    logger.success(f"Polygon added. Total polygons: {len(polygons)}")
                else:
                    logger.error("You need >= 3 points for a polygon")
            elif key == ord('q'):
                if polygons:
                    mask = np.zeros(frame.shape[:2], dtype=np.uint8)
                    for poly in polygons:
                        pts = np.array(poly, np.int32)
                        cv2.fillPoly(mask, [pts], 255)  # Все полигоны в одной маске
                    cv2.imwrite(mask_path, mask)
                    logger.success(f"Mask save: {mask_path}")
                    cap.release()
                    cv2.destroyAllWindows()
                    return mask_path
                else:
                    logger.error("There is no polygon to save")
            elif key == 27:
                logger.warning("Exit without save")
                cap.release()
                cv2.destroyAllWindows()
                return None


def load_mask(mask_path):
    """Загружает маску из файла"""
    if os.path.exists(mask_path):
        return cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
    return None

def overlay_mask(frame, mask, color=(0,255,0), alpha=0.3):
    """Накладывает прозрачную маску на кадр"""
    if mask is None:
        return frame
    overlay = frame.copy()
    mask_3ch = cv2.merge([mask, mask, mask])
    color_layer = np.zeros_like(frame)
    color_layer[:] = color
    overlay = np.where(mask_3ch != 0, cv2.addWeighted(color_layer, alpha, overlay, 1 - alpha, 0), overlay)
    return overlay

def draw_bounding_box(frame, rect, label=None, color=(0, 255, 0)):
    """Унифицированное рисование bounding box"""
    x, y, w, h = rect
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
    if label:
        cv2.putText(frame, label, (x + 5, y + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

def load_lbph_face_recognizer(model_path="face_model.yml", labels_path="labels.npy"):
    """Загрузка обученной модели распознавания лиц"""
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read(model_path)
    label_dict = np.load(labels_path, allow_pickle=True).item()
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    return recognizer, label_dict, face_cascade


def detect_faces_only(frame):
    """
    Детекция лиц БЕЗ распознавания (когда модель не обучена).
    Все лица отмечаются как "НЕ РАСПОЗНАН" красным цветом.
    """
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    face_boxes = []
    
    color = (0, 0, 255)  # Красный (BGR)
    
    for (x, y, w, h) in faces:
        face_boxes.append([x, y, x+w, y+h])
        
        # Рисуем красный квадрат
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        
        # Текст "НЕ РАСПОЗНАН"
        label_text = "NE RASPOZNAN"
        text_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        cv2.rectangle(frame, (x, y - text_size[1] - 10), (x + text_size[0] + 5, y), color, -1)
        cv2.putText(frame, label_text, (x + 2, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    return frame, face_boxes

def detect_and_recognize_faces(recognizer, label_dict, face_cascade, frame, confidence_threshold=80):
    """
    Распознавание лиц на кадре.
    - Распознанное лицо: ЗЕЛЁНЫЙ квадрат + имя
    - Нераспознанное лицо: КРАСНЫЙ квадрат + "НЕ РАСПОЗНАН"
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    face_boxes = []

    for (x, y, w, h) in faces:
        roi = gray[y:y+h, x:x+w]
        label_id, confidence = recognizer.predict(roi)
        
        if confidence < confidence_threshold:
            # Распознан - ЗЕЛЁНЫЙ
            name = label_dict.get(label_id, "Неизвестный ID")
            color = (0, 255, 0)  # Зелёный (BGR)
            label_text = f"{name} ({int(confidence)})"
        else:
            # НЕ распознан - КРАСНЫЙ
            color = (0, 0, 255)  # Красный (BGR)
            label_text = f"NE RASPOZNAN ({int(confidence)})"

        face_boxes.append([x, y, x+w, y+h])
        
        # Рисуем квадрат
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
        
        # Фон для текста (для лучшей читаемости)
        text_size = cv2.getTextSize(label_text, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
        cv2.rectangle(frame, (x, y - text_size[1] - 10), (x + text_size[0] + 5, y), color, -1)
        
        # Текст (белый на цветном фоне)
        cv2.putText(frame, label_text, (x + 2, y - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    
    return frame, face_boxes

