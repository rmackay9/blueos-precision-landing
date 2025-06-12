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


# test RTSP connection using OpenCV with FFMPEG backend
# called from index.html's Test button
def test_rtsp_connection(rtsp_url: str, timeout_seconds: int = 240) -> Dict[str, Any]:
    """
    Test RTSP connection using SIYI SDK's proven approach with OpenCV FFmpeg backend.
    Based on the working implementation from https://github.com/mzahana/siyi_sdk
    Returns connection status and basic stream information.
    """
    logger.info(f"Testing RTSP connection to: {rtsp_url}")

    # Initialize video capture object
    cap = None

    try:
        # Log the attempt to connect
        logger.info("Attempting connection...")

        # Use FFMPEG backend for RTSP connection
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)

        # check if the capture is opened successfully
        logger.info("Checking connection...")

        if not cap.isOpened():
            logger.warning("Connection failed")
            return {
                "success": False,
                "message": f"Video capture failed with {rtsp_url}",
                "error": "Failed to open video capture"
            }

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Reduce buffer size for lower latency
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)  # Lower resolution to reduce data size
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 15)  # Lower FPS to reduce processing load

        logger.info(f"Video capture succeeded with {rtsp_url}")

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
                "message": f"Frame reading timed out after {timeout_seconds} seconds. Method: {rtsp_url}",
                "error": "Frame reading timeout"
            }

        # Check if frame reading was successful
        if frame_data["success"] and frame_data["frame"] is not None:
            height, width = frame_data["frame"].shape[:2]
            logger.info(f"Read frame succeeded: {width}x{height}")

            # Perform AprilTag detection and get encoded image
            april_tag_result = _detect_april_tags_and_encode_image(frame_data["frame"])
            detection_result = april_tag_result["detection_result"]
            image_base64 = april_tag_result["image_base64"]

            return {
                "success": True,
                "message": f"RTSP connection successful ({width}x{height}). Method: {rtsp_url}",
                "connection_method": rtsp_url,
                "resolution": f"{width}x{height}",
                "image_base64": image_base64,
                "april_tag_detection": detection_result
            }
        else:
            return {
                "success": False,
                "message": f"Connected but unable to read frames. Method: {rtsp_url}",
                "error": "No video data received"
            }

    except Exception as e:
        logger.exception(f"Exception during RTSP test: {str(e)}")
        return {
            "success": False,
            "message": f"Error testing RTSP connection: {str(e)}. Method: {rtsp_url}",
            "error": str(e)
        }
    finally:
        if cap is not None:
            cap.release()


# captures a single frame from an RTSP stream
def capture_frame_from_stream(rtsp_url: str, timeout_seconds: int = 30) -> Dict[str, Any]:
    """
    Capture a single frame from an RTSP stream.
    This is a simplified version focused on just getting one frame quickly.

    Args:
        rtsp_url: The RTSP URL to connect to
        timeout_seconds: Timeout for frame capture (currently unused in this simplified version)

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

            # Perform AprilTag detection and get encoded image
            april_tag_result = _detect_april_tags_and_encode_image(frame)
            detection_result = april_tag_result["detection_result"]
            image_base64 = april_tag_result["image_base64"]

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


# Helper function to detect AprilTags and encode image as base64
def _detect_april_tags_and_encode_image(frame) -> Dict[str, Any]:
    """
    Helper function to detect AprilTags and encode image as base64.
    Returns detection results and base64 encoded image.
    """
    # Get AprilTag family and target ID from settings
    apriltag_family = "tag36h11"  # default
    target_apriltag_id = -1  # default (detect any ID)

    if settings is not None:
        try:
            apriltag_family = settings.get_apriltag_family()
            target_apriltag_id = settings.get_apriltag_target_id()
        except Exception as e:
            logger.warning(f"Could not get AprilTag settings: {e}")

    # Perform AprilTag detection on the captured frame if available
    # Pass target_id directly to detection for efficiency (filter at detection time)
    if APRIL_TAGS_AVAILABLE and april_tags is not None:
        try:
            detection_result = april_tags.detect_april_tags(frame, tag_family=apriltag_family, target_id=target_apriltag_id)

        except Exception as e:
            logger.error(f"Error during AprilTag detection: {str(e)}")
            detection_result = {
                "success": False,
                "message": f"AprilTag detection error: {str(e)}",
                "detections": [],
                "augmented_image_base64": ""
            }
    else:
        logger.debug("AprilTag detection not available - using original image")
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
        # Encode original frame as base64
        _, buffer = cv2.imencode('.jpg', frame)
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        logger.info(f"AprilTag detection failed: {detection_result.get('message', 'Unknown error')}")

    return {
        "detection_result": detection_result,
        "image_base64": image_base64
    }
