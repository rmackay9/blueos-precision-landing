#!/usr/bin/env python3

"""
Landing Target MAVLink Message Module for Precision Landing

This module handles sending LANDING_TARGET MAVLink messages to the vehicle
via BlueOS MAV2Rest API interface.
"""

import requests
import time
import logging
from typing import Dict, Any, Optional
import urllib.request

# Get logger
logger = logging.getLogger("precision-landing")

# MAV2Rest endpoint (fixed for BlueOS Docker environment)
MAV2REST_ENDPOINT = "http://host.docker.internal:6040"

# MAVLink constants (only the ones we actually use)
MAV_FRAME_BODY_FRD = 12
LANDING_TARGET_TYPE_VISION_FIDUCIAL = 2

# LANDING_TARGET message template (based on working BlueOS pattern)
LANDING_TARGET_TEMPLATE = """{{
  "header": {{
    "system_id": 255,
    "component_id": 0,
    "sequence": 0
  }},
  "message": {{
    "type": "LANDING_TARGET",
    "time_usec": {time_usec},
    "target_num": {target_num},
    "frame": {{
      "type": "MAV_FRAME_{frame_name}"
    }},
    "angle_x": {angle_x},
    "angle_y": {angle_y},
    "distance": {distance},
    "size_x": {size_x},
    "size_y": {size_y},
    "x": {x},
    "y": {y},
    "z": {z},
    "q": [
      {q0},
      {q1},
      {q2},
      {q3}
    ],
    "position_type": {{
      "type": "LANDING_TARGET_TYPE_{position_type_name}"
    }}
  }}
}}"""


def post_to_mav2rest(url: str, data: str) -> Optional[str]:
    """
    Sends a POST request to MAV2Rest with JSON data
    Returns response text if successful, None otherwise
    """
    try:
        jsondata = data.encode("ascii")  # data should be bytes
        req = urllib.request.Request(url, jsondata)
        req.add_header("Content-Type", "application/json")

        with urllib.request.urlopen(req, timeout=5) as response:
            return response.read().decode()
    except Exception as error:
        logger.warning(f"Error in MAV2Rest POST: {url}: {error}")
        return None


