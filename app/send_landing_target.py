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

# MAV2Rest endpoint
MAV2REST_ENDPOINT = "http://host.docker.internal:6040"

# MAVLink component ID
MAV_COMP_ID_ONBOARD_COMPUTER = 191  # Component ID for onboard computer systems

# LANDING_TARGET message template
LANDING_TARGET_TEMPLATE = """{{
  "header": {{
    "system_id": {sysid},
    "component_id": {component_id},
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


# send mavlink message using MAV2Rest
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


# test connection to MAV2Rest
def test_mav2rest_connection(sysid: int = 1) -> Dict[str, Any]:
    """
    Test connection to MAV2Rest API

    Args:
        sysid: System ID to use in test message

    Returns:
        Dictionary with connection test results
    """
    try:
        logger.debug(f"Testing MAV2Rest endpoint: {MAV2REST_ENDPOINT}")
        response = requests.get(f"{MAV2REST_ENDPOINT}/mavlink", timeout=3)
        if response.status_code == 200:
            logger.info(f"MAV2Rest connection successful on: {MAV2REST_ENDPOINT}")

            # Send a test LANDING_TARGET message to verify the connection
            test_result = send_landing_target_msg(
                angle_x=0.0,
                angle_y=0.0,
                distance=0.0,
                size_x=0.0,
                size_y=0.0,
                target_num=0,
                sysid=sysid
            )

            if test_result["success"]:
                return {
                    "success": True,
                    "message": f"MAV2Rest API connection successful, test LANDING_TARGET sent to SysID {sysid}",
                    "endpoint": MAV2REST_ENDPOINT
                }
            else:
                return {
                    "success": False,
                    "message": f"MAV2Rest connected but test message failed: {test_result['message']}",
                    "endpoint": MAV2REST_ENDPOINT
                }
        else:
            logger.error(f"MAV2Rest endpoint returned HTTP {response.status_code}")
            return {
                "success": False,
                "message": f"HTTP {response.status_code}",
                "endpoint": MAV2REST_ENDPOINT
            }
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error: {str(e)}"
        logger.error(f"MAV2Rest connection failed: {error_msg}")
        return {
            "success": False,
            "message": error_msg,
            "endpoint": MAV2REST_ENDPOINT
        }
    except requests.RequestException as e:
        error_msg = f"Request error: {str(e)}"
        logger.error(f"MAV2Rest connection failed: {error_msg}")
        return {
            "success": False,
            "message": error_msg,
            "endpoint": MAV2REST_ENDPOINT
        }


# send LANDING_TARGET message based on AprilTag information
def send_landing_target(tag_id: int,
                        tag_center_x: float,
                        tag_center_y: float,
                        tag_width_pixels: float,
                        tag_height_pixels: float,
                        image_width: int,
                        image_height: int,
                        camera_hfov_deg: float = 62.2,
                        camera_vfov_deg: float = 48.8,
                        sysid: int = 1) -> Dict[str, Any]:
    """
    Convert AprilTag detection to LANDING_TARGET MAVLink message and send it

    Args:
        tag_id: AprilTag ID number
        tag_center_x: X coordinate of tag center in pixels
        tag_center_y: Y coordinate of tag center in pixels
        tag_width_pixels: Width of the tag in pixels
        tag_height_pixels: Height of the tag in pixels
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels
        camera_hfov_deg: Horizontal field of view in degrees
        camera_vfov_deg: Vertical field of view in degrees
        sysid: System ID to send message to

    Returns:
        Dictionary with conversion and send results
    """
    try:
        # Calculate angular offsets
        angles = calculate_angular_offsets(tag_center_x, tag_center_y,
                                           image_width, image_height,
                                           camera_hfov_deg, camera_vfov_deg)

        # Estimate angular size
        size = estimate_target_size_angular(tag_width_pixels, tag_height_pixels,
                                            image_width, image_height,
                                            camera_hfov_deg, camera_vfov_deg)

        # Send LANDING_TARGET message directly (no sender instance needed)
        result = send_landing_target_msg(
            angle_x=angles["angle_x"],
            angle_y=angles["angle_y"],
            distance=0.0,  # Distance unknown from vision alone
            size_x=size["size_x"],
            size_y=size["size_y"],
            target_num=tag_id,  # Use AprilTag ID as target number
            sysid=sysid
        )

        if result["success"]:
            logger.info(f"Sent LANDING_TARGET for AprilTag ID {tag_id} with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER}: "
                        f"angle_x={angles['angle_x_deg']:.2f}°, angle_y={angles['angle_y_deg']:.2f}°")

        # Add angle and size information to result
        result.update({
            "tag_id": tag_id,
            "angles": angles,
            "size": size,
            "sysid": sysid
        })

        return result

    except Exception as e:
        logger.error(f"Error sending LANDING_TARGET: {str(e)}")
        return {
            "success": False,
            "message": f"Conversion error: {str(e)}",
            "conversion_error": True
        }


# calculate angular offsets required for LANDING_TARGET message
def calculate_angular_offsets(tag_center_x: float,
                              tag_center_y: float,
                              image_width: int,
                              image_height: int,
                              camera_hfov_deg: float = 62.2,
                              camera_vfov_deg: float = 48.8) -> Dict[str, float]:
    """
    Calculate angular offsets from AprilTag detection data

    Args:
        tag_center_x: X coordinate of tag center in pixels
        tag_center_y: Y coordinate of tag center in pixels
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


