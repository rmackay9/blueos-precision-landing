#!/usr/bin/env python3

# Precision Landing Python backend
# Implements these features required by the index.html frontend:
# - Save camera settings including type and RTSP URL
# - Get camera settings including last used settings
# - Save/get precision landing enabled state (persistent across restarts)
# - "Test" button to view the live video and capture the april tag location (placeholder)
# - "Run" button to enable the precision landing including sending MAVLink messages to the vehicle (placeholder)
# - Status endpoint to check if precision landing is currently running

import logging.handlers
import sys
import asyncio
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from typing import Dict, Any
from pydantic import BaseModel

# Import the settings module
from app import settings
# Import the image capture module
from app import image_capture
# Import the landing target sender module
from app import send_landing_target

# Configure console logging
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setLevel(logging.DEBUG)
console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(console_formatter)

# Create logger
logger = logging.getLogger("precision-landing")
logger.setLevel(logging.DEBUG)
logger.addHandler(console_handler)

app = FastAPI()

# Global exception handler to ensure all errors return JSON
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception in {request.url}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "message": f"Internal server error: {str(exc)}",
            "error": "Internal server error"
        }
    )

# Global variable to track precision landing running state
# In a real implementation, this might be a more sophisticated state management system
precision_landing_running = False
precision_landing_process = None

# Pydantic models for request bodies
class EnabledState(BaseModel):
    enabled: bool

logger.info("Precision Landing backend started")


# Internal function to start precision landing
async def start_precision_landing_internal(camera_type: str = None, rtsp_url: str = None):
    """Internal function to start the precision landing process"""
    global precision_landing_running, precision_landing_process

    try:
        logger.info("Starting precision landing process")
        precision_landing_running = True

        # Get camera settings if not provided
        if camera_type is None or rtsp_url is None:
            last_used = settings.get_last_used()
            camera_type = camera_type or last_used.get("camera_type", "siyi-a8")
            rtsp_url = rtsp_url or last_used.get("rtsp", "rtsp://192.168.87.200:8554/main.264")

        logger.info(f"Precision landing using camera: {camera_type}, RTSP: {rtsp_url}")

        # Get camera FOV setting
        camera_horizontal_fov = settings.get_camera_horizontal_fov(camera_type)
        logger.info(f"Using horizontal FOV: {camera_horizontal_fov}° for camera type: {camera_type}")

        # Initialize landing target sender
        sender = send_landing_target.get_landing_target_sender()

        # Refresh sender settings to get latest target system ID
        sender.refresh_settings()

        # Test MAV2Rest connection
        mav_test = sender.test_connection()
        if not mav_test["success"]:
            logger.error(f"MAV2Rest connection failed: {mav_test['message']}")
            precision_landing_running = False
            return

        logger.info("MAV2Rest connection successful - ready to send LANDING_TARGET messages")

        # Get AprilTag target ID from settings
        target_apriltag_id = settings.get_apriltag_target_id()
        if target_apriltag_id == -1:
            logger.info("AprilTag ID filter: -1 (accept any AprilTag ID)")
        else:
            logger.info(f"AprilTag ID filter: {target_apriltag_id} (accept only this specific ID)")

        # Precision landing main loop
        frame_count = 0
        last_detection_time = 0

        while precision_landing_running:
            try:
                # Capture frame from RTSP stream
                frame_result = image_capture.capture_frame_from_stream(rtsp_url, timeout_seconds=30)

                if not frame_result["success"]:
                    logger.warning(f"Failed to capture frame: {frame_result['message']}")
                    await asyncio.sleep(1)  # Wait before retrying
                    continue

                frame_count += 1

                # Check for AprilTag detections
                april_tag_detection = frame_result.get("april_tag_detection", {})

                if april_tag_detection.get("success") and april_tag_detection.get("detections"):
                    all_detections = april_tag_detection["detections"]

                    # Filter detections by target ID (-1 means accept any AprilTag ID)
                    if target_apriltag_id == -1:
                        # Accept any AprilTag ID
                        target_detections = all_detections
                    else:
                        # Only accept specific AprilTag ID
                        target_detections = [d for d in all_detections if d.get("tag_id") == target_apriltag_id]

                    if target_detections:
                        # Get image dimensions from resolution string
                        resolution = frame_result.get("resolution", "640x480")
                        width, height = map(int, resolution.split('x'))

                        # Process the largest (closest) AprilTag with matching ID
                        largest_tag = max(target_detections, key=lambda x: x.get("relative_size", 0))

                        # Send LANDING_TARGET message
                        send_result = send_landing_target.send_apriltag_as_landing_target(
                            largest_tag, width, height, sender, camera_horizontal_fov
                        )

                        if send_result["success"]:
                            last_detection_time = frame_count
                            logger.info(f"Frame {frame_count}: Sent LANDING_TARGET for AprilTag ID {largest_tag['tag_id']} "
                                      f"(angle_x={send_result['angles']['angle_x_deg']:.2f}°, "
                                      f"angle_y={send_result['angles']['angle_y_deg']:.2f}°)")
                        else:
                            logger.warning(f"Failed to send LANDING_TARGET: {send_result['message']}")
                    else:
                        # AprilTags detected but none match target ID (this should only happen for specific ID filtering)
                        if frame_count % 10 == 0:  # Log every 10 frames
                            detected_ids = [d.get("tag_id") for d in all_detections]
                            if target_apriltag_id == -1:
                                # This should not happen since -1 accepts any ID, but log just in case
                                logger.debug(f"Frame {frame_count}: Found AprilTags {detected_ids} but no detections returned (unexpected)")
                            else:
                                logger.debug(f"Frame {frame_count}: Found AprilTags {detected_ids} but looking for specific ID {target_apriltag_id}")
                else:
                    # No AprilTag detected
                    if frame_count % 10 == 0:  # Log every 10 frames
                        logger.debug(f"Frame {frame_count}: No AprilTag detected")

                # Short sleep to prevent overwhelming the system
                await asyncio.sleep(0.1)  # 10 Hz processing rate

            except Exception as e:
                logger.error(f"Error in precision landing loop: {str(e)}")
                await asyncio.sleep(1)  # Wait before retrying

    except Exception as e:
        logger.error(f"Error in precision landing process: {str(e)}")
    finally:
        precision_landing_running = False
        logger.info("Precision landing process stopped")


