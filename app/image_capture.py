#!/usr/bin/env python3

"""
Image Capture Module for Precision Landing

This module handles RTSP camera connection and frame capture functionality.

Methods include:

- `test_rtsp_connection`: Tests RTSP connection and captures a frame.


Based on the working implementation from https://github.com/mzahana/siyi_sdk
"""

import cv2
import base64
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


# test RTSP connection using OpenCV with FFMPEG backend
# called from index.html's Test button
def test_rtsp_connection(rtsp_url: str) -> Dict[str, Any]:
    """
    Test RTSP connection and capture a frame with AprilTag detection.
    Returns connection status and basic stream information.
    """
    logger.info(f"Testing RTSP connection to: {rtsp_url}")

    try:
        # capture single frame from RTSP stream
        frame_result = capture_frame_from_stream(rtsp_url)

        if not frame_result["success"]:
            return {
                "success": False,
                "message": f"RTSP connection failed: {frame_result['message']}",
                "error": frame_result.get("error", "Frame capture failed")
            }

        # Get frame data
        frame = frame_result["frame"]
        width = frame_result["width"]
        height = frame_result["height"]

        logger.info(f"Frame capture successful: {width}x{height}")

        # Perform AprilTag detection with default settings and include augmented image
        if APRIL_TAGS_AVAILABLE and april_tags is not None:
            result = april_tags.detect_april_tags(
                frame,
                tag_family="tag36h11",
                target_id=-1,
                include_augmented_image=True
            )
            detection_result = {"success": result["success"], "message": result["message"], "detections": [result["detection"]] if result["detection"] else []}
            image_base64 = result["image_base64"]
        else:
            # Encode original frame as base64 if AprilTags not available
            _, buffer = cv2.imencode('.jpg', frame)
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            detection_result = {
                "success": False,
                "message": "AprilTag detection module not available",
                "detections": []
            }

        return {
            "success": True,
            "message": f"RTSP connection successful ({width}x{height}). Method: {rtsp_url}",
            "connection_method": rtsp_url,
            "resolution": f"{width}x{height}",
            "image_base64": image_base64,
            "april_tag_detection": detection_result
        }

    except Exception as e:
        logger.exception(f"Exception during RTSP test: {str(e)}")
        return {
            "success": False,
            "message": f"Error testing RTSP connection: {str(e)}. Method: {rtsp_url}",
            "error": str(e)
        }


# captures a single frame from an RTSP stream
def capture_frame_from_stream(rtsp_url: str) -> Dict[str, Any]:
    """
    Capture a single frame from an RTSP stream.
    This is a simplified version focused on just getting one frame quickly.

    Args:
        rtsp_url: The RTSP URL to connect to

    Returns:
        Dictionary with success status and frame data (numpy array)
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

            return {
                "success": True,
                "message": f"Frame captured successfully ({width}x{height})",
                "frame": frame,
                "resolution": f"{width}x{height}",
                "width": width,
                "height": height
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
