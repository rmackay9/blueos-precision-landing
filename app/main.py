#!/usr/bin/env python3

# Precision Landing Python backend
# Implements these features required by the index.html frontend:
# - Save camera settings including type and RTSP URL
# - Get camera settings including last used settings
# - Save/get precision landing enabled state (persistent across restarts)
# - "Test" button to view the live video and capture the april tag location
# - "Run" button to enable the precision landing including sending MAVLink messages to the vehicle
# - Status endpoint to check if precision landing is currently running

import logging.handlers
import sys
import asyncio
from math import tan, atan, radians, degrees
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from typing import Dict, Any

# Import the local modules
from app import settings
from app import image_capture
from app import send_landing_target
from app import april_tags

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
precision_landing_running = False

logger.info("Precision Landing backend started")


# Auto-start precision landing if it was previously enabled
async def startup_auto_restart():
    """Check if precision landing was previously enabled and auto-restart if needed"""
    try:
        enabled = settings.get_precision_landing_enabled()
        if enabled:
            logger.info("Auto-restarting precision landing as it was previously enabled")
            # Get last used settings for auto-restart
            last_used = settings.get_last_used()
            camera_type = last_used.get("camera_type", "siyi-a8")
            rtsp_url = last_used.get("rtsp", "rtsp://192.168.144.25:8554/main.264")
            # Don't await this so startup doesn't block
            asyncio.create_task(start_precision_landing_internal(camera_type, rtsp_url))
    except Exception as e:
        logger.error(f"Error during auto-restart check: {str(e)}")


# Internal function to start precision landing
async def start_precision_landing_internal(camera_type: str, rtsp_url: str):
    """Internal function to start the precision landing process"""
    global precision_landing_running

    try:
        logger.info("Starting precision landing process")
        precision_landing_running = True

        logger.info(f"Precision landing using camera: {camera_type}, RTSP: {rtsp_url}")

        # Get camera FOV setting
        camera_hfov = settings.get_camera_horizontal_fov(camera_type)
        logger.info(f"Using horizontal FOV: {camera_hfov}° for camera type: {camera_type}")

        # Get MAVLink target system ID from settings
        target_system_id = settings.get_mavlink_sysid()

        # Test MAV2Rest connection by sending a test LANDING_TARGET message
        logger.info(f"Testing MAV2Rest connection with SysID {target_system_id}")
        mav_test = send_landing_target.send_landing_target_msg(
            angle_x=0.0,
            angle_y=0.0,
            distance=0.0,
            size_x=0.0,
            size_y=0.0,
            target_num=0,
            sysid=target_system_id
        )
        if not mav_test["success"]:
            logger.error(f"MAV2Rest connection test failed: {mav_test['message']}")
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

        while precision_landing_running:
            try:
                # Capture frame from RTSP stream
                frame_result = image_capture.capture_frame_from_stream(rtsp_url)

                if not frame_result["success"]:
                    logger.warning(f"Failed to capture frame: {frame_result['message']}")
                    await asyncio.sleep(1)  # Wait before retrying
                    continue

                frame_count += 1

                # Get the captured frame
                frame = frame_result["frame"]
                width = frame_result["width"]
                height = frame_result["height"]

                # calculate hfov
                camera_vfov = calculate_vertical_fov(camera_hfov, width, height)

                # Perform AprilTag detection (returns single detection with lowest ID)
                april_tag_result = april_tags.detect_april_tags(
                    frame,
                    tag_family=settings.get_apriltag_family(),
                    target_id=target_apriltag_id,
                    include_augmented_image=False  # Don't need augmented image for precision landing
                )

                if april_tag_result.get("success") and april_tag_result.get("detection"):
                    # Get the single detected tag (lowest ID)
                    detected_tag = april_tag_result["detection"]

                    # Send LANDING_TARGET message
                    send_result = send_landing_target.send_landing_target(
                        detected_tag["tag_id"],
                        detected_tag["center_x"],
                        detected_tag["center_y"],
                        detected_tag["width"],
                        detected_tag["height"],
                        width,
                        height,
                        camera_hfov,
                        camera_vfov,
                        sysid=target_system_id
                    )

                    if send_result["success"]:
                        logger.info(f"Frame {frame_count}: Sent LANDING_TARGET for AprilTag ID {detected_tag['tag_id']} "
                                    f"(angle_x={send_result['angles']['angle_x_deg']:.2f}°, "
                                    f"angle_y={send_result['angles']['angle_y_deg']:.2f}°)")
                    else:
                        logger.warning(f"Failed to send LANDING_TARGET: {send_result['message']}")
                else:
                    # No AprilTag detected or none matched target ID
                    if frame_count % 10 == 0:  # Log every 10 frames
                        if target_apriltag_id == -1:
                            logger.debug(f"Frame {frame_count}: No AprilTag detected")
                        else:
                            logger.debug(f"Frame {frame_count}: No AprilTag detected with target ID {target_apriltag_id}")

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


