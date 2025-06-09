#!/usr/bin/env python3

"""
AprilTag Detection Module for Precision Landing

This module handles AprilTag detection in images and provides
augmented images with detection visualizations.
"""

import cv2
import numpy as np
import logging
from typing import Dict, List, Tuple, Any, Optional
import base64

# Get logger
logger = logging.getLogger("precision-landing")

try:
    import apriltag
    APRILTAG_AVAILABLE = True
    logger.info("AprilTag library loaded successfully")
except Exception as e:
    APRILTAG_AVAILABLE = False
    logger.warning(f"AprilTag library not available: {str(e)}. Please install with: pip install apriltag")


class AprilTagDetector:
    """AprilTag detector class for precision landing"""

    def __init__(self, tag_family: str = "tag36h11"):
        """
        Initialize the AprilTag detector

        Args:
            tag_family: AprilTag family to detect (tag36h11, tag25h9, tag16h5, tagCircle21h7, tagStandard41h12)
        """
        self.tag_family = tag_family
        self.detector = None

        if APRILTAG_AVAILABLE:
            try:
                # Create detector with optimized options for precision landing
                options = apriltag.DetectorOptions(
                    families=tag_family,
                    border=1,
                    nthreads=4,
                    quad_decimate=1.0,
                    quad_blur=0.0,
                    refine_edges=True,
                    refine_decode=False,
                    refine_pose=False,
                    debug=False,
                    quad_contours=True
                )
                self.detector = apriltag.Detector(options)
                logger.info(f"AprilTag detector initialized with family: {tag_family}")
            except Exception as e:
                logger.error(f"Failed to initialize AprilTag detector: {str(e)}")
                self.detector = None
        else:
            logger.error("Cannot initialize AprilTag detector - library not available")