# Estimate angular size of the AprilTag
def estimate_target_size_angular(tag_width_pixels: float,
                                 tag_height_pixels: float,
                                 image_width: int,
                                 image_height: int,
                                 camera_hfov_deg: float = 62.2,
                                 camera_vfov_deg: float = 48.8) -> Dict[str, float]:
    """
    Estimate angular size of the AprilTag target

    Args:
        tag_width_pixels: Width of the tag in pixels
        tag_height_pixels: Height of the tag in pixels
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


# Low level function to send LANDING_TARGET MAVLink message
def send_landing_target_msg(angle_x: float,
                            angle_y: float,
                            distance: float = 0.0,
                            size_x: float = 0.0,
                            size_y: float = 0.0,
                            target_num: int = 0,
                            sysid: int = 1) -> Dict[str, Any]:
    """
    Send LANDING_TARGET MAVLink message

    Args:
        angle_x: X-axis angular offset in radians
        angle_y: Y-axis angular offset in radians
        distance: Distance to target in meters (0 if unknown)
        size_x: Size of target along x-axis in radians (0 if unknown)
        size_y: Size of target along y-axis in radians (0 if unknown)
        target_num: Target number (0 for standard landing target)
        sysid: System ID to send message to

    Returns:
        Dictionary with send results
    """
    try:
        # Get current time in microseconds since UNIX epoch
        current_time = time.time()
        time_usec = int(current_time * 1000000)

        # Always use MAV_FRAME_LOCAL_FRD
        frame_name = "LOCAL_FRD"

        # Map position type integer to type name (always use VISION_FIDUCIAL)
        position_type_name = "VISION_FIDUCIAL"

        # Format the LANDING_TARGET message using BlueOS-style template
        landing_target_data = LANDING_TARGET_TEMPLATE.format(
            sysid=sysid,
            component_id=MAV_COMP_ID_ONBOARD_COMPUTER,
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
        url = f"{MAV2REST_ENDPOINT}/mavlink"

        logger.debug(f"Sending LANDING_TARGET with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER}: angle_x={angle_x:.4f}, angle_y={angle_y:.4f}, distance={distance:.2f}")

        response = post_to_mav2rest(url, landing_target_data)

        if response is not None:
            logger.debug(f"LANDING_TARGET message sent successfully with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER}")
            return {
                "success": True,
                "message": f"LANDING_TARGET message sent successfully with SysID {sysid} CompID {MAV_COMP_ID_ONBOARD_COMPUTER}",
                "time_usec": time_usec,
                "angle_x": angle_x,
                "angle_y": angle_y,
                "sysid": sysid,
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
