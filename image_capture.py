import cv2
import os
from datetime import datetime
import time

# Change this to the name of the person you're photographing
PERSON_NAME = "juler_hermitano"

def create_folder(name):
    dataset_folder = "dataset"
    if not os.path.exists(dataset_folder):
        os.makedirs(dataset_folder)

    person_folder = os.path.join(dataset_folder, name)
    if not os.path.exists(person_folder):
        os.makedirs(person_folder)
    return person_folder

def capture_photos(name):
    folder = create_folder(name)

    # Initialize the default or USB camera
    camera = cv2.VideoCapture(0)  # Change to 0 for built-in camera
    if not camera.isOpened():
        raise IOError("[ERROR] Cannot open webcam")

    # Optionally set resolution
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    # Allow camera to warm up
    time.sleep(2)

    photo_count = 0
    print(f"Taking photos for {name}. Press SPACE to capture, 'q' to quit.")

    while True:
        ret, frame = camera.read()
        if not ret:
            print("[ERROR] Failed to grab frame")
            break

        cv2.imshow('Capture', frame)
        key = cv2.waitKey(1) & 0xFF

        if key == ord(' '):  # Space key
            photo_count += 1
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.jpg"
            filepath = os.path.join(folder, filename)
            cv2.imwrite(filepath, frame)
            print(f"Photo {photo_count} saved: {filepath}")

        elif key == ord('q'):  # Q key
            break

    # Clean up
    camera.release()
    cv2.destroyAllWindows()
    print(f"Photo capture completed. {photo_count} photos saved for {name}.")

if __name__ == "__main__":
    capture_photos(PERSON_NAME)