# helper function to calculate the vertical FOV based on the horizontal FOV, image width, and height (in pixels)
def calculate_vertical_fov(hfov_deg: float, width: int, height: int) -> float:
    """Calculate vertical FOV based on horizontal FOV, image width, and height
       tan(vfov/2) = tan(hfov/2) * (height/width)
    """

    # Validate inputs to prevent mathematical errors
    if width <= 0:
        logger.error(f"Invalid image width: {width}")
        return 0.0

    if height <= 0:
        logger.error(f"Invalid image height: {height}")
        return 0.0

    if hfov_deg <= 0 or hfov_deg >= 180:
        logger.error(f"Invalid horizontal FOV: {hfov_deg}° (must be between 0 and 180)")
        return 0.0

    try:
        # Convert horizontal FOV from degrees to radians
        hfov_rad = radians(hfov_deg)

        # Calculate aspect ratio
        aspect_ratio = height / width

        # Use trigonometric relationship to calculate vertical FOV
        vfov_rad = 2 * atan(tan(hfov_rad / 2) * aspect_ratio)

        # Convert back to degrees
        vfov_deg = degrees(vfov_rad)

        # Sanity check result
        if vfov_deg <= 0 or vfov_deg >= 180:
            logger.error(f"Calculated invalid vertical FOV: {vfov_deg}°")
            return 0.0

        return vfov_deg
    except (ValueError, OverflowError) as e:
        logger.error(f"Mathematical error in vertical FOV calculation: {e}")
        return 0.0

# Precision Landing API Endpoints

# Load precision landing settings
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
            "flight_controller_sysid": settings.get_mavlink_sysid()
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


# Save precision landing settings
@app.post("/precision-landing/save-settings")
async def save_precision_landing_settings(
    type: str,
    rtsp: str,
    fov: float,
    apriltag_family: str,
    tag_id: int,
    flight_controller_sysid: int  # Keep this for HTML compatibility
) -> Dict[str, Any]:
    """Save camera settings and other precision landing settings to persistent storage (using query parameters)"""
    # Map flight_controller_sysid to sysid for internal use
    sysid = flight_controller_sysid
    logger.info(f"Saving precision landing settings: type={type}, rtsp_url={rtsp}, fov={fov}, "
                f"apriltag_family={apriltag_family}, tag_id={tag_id}, sysid={sysid}")

    # Save camera settings
    camera_success = settings.update_camera_settings(type, rtsp, fov)

    # Save AprilTag settings
    apriltag_success = settings.update_apriltag_settings(apriltag_family, tag_id)

    # Save MAVLink settings
    mavlink_success = settings.update_mavlink_sysid(sysid)

    if camera_success and apriltag_success and mavlink_success:
        return {"success": True, "message": f"Settings saved for {type}"}
    else:
        return {"success": False, "message": "Failed to save some settings"}


# Get precision landing enabled state
@app.get("/precision-landing/get-enabled-state")
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


# Save precision landing enabled state
@app.post("/precision-landing/save-enabled-state")
async def save_precision_landing_enabled_state(enabled: bool) -> Dict[str, Any]:
    """Save precision landing enabled state to persistent storage (using query parameter)"""
    logger.info(f"Saving precision landing enabled state: {enabled}")
    success = settings.update_precision_landing_enabled(enabled)

    if success:
        return {"success": True, "message": f"Enabled state saved: {enabled}"}
    else:
        return {"success": False, "message": "Failed to save enabled state"}


# Test image retrieval from the RTSP stream and AprilTag detection
@app.post("/precision-landing/test")
async def test_precision_landing(type: str, rtsp: str) -> Dict[str, Any]:
    """Test precision landing functionality with RTSP connection"""
    logger.info(f"Testing precision landing with type={type}, rtsp={rtsp}")

    try:
        # Run the RTSP connection test in a thread to avoid blocking
        def run_test():
            return image_capture.test_rtsp_connection(rtsp)

        # Run the test in an executor to avoid blocking the async loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)  # 60 second timeout should be sufficient

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
            "message": "Test timed out - unable to connect to camera within 60 seconds",
            "error": "Connection timeout"
        }
    except Exception as e:
        logger.exception(f"Error during precision landing test: {str(e)}")
        return {"success": False, "message": f"Test failed: {str(e)}"}


# Get precision landing running status
@app.get("/precision-landing/status")
async def get_precision_landing_status() -> Dict[str, Any]:
    """Get precision landing running status"""
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


# Start precision landing (this is called by the frontend's "Run" button)
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


# Stop precision landing (this is called by the frontend's "Stop" button)
@app.post("/precision-landing/stop")
async def stop_precision_landing() -> Dict[str, Any]:
    """Stop precision landing"""
    global precision_landing_running

    logger.info("Stop precision landing request received")

    try:
        if not precision_landing_running:
            return {"success": False, "message": "Precision landing is not running"}

        # Stop the precision landing process
        precision_landing_running = False

        return {
            "success": True,
            "message": "Precision landing stopped successfully"
        }
    except Exception as e:
        logger.exception(f"Error stopping precision landing: {str(e)}")
        return {"success": False, "message": f"Failed to stop: {str(e)}"}


# Test MAV2Rest MAVLink connection
@app.post("/precision-landing/test-mavlink")
async def test_mavlink_connection() -> Dict[str, Any]:
    """Test MAV2Rest MAVLink connection"""
    try:
        target_system_id = settings.get_mavlink_sysid()
        result = send_landing_target.send_landing_target_msg(
            angle_x=0.0,
            angle_y=0.0,
            distance=0.0,
            size_x=0.0,
            size_y=0.0,
            target_num=0,
            sysid=target_system_id
        )
        if result["success"]:
            logger.info("MAV2Rest connection test successful")
            return {
                "success": True,
                "message": f"MAV2Rest API connection successful, test LANDING_TARGET sent to SysID {target_system_id}",
                "endpoint": send_landing_target.MAV2REST_ENDPOINT
            }
        else:
            logger.warning(f"MAV2Rest connection test failed: {result['message']}")
            return {
                "success": False,
                "message": f"MAV2Rest connected but test message failed: {result['message']}",
                "endpoint": send_landing_target.MAV2REST_ENDPOINT
            }
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
