#!/usr/bin/env python3

"""
Image Capture Module for Precision Landing

This module handles RTSP camera connection and frame capture functionality.
Based on the working implementation from https://github.com/mzahana/siyi_sdk
"""

import cv2
import base64
import threading
import logging
from typing import Dict, Any

# Get logger
logger = logging.getLogger("precision-landing")

# Import AprilTag detection module with error handling
try:
    from app import april_tags
    APRIL_TAGS_AVAILABLE = True
    logger.info("AprilTag detection module imported successfully")
except ImportError as e:
    logger.warning(f"AprilTag detection module not available: {str(e)}")
    APRIL_TAGS_AVAILABLE = False
    april_tags = None

# Import settings module
try:
    from app import settings
    logger.info("Settings module imported successfully")
except ImportError as e:
    logger.warning(f"Settings module not available: {str(e)}")
    settings = None


def test_rtsp_connection(rtsp_url: str, timeout_seconds: int = 240) -> Dict[str, Any]:
    """
    Test RTSP connection using SIYI SDK's proven approach with OpenCV FFmpeg backend.
    Based on the working implementation from https://github.com/mzahana/siyi_sdk
    Returns connection status and basic stream information.
    """
    logger.info(f"Testing RTSP connection to: {rtsp_url}")

    # Log system information for debugging
    import sys
    logger.info(f"Python version: {sys.version}")

    # Log OpenCV version and build information
    logger.info(f"OpenCV version: {cv2.__version__}")
    build_info = cv2.getBuildInformation()

    # Extract key build information
    for line in build_info.split('\n'):
        line = line.strip()
        if 'Video I/O:' in line or 'FFMPEG:' in line or 'GStreamer:' in line:
            logger.info(f"OpenCV build info: {line}")
        elif line.startswith('FFMPEG:') or line.startswith('GStreamer:'):
            logger.info(f"OpenCV build info: {line}")

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

        # non-working GStreamer pipeline (connects but no frames read)
        #rtsp_url_extended = f"rtspsrc location={rtsp_url} latency=41 udp-reconnect=1 timeout=0 do-retransmission=false ! application/x-rtp ! decodebin3 ! queue max-size-buffers=1 leaky=2 ! videoconvert ! video/x-raw,format=BGRA ! appsink"
        #cap = cv2.VideoCapture(rtsp_url_extended, cv2.CAP_GSTREAMER)

        # partially working FFMPEG pipeline (connects but no frames read)
        rtsp_url_extended = rtsp_url
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

        # check if the capture is opened successfully
        logger.info("Checking connection...")

        if not cap.isOpened():
            logger.warning("Connection failed")
            return {
                "success": False,
                "message": f"Video capture failed with {rtsp_url_extended}",
                "error": "Failed to open video capture"
            }

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer size for lower latency
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Lower resolution to reduce data size
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)  # Lower FPS to reduce processing load

        logger.info(f"Video capture succeeded with {rtsp_url_extended}")

        # Test frame reading with separate thread (similar to SIYI SDK)
        frame_data = {"frame": None, "ret": False, "success": False}

        def read_frame_thread():
            """Thread function to read frames from the video capture"""
            try:
                logger.debug("Frame reading thread started")
                ret, frame = cap.read()
                frame_data["ret"] = ret
                frame_data["frame"] = frame
                if ret and frame is not None:
                    frame_data["success"] = True
                    logger.debug("Frame read successful in thread")
                else:
                    logger.debug(f"Frame read failed in thread: ret={ret}")
            except Exception as e:
                logger.error(f"Exception in frame reading thread: {str(e)}")

        # Start frame reading in a separate thread
        frame_thread = threading.Thread(target=read_frame_thread)
        frame_thread.daemon = True
        frame_thread.start()

        # Wait for the thread to complete with timeout
        frame_thread.join(timeout=timeout_seconds)

        if frame_thread.is_alive():
            logger.warning("Frame reading thread timed out")
            return {
                "success": False,
                "message": f"Frame reading timed out after {timeout_seconds} seconds. Method: {rtsp_url_extended}",
                "error": "Frame reading timeout"
            }

        # Check if frame reading was successful
        if frame_data["success"] and frame_data["frame"] is not None:
            height, width = frame_data["frame"].shape[:2]
            logger.info(f"Read frame succeeded: {width}x{height}")

            # Perform AprilTag detection on the captured frame if available
            if APRIL_TAGS_AVAILABLE and april_tags is not None:
                try:
                    # Get AprilTag family from settings
                    apriltag_family = "tag36h11"  # default
                    if settings is not None:
                        try:
                            apriltag_family = settings.get_apriltag_family()
                        except Exception as e:
                            logger.warning(f"Could not get AprilTag family from settings: {e}")

                    detection_result = april_tags.detect_april_tags(image = frame_data["frame"], tag_family=apriltag_family)

                    # Apply AprilTag ID filtering if detection was successful
                    if detection_result.get("success") and settings is not None:
                        try:
                            target_apriltag_id = settings.get_apriltag_target_id()
                            detection_result = april_tags.filter_april_tag_detection_result(detection_result, target_apriltag_id)
                        except Exception as e:
                            logger.warning(f"Could not apply AprilTag ID filtering: {e}")

                except Exception as e:
                    logger.error(f"Error during AprilTag detection: {str(e)}")
                    detection_result = {
                        "success": False,
                        "message": f"AprilTag detection error: {str(e)}",
                        "detections": [],
                        "augmented_image_base64": ""
                    }
            else:
                logger.info("AprilTag detection not available - showing original image")
                detection_result = {
                    "success": False,
                    "message": "AprilTag detection module not available",
                    "detections": [],
                    "augmented_image_base64": ""
                }

            # Use augmented image if AprilTag detection was successful, otherwise use original
            if detection_result["success"] and detection_result.get("augmented_image_base64"):
                image_base64 = detection_result["augmented_image_base64"]
                logger.info(f"AprilTag detection: {detection_result['message']}")
            else:
                # Encode frame as base64 for web display
                _, buffer = cv2.imencode('.jpg', frame_data["frame"])
                image_base64 = base64.b64encode(buffer).decode('utf-8')
                logger.info(f"AprilTag detection failed: {detection_result.get('message', 'Unknown error')}")

            return {
                "success": True,
                "message": f"RTSP connection successful ({width}x{height}). Method: {rtsp_url_extended}",
                "connection_method": rtsp_url_extended,
                "resolution": f"{width}x{height}",
                "image_base64": image_base64,
                "april_tag_detection": detection_result
            }
        else:
            return {
                "success": False,
                "message": f"Connected but unable to read frames. Method: {rtsp_url_extended}",
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


def capture_frame_from_stream(rtsp_url: str, timeout_seconds: int = 30) -> Dict[str, Any]:
    """
    Capture a single frame from an RTSP stream.
    This is a simplified version focused on just getting one frame quickly.

    Args:
        rtsp_url: The RTSP URL to connect to
        timeout_seconds: Timeout for frame capture

    Returns:
        Dictionary with success status and frame data
    """
    logger.info(f"Capturing frame from: {rtsp_url}")

    cap = None
    try:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        if not cap.isOpened():
            return {
                "success": False,
                "message": "Failed to open video stream",
                "error": "Video capture failed"
            }

        # Try to read a frame
        ret, frame = cap.read()

        if ret and frame is not None:
            height, width = frame.shape[:2]

            # Get AprilTag family from settings
            apriltag_family = "tag36h11"  # default
            if settings is not None:
                try:
                    apriltag_family = settings.get_apriltag_family()
                except Exception as e:
                    logger.warning(f"Could not get AprilTag family from settings: {e}")

            # Perform AprilTag detection on the captured frame
            detection_result = april_tags.detect_april_tags(frame, tag_family=apriltag_family)

            # Apply AprilTag ID filtering if detection was successful
            if detection_result.get("success") and settings is not None:
                try:
                    target_apriltag_id = settings.get_apriltag_target_id()
                    detection_result = april_tags.filter_april_tag_detection_result(detection_result, target_apriltag_id)
                except Exception as e:
                    logger.warning(f"Could not apply AprilTag ID filtering: {e}")

            # Use augmented image if AprilTag detection was successful, otherwise use original
            if detection_result["success"] and detection_result.get("augmented_image_base64"):
                # Encode augmented frame as base64
                image_base64 = detection_result["augmented_image_base64"]
                logger.info(f"AprilTag detection: {detection_result['message']}")
            else:
                # Encode original frame as base64
                _, buffer = cv2.imencode('.jpg', frame)
                image_base64 = base64.b64encode(buffer).decode('utf-8')
                logger.info(f"AprilTag detection failed: {detection_result.get('message', 'Unknown error')}")

            return {
                "success": True,
                "message": f"Frame captured successfully ({width}x{height})",
                "resolution": f"{width}x{height}",
                "image_base64": image_base64,
                "april_tag_detection": detection_result
            }
        else:
            return {
                "success": False,
                "message": "Unable to read frame from stream",
                "error": "Frame read failed"
            }

    except Exception as e:
        logger.exception(f"Exception during frame capture: {str(e)}")
        return {
            "success": False,
            "message": f"Error capturing frame: {str(e)}",
            "error": str(e)
        }
    finally:
        if cap is not None:
            cap.release()
