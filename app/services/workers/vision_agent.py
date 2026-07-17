# from redis.client import Redis
# import threading
# import time
# import cv2
# import numpy as np  # Used for dilate kernel
# import redis
# import json         # Used for event logging
# import os
# from collections import deque
# from typing import Optional # Essential for fixing "None" errors
# from picamera2 import Picamera2

# ENABLED = False
# class VisionAgent(threading.Thread):
#     def __init__(self, redis_client: redis.Redis):
#         super().__init__()
#         self.r: Redis = redis_client
#         self.stop_event = threading.Event()
        
#         # Camera & Storage Config
#         self.picam2: Optional[Picamera2] = None
#         self.storage_path = "/media/raspiuser/KINGSTON"
        
#         # Vision State
#         self.background_frame: Optional[np.ndarray] = None
#         self.buffer: deque = deque(maxlen=50) 
#         self.out: Optional[cv2.VideoWriter] = None
#         self.is_recording = False
        
#         # Tuning
#         self.MIN_MOTION_AREA = 2000
#         self.LEARNING_RATE = 0.05
#         # Define kernel once to satisfy static analyzer and improve performance
#         self.kernel = np.ones((5, 5), np.uint8) 

#         self.frame_lock = threading.Lock() # For the video frame
#         self.latest_frame: Optional[np.ndarray] = None

#         self.viewer_count = 0
#         self.state_lock = threading.Lock() # For viewer_count and hardware logic

#     def increment_viewers(self):
#         with self.state_lock:
#             self.viewer_count += 1
#             print(f"[Agent] Viewer added. Total: {self.viewer_count}")

#     def decrement_viewers(self):
#         with self.state_lock:
#             self.viewer_count -= 1
#             print(f"[Agent] Viewer removed. Total: {self.viewer_count}")

#     def run(self):
#         print("[Agent] Vision thread active.")
#         try:
#             while not self.stop_event.is_set():
#                 # Fix: Ensure active key exists and is "true"
#                 # is_active = ENABLED#self.r.get("sentinel:camera:active") == "true"
#                 is_active_setting = self.r.get("sentinel:camera:active") == "true"
                
#                 needs_power = is_active_setting or (self.viewer_count > 0)
                
#                 if needs_power and self.picam2 is None:
#                     self._init_camera()
#                 elif not needs_power and self.picam2 is not None:
#                     self._shutdown_camera()

#                 if self.picam2:
#                         try:
#                             self._process_frame(is_active_setting)
#                         except Exception as e:
#                             print(f"[Error] Processing frame failed: {e}")
#                             # If frame processing fails, ensure we don't spam errors
#                             time.sleep(1)
#                 else:
#                     time.sleep(1)
#         except Exception as e:
#             print(f"[Critical Error] Vision thread crashed: {e}")

#     def _init_camera(self):
#         try:
#             print("[Agent] Booting sensor...")
#             self.picam2 = Picamera2()
#             # Try a simpler, more compatible configuration
#             config = self.picam2.create_video_configuration(main={"size": (640, 360)})
#             self.picam2.configure(config)
#             self.picam2.start()
#             print("[Agent] Sensor started successfully.")
#             time.sleep(3) 
#             print("[Agent] Sensor ready.")
#         except Exception as e:
#             print(f"[Agent] Failed to init camera: {e}")
#             self.picam2 = None # Ensure it retries next time

#     def _shutdown_camera(self):
#         self._stop_recording()
#         if self.picam2:
#             self.picam2.stop()
#             self.picam2.close()
#             self.picam2 = None
#         self.background_frame = None

#     def _process_frame(self, is_recording_active):
#         if self.picam2 is None: 
#             return
        
#         # 1. ALWAYS Capture the frame (for the stream)
#         try:
#             frame = self.picam2.capture_array()
#             frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
#         except Exception as e:
#             print(f"[Agent] Capture failed: {e}")
#             return

#         # 2. ALWAYS update the stream
#         with self.frame_lock:
#             self.latest_frame = frame_bgr.copy()

#         # 3. ONLY run Motion/Recording logic if is_recording_active is True
#         if not is_recording_active:
#             return

#         # --- Everything below this line ONLY runs if Active=True ---
#         gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
#         gray_blurred = cv2.GaussianBlur(gray, (21, 21), 0)

#         # Update background model
#         if self.background_frame is None:
#             self.background_frame = gray_blurred.copy().astype("float")
#             return

#         cv2.accumulateWeighted(gray_blurred, self.background_frame, self.LEARNING_RATE)
#         background_base = cv2.convertScaleAbs(self.background_frame)

#         # Delta & Threshold
#         frame_delta = cv2.absdiff(gray_blurred, background_base)
#         _, thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)
#         thresh = cv2.dilate(thresh, self.kernel, iterations=2)
        
#         # Detect Contours
#         contours, _ = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
#         motion_detected = any(cv2.contourArea(c) > self.MIN_MOTION_AREA for c in contours)

#         # Handle Recording State
#         self.buffer.append(frame_bgr)
        
#         if motion_detected and not self.is_recording:
#             self.r.rpush("sentinel:events", json.dumps({"status": "motion"}))
#             self._start_recording()
        
#         if self.is_recording:
#             if not motion_detected:
#                 self._stop_recording()
#             elif self.out is not None:
#                 self.out.write(frame_bgr)

#     def _start_recording(self):
#         self.is_recording = True
#         timestamp = time.strftime("%Y%m%d-%H%M%S")
#         filename = os.path.join(self.storage_path, f"motion_{timestamp}.mp4")
#         # Fix: Use cv2.VideoWriter.fourcc (more reliable in VSCode)
#         fourcc = cv2.VideoWriter.fourcc(*'mp4v')
#         self.out = cv2.VideoWriter(filename, fourcc, 10.0, (640, 360))
#         for buffered_frame in self.buffer:
#             self.out.write(buffered_frame)
#         print(f"[Agent] Recording to {filename}")

#     def _stop_recording(self):
#         if self.out:
#             self.out.release()
#             self.out = None
#         self.is_recording = False

#     def stop(self):
#         self.stop_event.set()
#         self._shutdown_camera()
#         self.join()
