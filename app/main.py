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
import cv2
import threading
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from typing import Dict, Any
from pydantic import BaseModel

# Import the settings module
from app import settings

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

# RTSP connection test function using SIYI SDK's proven approach
def test_rtsp_connection(rtsp_url: str, timeout_seconds: int = 10) -> Dict[str, Any]:
    """
    Test RTSP connection using SIYI SDK's proven approach with OpenCV FFmpeg backend.
    Based on the working implementation from https://github.com/mzahana/siyi_sdk
    Returns connection status and basic stream information.
    """
    logger.info(f"Testing RTSP connection to: {rtsp_url}")

    # Log system information for debugging
    import sys
    logger.info(f"Python version: {sys.version}")

    # Try to get GStreamer version
    try:
        import subprocess
        result = subprocess.run(['gst-launch-1.0', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            gst_version = result.stdout.split('\n')[0]
            logger.info(f"GStreamer version: {gst_version}")
        else:
            logger.info("GStreamer version: Could not determine (gst-launch-1.0 failed)")
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.info(f"GStreamer version: Could not determine ({str(e)})")

    cap = None
    rtsp_url_extended = ""

    try:
        # Log the attempt to connect
        logger.info("Attempting connection...")

        # non-working GStreamer pipeline below
        #rtsp_url_extended = (
        #    f"rtspsrc location={rtsp_url} latency=100 ! "
        #    "rtph264depay ! h264parse ! avdec_h264 ! videoconvert ! appsink"
        #)
        # cap = cv2.VideoCapture(rtsp_url_extended, cv2.CAP_GSTREAMER)

        # partially working FFMPEG pipeline (connects but no frames read)
        #rtsp_url_extended = rtsp_url
        #cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

        # partially working GStreamer pipeline (connects but no frames read)
        rtsp_url_extended = f"rtspsrc location={rtsp_url} latency=41 udp-reconnect=1 timeout=0 do-retransmission=false ! application/x-rtp ! decodebin3 ! queue max-size-buffers=1 leaky=2 ! videoconvert ! video/x-raw,format=BGRA ! appsink"
        cap = cv2.VideoCapture(rtsp_url_extended, cv2.CAP_GSTREAMER)

        # Apply SIYI SDK's proven settings
        #cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer size for lower latency
        #cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Lower resolution to reduce data size
        #cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        #cap.set(cv2.CAP_PROP_FPS, 15)  # Lower FPS to reduce processing load

        if not cap.isOpened():
            logger.warning("Connection failed")
            return {
                "success": False,
                "message": f"Video capture failed with {rtsp_url_extended}",
                "error": "Failed to open video capture"
            }

        logger.info(f"Video capture succeeded with {rtsp_url_extended}")

        # Test frame reading with timeout mechanism (similar to SIYI SDK)
        start_time = time.time()
        frame_read_success = False

        # Try to read frames for up to timeout_seconds
        while (time.time() - start_time) < timeout_seconds and not frame_read_success:
            ret, frame = cap.read()

            if ret and frame is not None:
                frame_read_success = True
                height, width = frame.shape[:2]
                logger.info(f"Read frame succeeded: {width}x{height}")

                return {
                    "success": True,
                    "message": f"RTSP connection successful ({width}x{height}). Method: {rtsp_url_extended}",
                    "connection_method": rtsp_url_extended,
                    "resolution": f"{width}x{height}"
                }
            else:
                logger.debug(f"Read frame failed (ret={ret}), retrying...")
                time.sleep(0.001)  # Brief pause before retry

        # If we get here, frame reading failed
        return {
            "success": False,
            "message": f"Connected but unable to read frames after {timeout_seconds} seconds. Method: {rtsp_url_extended}",
            "error": "No video data received"
        }

    except Exception as e:
        logger.exception(f"Exception during RTSP test: {str(e)}")
        return {
            "success": False,
            "message": f"Error testing RTSP connection: {str(e)}. Method: {rtsp_url_extended}",
            "error": str(e)
        }
    finally:
        if cap is not None:
            cap.release()


# Global variable to track precision landing running state
# In a real implementation, this might be a more sophisticated state management system
precision_landing_running = False
precision_landing_process = None

# Pydantic models for request bodies
class EnabledState(BaseModel):
    enabled: bool

logger.info("Precision Landing backend started")


# Internal function to start precision landing
async def start_precision_landing_internal():
    """Internal function to start the precision landing process"""
    global precision_landing_running, precision_landing_process

    try:
        logger.info("Starting precision landing process")
        precision_landing_running = True

        # TODO: Implement actual precision landing logic here
        # This would include:
        # - Connecting to the RTSP stream
        # - Processing video frames for AprilTag detection
        # - Sending MAVLink messages to the vehicle

        # For now, this is a placeholder that just runs indefinitely
        while precision_landing_running:
            logger.debug("Precision landing running...")
            await asyncio.sleep(5)  # Simulate work

    except Exception as e:
        logger.error(f"Error in precision landing process: {str(e)}")
        precision_landing_running = False


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
async def save_precision_landing_settings(type: str, rtsp: str) -> Dict[str, Any]:
    """Save camera settings to persistent storage (using query parameters)"""
    logger.info(f"Saving precision landing settings: type={type}, rtsp_url={rtsp}")
    success = settings.update_camera_rtsp(type, rtsp)

    if success:
        return {"success": True, "message": f"Settings saved for {type}"}
    else:
        return {"success": False, "message": "Failed to save settings"}


@app.post("/precision-landing/get-settings")
async def get_precision_landing_settings() -> Dict[str, Any]:
    """Get saved camera settings"""
    logger.info("Getting precision landing settings")

    try:
        # Get the last used camera settings
        last_used = settings.get_last_used()

        # Get RTSP URLs for all camera types
        cameras = {}
        for camera_type in ["siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb"]:
            rtsp_url = settings.get_camera_rtsp(camera_type)
            cameras[camera_type] = {"rtsp_url": rtsp_url}

        return {
            "success": True,
            "last_used": last_used,
            "cameras": cameras
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
            return test_rtsp_connection(rtsp, timeout_seconds=60)

        # Run the test in an executor to avoid blocking the async loop
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_test)
            result = future.result(timeout=60)  # 60 second total timeout

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
        asyncio.create_task(start_precision_landing_internal())

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