# Auto-start precision landing if it was previously enabled
async def startup_auto_restart():
    """Check if precision landing was previously enabled and auto-restart if needed"""
    try:
        enabled = settings.get_precision_landing_enabled()
        if enabled:
            logger.info("Auto-restarting precision landing as it was previously enabled")
            # Don't await this so startup doesn't block
            asyncio.create_task(start_precision_landing_internal())
    except Exception as e:
        logger.error(f"Error during auto-restart check: {str(e)}")


# Precision Landing API Endpoints

@app.post("/precision-landing/save-settings")
async def save_precision_landing_settings(
    type: str,
    rtsp: str,
    fov: float = None,
    apriltag_family: str = None,
    tag_id: int = None,
    flight_controller_sysid: int = None
) -> Dict[str, Any]:
    """Save camera settings and other precision landing settings to persistent storage (using query parameters)"""
    logger.info(f"Saving precision landing settings: type={type}, rtsp_url={rtsp}, fov={fov}, "
                f"apriltag_family={apriltag_family}, tag_id={tag_id}, flight_controller_sysid={flight_controller_sysid}")

    # Save camera settings
    camera_success = settings.update_camera_settings(type, rtsp, fov)

    # Save AprilTag settings
    apriltag_success = True
    if apriltag_family is not None or tag_id is not None:
        apriltag_success = settings.update_apriltag_settings(apriltag_family, tag_id)

    # Save MAVLink settings
    mavlink_success = True
    if flight_controller_sysid is not None:
        mavlink_success = settings.update_mavlink_settings(flight_controller_sysid)

    if camera_success and apriltag_success and mavlink_success:
        return {"success": True, "message": f"Settings saved for {type}"}
    else:
        return {"success": False, "message": "Failed to save some settings"}


@app.post("/precision-landing/get-settings")
async def get_precision_landing_settings() -> Dict[str, Any]:
    """Get saved camera settings"""
    logger.info("Getting precision landing settings")

    try:
        # Get the last used camera settings
        last_used = settings.get_last_used()

        # Get RTSP URLs and FOV values for all camera types
        cameras = {}
        for camera_type in ["siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb"]:
            rtsp_url = settings.get_camera_rtsp(camera_type)
            horizontal_fov = settings.get_camera_horizontal_fov(camera_type)
            cameras[camera_type] = {
                "rtsp": rtsp_url,
                "horizontal_fov": horizontal_fov
            }

        # Get AprilTag settings
        apriltag_settings = {
            "family": settings.get_apriltag_family(),
            "target_id": settings.get_apriltag_target_id()
        }

        # Get MAVLink settings
        mavlink_settings = {
            "flight_controller_sysid": settings.get_mavlink_flight_controller_sysid()
        }

        return {
            "success": True,
            "last_used": last_used,
            "cameras": cameras,
            "apriltag": apriltag_settings,
            "mavlink": mavlink_settings
        }
    except Exception as e:
        logger.exception(f"Error getting precision landing settings: {str(e)}")
        return {"success": False, "message": f"Error: {str(e)}"}


@app.post("/precision-landing/save-enabled-state")
async def save_precision_landing_enabled_state(enabled: bool) -> Dict[str, Any]:
    """Save precision landing enabled state to persistent storage (using query parameter)"""
    logger.info(f"Saving precision landing enabled state: {enabled}")
    success = settings.update_precision_landing_enabled(enabled)

    if success:
        return {"success": True, "message": f"Enabled state saved: {enabled}"}
    else:
        return {"success": False, "message": "Failed to save enabled state"}