def test_mav2rest_connection() -> Dict[str, Any]:
    """Class to handle sending LANDING_TARGET MAVLink messages"""

    def __init__(self, mav2rest_endpoint: str = MAV2REST_ENDPOINT, target_system: int = 1):
        """
        Initialize the landing target sender

        Args:
            mav2rest_endpoint: MAV2Rest API endpoint URL
            target_system: Target system ID for MAVLink messages
        """
        self.mav2rest_endpoint = mav2rest_endpoint
        self.target_system = target_system  # Use provided target system ID

        self.target_component = 1  # Default target component ID
        self.last_send_time = 0
        self.send_interval_sec = 0.1  # Minimum interval between messages (100ms)

        # LANDING_TARGET message template (based on working BlueOS pattern)
        self.landing_target_template = """{{
  "header": {{
    "system_id": 255,
    "component_id": 0,
    "sequence": 0
  }},
  "message": {{
    "type": "LANDING_TARGET",
    "time_usec": {time_usec},
    "target_num": {target_num},
    "frame": {{
      "type": "MAV_FRAME_{frame_name}"
    }},
    "angle_x": {angle_x},
    "angle_y": {angle_y},
    "distance": {distance},
    "size_x": {size_x},
    "size_y": {size_y},
    "x": {x},
    "y": {y},
    "z": {z},
    "q": [
      {q0},
      {q1},
      {q2},
      {q3}
    ],
    "position_type": {{
      "type": "LANDING_TARGET_TYPE_{position_type_name}"
    }}
  }}
}}"""

        logger.info(f"LandingTargetSender initialized with endpoint: {mav2rest_endpoint}, target_system: {self.target_system}")

    def test_connection(self) -> Dict[str, Any]:
        """
        Test connection to MAV2Rest API

        Returns:
            Dictionary with connection test results
        """
        # List of common BlueOS MAV2Rest endpoints to try
        # Since container uses host networking, try localhost first
        endpoints_to_try = [
            "http://localhost:6040",
            "http://127.0.0.1:6040",
            "http://localhost:6041",  # Alternative port
            "http://127.0.0.1:6041",
            self.mav2rest_endpoint,
            "http://host.docker.internal:6040",
            "http://localhost/mavlink2rest",
            "http://127.0.0.1/mavlink2rest",
            "http://host.docker.internal/mavlink2rest"
        ]

        # Remove duplicates while preserving order
        unique_endpoints = []
        for endpoint in endpoints_to_try:
            if endpoint not in unique_endpoints:
                unique_endpoints.append(endpoint)

        last_error = None

        for endpoint in unique_endpoints:
            try:
                logger.debug(f"Testing MAV2Rest endpoint: {endpoint}")
                response = requests.get(f"{endpoint}/mavlink", timeout=3)
                if response.status_code == 200:
                    logger.info(f"MAV2Rest connection successful on: {endpoint}")
                    # Update the endpoint if we found a working one different from default
                    if endpoint != self.mav2rest_endpoint:
                        logger.info(f"Updating MAV2Rest endpoint from {self.mav2rest_endpoint} to {endpoint}")
                        self.mav2rest_endpoint = endpoint
                    return {
                        "success": True,
                        "message": "MAV2Rest API connection successful",
                        "endpoint": endpoint,
                        "tested_endpoints": unique_endpoints
                    }
                else:
                    last_error = f"HTTP {response.status_code}"
                    logger.debug(f"MAV2Rest endpoint {endpoint} returned HTTP {response.status_code}")
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {str(e)}"
                logger.debug(f"MAV2Rest endpoint {endpoint} failed: {last_error}")
            except requests.RequestException as e:
                last_error = f"Request error: {str(e)}"
                logger.debug(f"MAV2Rest endpoint {endpoint} failed: {last_error}")

        # All endpoints failed
        logger.error(f"All MAV2Rest endpoints failed. Last error: {last_error}")
        return {
            "success": False,
            "message": f"Failed to connect to any MAV2Rest endpoint. Last error: {last_error}",
            "tested_endpoints": unique_endpoints,
            "last_error": last_error
        }

    def send_landing_target(self,
                            angle_x: float,
                            angle_y: float,
                            distance: float = 0.0,
                            size_x: float = 0.0,
                            size_y: float = 0.0,
                            target_num: int = 0,
                            frame: int = MAV_FRAME_BODY_FRD,
                            position_type: int = LANDING_TARGET_TYPE_VISION_FIDUCIAL) -> Dict[str, Any]:
        """
        Send LANDING_TARGET MAVLink message

        Args:
            angle_x: X-axis angular offset in radians
            angle_y: Y-axis angular offset in radians
            distance: Distance to target in meters (0 if unknown)
            size_x: Size of target along x-axis in radians (0 if unknown)
            size_y: Size of target along y-axis in radians (0 if unknown)
            target_num: Target number (0 for standard landing target)
            frame: Coordinate frame of reference
            position_type: Type of landing target

        Returns:
            Dictionary with send results
        """
        # Rate limiting - don't send messages too frequently
        current_time = time.time()
        if current_time - self.last_send_time < self.send_interval_sec:
            return {
                "success": False,
                "message": "Rate limited - message sent too soon after previous message",
                "rate_limited": True
            }

        try:
            # Get current time in microseconds since UNIX epoch
            time_usec = int(current_time * 1000000)

            # Map frame integer to frame name (simplified - we only use BODY_FRD)
            frame_name = "BODY_FRD" if frame == MAV_FRAME_BODY_FRD else "BODY_FRD"

            # Map position type integer to type name (simplified - we only use VISION_FIDUCIAL)
            position_type_name = "VISION_FIDUCIAL" if position_type == LANDING_TARGET_TYPE_VISION_FIDUCIAL else "VISION_FIDUCIAL"

            # Format the LANDING_TARGET message using BlueOS-style template
            landing_target_data = self.landing_target_template.format(
                time_usec=time_usec,
                target_num=target_num,
                frame_name=frame_name,
                angle_x=angle_x,
                angle_y=angle_y,
                distance=distance,
                size_x=size_x,
                size_y=size_y,
                x=0.0,  # X Position of the landing target in MAV_FRAME (not used for angular)
                y=0.0,  # Y Position of the landing target in MAV_FRAME (not used for angular)
                z=0.0,  # Z Position of the landing target in MAV_FRAME (not used for angular)
                q0=1.0,  # Quaternion of landing target orientation (not used)
                q1=0.0,
                q2=0.0,
                q3=0.0,
                position_type_name=position_type_name
            )

            # Send message via MAV2Rest using BlueOS-style post
            url = f"{self.mav2rest_endpoint}/mavlink"

            logger.debug(f"Sending LANDING_TARGET: angle_x={angle_x:.4f}, angle_y={angle_y:.4f}, distance={distance:.2f}")

            response = post_to_mav2rest(url, landing_target_data)

            if response is not None:
                self.last_send_time = current_time
                logger.debug("LANDING_TARGET message sent successfully")
                return {
                    "success": True,
                    "message": "LANDING_TARGET message sent successfully",
                    "time_usec": time_usec,
                    "angle_x": angle_x,
                    "angle_y": angle_y,
                    "response": response
                }
            else:
                logger.warning(f"Failed to send LANDING_TARGET: No response from MAV2Rest")
                return {
                    "success": False,
                    "message": "MAV2Rest returned no response",
                    "network_error": True
                }

        except Exception as e:
            logger.error(f"Unexpected error sending LANDING_TARGET: {str(e)}")
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}",
                "unexpected_error": True
            }


