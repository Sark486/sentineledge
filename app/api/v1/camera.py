# import asyncio
# import time
# import cv2
# from app.services.workers.vision_agent import VisionAgent
# from fastapi.responses import StreamingResponse
# from fastapi import Request, APIRouter

# router = APIRouter(prefix="/camera", tags=["Camera"])

# # def generate_frames(agent: VisionAgent):
# #     """Generator to yield frames for the MJPEG stream."""
# #     while True:
# #         frame = None
        
# #         # Check if the camera is currently running
# #         if agent.picam2 is not None:
# #             with agent.frame_lock:
# #                 if agent.latest_frame is not None:
# #                     frame = agent.latest_frame.copy()
        
# #         # If no camera frame (inactive or not yet ready), show offline image
# #         if frame is None:
# #             frame = agent.get_offline_frame()
        
# #         # Encode and yield (Existing code)
# #         _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
# #         frame_bytes = buffer.tobytes()
        
# #         yield (b'--frame\r\n'
# #                b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        
# #         time.sleep(0.06)

# def sync_encode_frame(frame):
#     """Encodes a frame to JPEG. Runs in a separate thread."""
#     _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
#     return buffer.tobytes()

# async def generate_frames(agent: VisionAgent, request: Request):
#     """Generator that yields MJPEG frames."""
#     try:
#         while True:

#             if await request.is_disconnected():
#                 print("[Agent] Client disconnected, breaking loop.")
#                 break
#             frame = None
            
#             # 1. Grab the latest frame from the Agent
#             with agent.frame_lock:
#                 if agent.latest_frame is not None:
#                     frame = agent.latest_frame.copy()
            
#             if frame is not None:
#                 # 2. Non-blocking encoding
#                 frame_bytes = await asyncio.to_thread(sync_encode_frame, frame)
                
#                 # 3. Yield the byte stream for MJPEG
#                 yield (b'--frame\r\n'
#                        b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            
#             # Throttle to ~15 FPS
#             await asyncio.sleep(0.06)
#     except Exception as e:
#         print(f"[Agent] Generator Exception: {e}")
#     except GeneratorExit:
#         print("[Agent] GeneratorExit received (Client closed tab).")
#         raise # Crucial: GeneratorExit must be re-raised
#     finally:
#         print("[Agent] FINALLY block reached. Decrementing viewers.")
#         agent.decrement_viewers()

# @router.get("/stream")
# async def video_feed(request: Request):
#     """
#     Endpoint that powers on the camera on-demand and streams the live feed.
#     """
#     # print("[API] /camera/stream endpoint hit.")
#     agent: VisionAgent = request.app.state.vision_agent
    
#     # Register the viewer (this triggers the camera power-on logic)
#     agent.increment_viewers()
    
#     return StreamingResponse(
#         generate_frames(agent, request), 
#         media_type="multipart/x-mixed-replace; boundary=frame"
#     )