import cv2
import time 
import os
from directory import directory
from AI_face import learning
from loguru import logger
def sv():
    print("You need to create a dataset directory (y/n)")
    create_dir=input(str())
    if create_dir=="y":
            directory()
    else:
        
    # --- Создание основной папки directory ---
    # предполагаю, что эта функция создаёт папку "directory"
    
        # --- Запрос ФИО ---
        fio = input("Enter the user's full name: ").strip()
    
        # --- Полный путь для сохранения фото ---
        save_dir = os.path.join("dataset", fio)
        os.makedirs(save_dir, exist_ok=True)  # создаём папку, если её нет
    
        # --- Настройка камеры ---
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    
        if not cap.isOpened():
            logger.error("Couldn't open camera")
            exit()
    
        print("The camera is running. Press ENTER to start shooting")
    
        # --- Ждем ENTER ---
        while True:
            ret, frame = cap.read()
            if not ret:
                logger.error("Frame reading error")
                break
            
            cv2.imshow("Camera", frame)
    
            key = cv2.waitKey(1) & 0xFF
            if key == 13:  # ENTER
                logger.info("Filming has begun")
                break
            elif key == ord('q'):
                logger.info("Exit without shooting")
                cap.release()
                cv2.destroyAllWindows()
                exit()
    
        # --- Съёмка кадров ---
        for i in range(20):
            ret, frame = cap.read()
            if not ret:
                logger.error("Frame reading error")
                break
            
            filename = os.path.join(save_dir, f"photo_{i+1}.png")
            cv2.imwrite(filename, frame)
    
            cv2.imshow("Camera", frame)
            time.sleep(0.5)
    
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            
        cap.release()
        cv2.destroyAllWindows()
        logger.success("All photos are saved in a folder:", save_dir)
    
        print("To train the model, enter (y/n)")
        checking=input(str())
        if checking=="y":
            learning()
        else:
            return 0