def calculate_angular_offsets(detection: Dict[str, Any],
                              image_width: int,
                              image_height: int,
                              camera_hfov_deg: float = 62.2,
                              camera_vfov_deg: float = 48.8) -> Dict[str, float]:
    """
    Calculate angular offsets from AprilTag detection data

    Args:
        detection: AprilTag detection dictionary
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels
        camera_hfov_deg: Horizontal field of view in degrees
        camera_vfov_deg: Vertical field of view in degrees

    Returns:
        Dictionary with angular offset information:
        - angle_x: Horizontal angular offset in radians
        - angle_y: Vertical angular offset in radians
        - angle_x_deg: Horizontal angular offset in degrees
        - angle_y_deg: Vertical angular offset in degrees
    """
    import math

    # Get image center
    image_center_x = image_width / 2
    image_center_y = image_height / 2

    # Get tag center
    tag_center_x = detection["center_x"]
    tag_center_y = detection["center_y"]

    # Calculate pixel offsets from center
    pixel_offset_x = tag_center_x - image_center_x
    pixel_offset_y = tag_center_y - image_center_y

    # Convert to normalized coordinates (-1 to 1)
    normalized_x = pixel_offset_x / (image_width / 2)
    normalized_y = pixel_offset_y / (image_height / 2)

    # Convert to angular offsets
    # For small angles, angle ≈ tan(angle) ≈ normalized_offset * (fov/2)
    angle_x_rad = normalized_x * math.radians(camera_hfov_deg / 2)
    angle_y_rad = normalized_y * math.radians(camera_vfov_deg / 2)

    return {
        "angle_x": angle_x_rad,
        "angle_y": angle_y_rad,
        "angle_x_deg": math.degrees(angle_x_rad),
        "angle_y_deg": math.degrees(angle_y_rad),
        "normalized_x": normalized_x,
        "normalized_y": normalized_y,
        "pixel_offset_x": pixel_offset_x,
        "pixel_offset_y": pixel_offset_y
    }