@app.get("/precision-landing/get-enabled-state")
@app.post("/precision-landing/get-enabled-state")
async def get_precision_landing_enabled_state() -> Dict[str, Any]:
    """Get saved precision landing enabled state (supports both GET and POST)"""
    logger.info("Getting precision landing enabled state")

    try:
        enabled = settings.get_precision_landing_enabled()
        return {
            "success": True,
            "enabled": enabled
        }
    except Exception as e:
        logger.exception(f"Error getting precision landing enabled state: {str(e)}")
        return {"success": False, "message": f"Error: {str(e)}", "enabled": False}


@app.post("/precision-landing/test")
async def test_precision_landing(type: str, rtsp: str) -> Dict[str, Any]:
    """Test precision landing functionality with RTSP connection"""
    logger.info(f"Testing precision landing with type={type}, rtsp={rtsp}")

    try:
        # Run the RTSP connection test in a thread to avoid blocking
        def run_test():
            return image_capture.test_rtsp_connection(rtsp, timeout_seconds=240)

        # Run the test in an executor to avoid blocking the async loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=240)  # 240 second total timeout (4 minutes)

        if result["success"]:
            logger.info(f"RTSP test successful for {type}: {result['message']}")
            # Add camera type to the response
            result["camera_type"] = type
            result["rtsp_url"] = rtsp
        else:
            logger.warning(f"RTSP test failed for {type}: {result['message']}")

        return result

    except concurrent.futures.TimeoutError:
        logger.error(f"RTSP test timed out for {type} camera")
        return {
            "success": False,
            "message": "Test timed out - unable to connect to camera within 240 seconds (4 minutes)",
            "error": "Connection timeout"
        }
    except Exception as e:
        logger.exception(f"Error during precision landing test: {str(e)}")
        return {"success": False, "message": f"Test failed2: {str(e)}"}


@app.post("/precision-landing/start")
async def start_precision_landing(type: str, rtsp: str) -> Dict[str, Any]:
    """Start precision landing"""
    global precision_landing_running

    logger.info(f"Start precision landing request received for type={type}, rtsp={rtsp}")

    try:
        if precision_landing_running:
            return {"success": False, "message": "Precision landing is already running"}

        # Start the precision landing process
        asyncio.create_task(start_precision_landing_internal(type, rtsp))

        return {
            "success": True,
            "message": f"Precision landing started successfully with {type} camera"
        }
    except Exception as e:
        logger.exception(f"Error starting precision landing: {str(e)}")
        return {"success": False, "message": f"Failed to start: {str(e)}"}


@app.post("/precision-landing/stop")
async def stop_precision_landing() -> Dict[str, Any]:
    """Stop precision landing"""
    global precision_landing_running, precision_landing_process

    logger.info("Stop precision landing request received")

    try:
        if not precision_landing_running:
            return {"success": False, "message": "Precision landing is not running"}

        # Stop the precision landing process
        precision_landing_running = False

        # If we had a process handle, we could terminate it here
        if precision_landing_process:
            precision_landing_process.terminate()
            precision_landing_process = None

        return {
            "success": True,
            "message": "Precision landing stopped successfully"
        }
    except Exception as e:
        logger.exception(f"Error stopping precision landing: {str(e)}")
        return {"success": False, "message": f"Failed to stop: {str(e)}"}


@app.get("/precision-landing/status")
@app.post("/precision-landing/status")
async def get_precision_landing_status() -> Dict[str, Any]:
    """Get precision landing status (supports both GET and POST)"""
    logger.debug("Getting precision landing status")

    try:
        return {
            "success": True,
            "running": precision_landing_running,
            "message": "Running" if precision_landing_running else "Stopped"
        }
    except Exception as e:
        logger.exception(f"Error getting precision landing status: {str(e)}")
        return {"success": False, "message": f"Error: {str(e)}", "running": False}


@app.post("/precision-landing/test-mavlink")
async def test_mavlink_connection() -> Dict[str, Any]:
    """Test MAV2Rest MAVLink connection"""
    logger.info("Testing MAV2Rest MAVLink connection")

    try:
        result = send_landing_target.test_mav2rest_connection()
        if result["success"]:
            logger.info("MAV2Rest connection test successful")
        else:
            logger.warning(f"MAV2Rest connection test failed: {result['message']}")
        return result
    except Exception as e:
        logger.exception(f"Error during MAV2Rest test: {str(e)}")
        return {"success": False, "message": f"MAV2Rest test failed: {str(e)}"}


# Initialize auto-restart task
@app.on_event("startup")
async def on_startup():
    """Application startup event handler"""
    await startup_auto_restart()


# Mount static files AFTER defining API routes
# Use absolute path to handle Docker container environment
static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# Set up logging for the app
log_dir = Path('/app/logs')
log_dir.mkdir(parents=True, exist_ok=True)
fh = logging.handlers.RotatingFileHandler(log_dir / 'lumber.log', maxBytes=2**16, backupCount=1)
logger.addHandler(fh)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
