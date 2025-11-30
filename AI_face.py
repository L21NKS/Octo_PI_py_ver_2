import cv2
import os
import numpy as np
from loguru import logger
# Папка с датасетом



def learning():
    DATASET_PATH = "dataset"
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    def load_images(dataset_path):
        faces = []
        labels = []
        label_dict = {}
        current_id = 0

        for person_name in os.listdir(dataset_path):
            person_path = os.path.join(dataset_path, person_name)
            if not os.path.isdir(person_path):
                continue

            label_dict[current_id] = person_name

            for img_name in os.listdir(person_path):
                img_path = os.path.join(person_path, img_name)
                img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)

                if img is None:
                    continue

                faces_detected = face_cascade.detectMultiScale(img, scaleFactor=1.1, minNeighbors=5)
                for (x, y, w, h) in faces_detected:
                    faces.append(img[y:y+h, x:x+w])
                    labels.append(current_id)

            current_id += 1

        return faces, labels, label_dict

    # Загружаем данные
    faces, labels, label_dict = load_images(DATASET_PATH)

    # Обучаем модель
    recognizer.train(faces, np.array(labels))

    # Сохраняем модель и словарь имён
    recognizer.save("face_model.yml")
    np.save("labels.npy", label_dict)
    logger.success("The model is trained and saved")