def estimate_target_size_angular(detection: Dict[str, Any],
                                 image_width: int,
                                 image_height: int,
                                 camera_hfov_deg: float = 62.2,
                                 camera_vfov_deg: float = 48.8) -> Dict[str, float]:
    """
    Estimate angular size of the AprilTag target

    Args:
        detection: AprilTag detection dictionary
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels
        camera_hfov_deg: Horizontal field of view in degrees
        camera_vfov_deg: Vertical field of view in degrees

    Returns:
        Dictionary with angular size information:
        - size_x: Horizontal angular size in radians
        - size_y: Vertical angular size in radians
    """
    import math

    # Get tag dimensions in pixels
    tag_width_pixels = detection["width"]
    tag_height_pixels = detection["height"]

    # Convert pixel size to angular size
    pixels_per_degree_h = image_width / camera_hfov_deg
    pixels_per_degree_v = image_height / camera_vfov_deg

    size_x_deg = tag_width_pixels / pixels_per_degree_h
    size_y_deg = tag_height_pixels / pixels_per_degree_v

    size_x_rad = math.radians(size_x_deg)
    size_y_rad = math.radians(size_y_deg)

    return {
        "size_x": size_x_rad,
        "size_y": size_y_rad,
        "size_x_deg": size_x_deg,
        "size_y_deg": size_y_deg
    }


def send_apriltag_as_landing_target(detection: Dict[str, Any],
                                    image_width: int,
                                    image_height: int,
                                    sender: LandingTargetSender,
                                    camera_hfov_deg: float = 62.2,
                                    camera_vfov_deg: float = 48.8) -> Dict[str, Any]:
    """
    Convert AprilTag detection to LANDING_TARGET MAVLink message and send it

    Args:
        detection: AprilTag detection dictionary
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels
        sender: LandingTargetSender instance
        camera_hfov_deg: Horizontal field of view in degrees
        camera_vfov_deg: Vertical field of view in degrees

    Returns:
        Dictionary with conversion and send results
    """
    try:
        # Calculate angular offsets
        angles = calculate_angular_offsets(detection, image_width, image_height,
                                           camera_hfov_deg, camera_vfov_deg)

        # Estimate angular size
        size = estimate_target_size_angular(detection, image_width, image_height,
                                            camera_hfov_deg, camera_vfov_deg)

        # Send LANDING_TARGET message
        result = sender.send_landing_target(
            angle_x=angles["angle_x"],
            angle_y=angles["angle_y"],
            distance=0.0,  # Distance unknown from vision alone
            size_x=size["size_x"],
            size_y=size["size_y"],
            target_num=detection["tag_id"],  # Use AprilTag ID as target number
            frame=MAV_FRAME_BODY_FRD,  # Body frame forward-right-down
            position_type=LANDING_TARGET_TYPE_VISION_FIDUCIAL
        )

        if result["success"]:
            logger.info(f"Sent LANDING_TARGET for AprilTag ID {detection['tag_id']}: "
                        f"angle_x={angles['angle_x_deg']:.2f}°, angle_y={angles['angle_y_deg']:.2f}°")

        # Add angle and size information to result
        result.update({
            "tag_id": detection["tag_id"],
            "angles": angles,
            "size": size
        })

        return result

    except Exception as e:
        logger.error(f"Error converting AprilTag to LANDING_TARGET: {str(e)}")
        return {
            "success": False,
            "message": f"Conversion error: {str(e)}",
            "conversion_error": True
        }


def get_landing_target_sender(mav2rest_endpoint: str = MAV2REST_ENDPOINT, target_system: int = 1) -> LandingTargetSender:
    """
    Create a new LandingTargetSender instance

    Args:
        mav2rest_endpoint: MAV2Rest API endpoint URL
        target_system: Target system ID for MAVLink messages

    Returns:
        LandingTargetSender instance
    """
    return LandingTargetSender(mav2rest_endpoint, target_system)


def test_mav2rest_connection(mav2rest_endpoint: str = MAV2REST_ENDPOINT, target_system: int = 1) -> Dict[str, Any]:
    """
    Test connection to MAV2Rest API

    Args:
        mav2rest_endpoint: MAV2Rest API endpoint URL
        target_system: Target system ID for MAVLink messages

    Returns:
        Dictionary with connection test results
    """
    sender = get_landing_target_sender(mav2rest_endpoint, target_system)
    return sender.test_connection()
