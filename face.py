
import cv2
import numpy as np

def detect_faces_lbph():
# Загружаем модель и словарь имён
    recognizer = cv2.face.LBPHFaceRecognizer_create()
    recognizer.read("face_model.yml")
    label_dict = np.load("labels.npy", allow_pickle=True).item()

    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    cap = cv2.VideoCapture(0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)

        for (x, y, w, h) in faces:
            roi = gray[y:y+h, x:x+w]
            label_id, confidence = recognizer.predict(roi)

            if confidence < 80:  # чем меньше — тем увереннее
                name = label_dict[label_id]
            else:
                name = "Is unknown"

            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
            cv2.putText(frame, f"{name} ({int(confidence)})", (x, y-10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

        cv2.imshow("Face Recognition", frame)

        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()