def detect_april_tags(image: np.ndarray, tag_family: str = "tag36h11") -> Dict[str, Any]:
    """
    Detect AprilTags in an image and return augmented image with detection data

    Args:
        image: Input image as numpy array (BGR format from OpenCV)
        tag_family: AprilTag family to detect

    Returns:
        Dictionary containing:
        - success: bool indicating if detection was successful
        - augmented_image: Image with red boxes drawn around detected tags
        - augmented_image_base64: Base64 encoded augmented image
        - detections: List of detected tag information
        - message: Status message
    """
    logger.info("Starting AprilTag detection")

    if not APRILTAG_AVAILABLE:
        return {
            "success": False,
            "message": "AprilTag library not available. Please install with: pip install apriltag",
            "detections": [],
            "augmented_image_base64": ""
        }

    try:
        # Create detector
        detector = AprilTagDetector(tag_family)
        if detector.detector is None:
            return {
                "success": False,
                "message": "Failed to initialize AprilTag detector",
                "detections": [],
                "augmented_image_base64": ""
            }

        # Convert to grayscale for detection
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Detect AprilTags
        detections = detector.detector.detect(gray)

        # Create augmented image (copy original)
        augmented_image = image.copy()

        # Process detections
        detection_data = []

        for detection in detections:
            # Get tag information
            tag_id = detection.tag_id
            center = detection.center
            corners = detection.corners

            # Calculate relative size (diagonal length of bounding box)
            corner_array = np.array(corners)
            width = np.max(corner_array[:, 0]) - np.min(corner_array[:, 0])
            height = np.max(corner_array[:, 1]) - np.min(corner_array[:, 1])
            diagonal = np.sqrt(width**2 + height**2)

            # Normalize diagonal by image diagonal for relative size
            image_diagonal = np.sqrt(image.shape[1]**2 + image.shape[0]**2)
            relative_size = diagonal / image_diagonal

            # Store detection data
            detection_info = {
                "tag_id": int(tag_id),
                "center_x": float(center[0]),
                "center_y": float(center[1]),
                "corners": [[float(corner[0]), float(corner[1])] for corner in corners],
                "width": float(width),
                "height": float(height),
                "diagonal": float(diagonal),
                "relative_size": float(relative_size),
                "confidence": float(detection.decision_margin) if hasattr(detection, 'decision_margin') else 1.0
            }
            detection_data.append(detection_info)

            # Draw red box around the tag
            corners_int = corners.astype(int)
            cv2.polylines(augmented_image, [corners_int], True, (0, 0, 255), 3)  # Red color in BGR

            # Draw center point
            center_int = (int(center[0]), int(center[1]))
            cv2.circle(augmented_image, center_int, 5, (0, 0, 255), -1)

            # Draw tag ID text
            text_position = (int(center[0] - 20), int(center[1] - 20))
            cv2.putText(augmented_image, f"ID:{tag_id}", text_position,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            # Draw size information
            size_text = f"Size:{relative_size:.3f}"
            size_position = (int(center[0] - 30), int(center[1] + 30))
            cv2.putText(augmented_image, size_text, size_position,
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

        # Encode augmented image as base64
        _, buffer = cv2.imencode('.jpg', augmented_image)
        augmented_image_base64 = base64.b64encode(buffer).decode('utf-8')

        logger.info(f"AprilTag detection completed. Found {len(detection_data)} tags")

        return {
            "success": True,
            "message": f"Detected {len(detection_data)} AprilTag(s)",
            "detections": detection_data,
            "augmented_image_base64": augmented_image_base64
        }

    except Exception as e:
        logger.exception(f"Error during AprilTag detection: {str(e)}")
        return {
            "success": False,
            "message": f"AprilTag detection failed: {str(e)}",
            "detections": [],
            "augmented_image_base64": ""
        }


def detect_april_tags_from_base64(image_base64: str, tag_family: str = "tag36h11") -> Dict[str, Any]:
    """
    Detect AprilTags from a base64 encoded image

    Args:
        image_base64: Base64 encoded image string
        tag_family: AprilTag family to detect

    Returns:
        Dictionary containing detection results (same as detect_april_tags)
    """
    try:
        # Decode base64 image
        image_data = base64.b64decode(image_base64)
        nparr = np.frombuffer(image_data, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            return {
                "success": False,
                "message": "Failed to decode base64 image",
                "detections": [],
                "augmented_image_base64": ""
            }

        # Perform detection
        return detect_april_tags(image, tag_family)

    except Exception as e:
        logger.exception(f"Error processing base64 image: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to process base64 image: {str(e)}",
            "detections": [],
            "augmented_image_base64": ""
        }


def get_largest_april_tag(detections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Get the largest AprilTag from a list of detections

    Args:
        detections: List of detection dictionaries

    Returns:
        Dictionary of the largest tag detection, or None if no detections
    """
    if not detections:
        return None

    # Find the tag with the largest relative size
    largest_tag = max(detections, key=lambda x: x.get("relative_size", 0))
    return largest_tag


def calculate_landing_offset(detection: Dict[str, Any], image_width: int, image_height: int) -> Dict[str, float]:
    """
    Calculate landing offset from image center to AprilTag center

    Args:
        detection: AprilTag detection dictionary
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels

    Returns:
        Dictionary with offset information:
        - offset_x: Horizontal offset (-1 to 1, negative = left, positive = right)
        - offset_y: Vertical offset (-1 to 1, negative = up, positive = down)
        - distance_pixels: Distance from center in pixels
        - distance_normalized: Distance from center normalized (0 to 1)
    """
    # Get image center
    image_center_x = image_width / 2
    image_center_y = image_height / 2

    # Get tag center
    tag_center_x = detection["center_x"]
    tag_center_y = detection["center_y"]

    # Calculate offsets (normalized to -1 to 1)
    offset_x = (tag_center_x - image_center_x) / (image_width / 2)
    offset_y = (tag_center_y - image_center_y) / (image_height / 2)

    # Calculate distance
    distance_pixels = np.sqrt((tag_center_x - image_center_x)**2 + (tag_center_y - image_center_y)**2)
    max_distance = np.sqrt((image_width/2)**2 + (image_height/2)**2)
    distance_normalized = distance_pixels / max_distance

    return {
        "offset_x": float(offset_x),
        "offset_y": float(offset_y),
        "distance_pixels": float(distance_pixels),
        "distance_normalized": float(distance_normalized)
    }


def is_apriltag_available() -> bool:
    """
    Check if AprilTag library is available

    Returns:
        True if AprilTag library is available, False otherwise
    """
    return APRILTAG_AVAILABLE


def get_supported_tag_families() -> List[str]:
    """
    Get list of supported AprilTag families

    Returns:
        List of supported tag family names
    """
    return ["tag36h11", "tag25h9", "tag16h5", "tagCircle21h7", "tagStandard41h12"]
