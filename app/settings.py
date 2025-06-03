#!/usr/bin/env python3

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger("precision-landing.settings")

# Settings file path - stored in the extension's persistent storage directory
SETTINGS_FILE = Path('/app/settings/precision-landing-settings.json')

# Default settings
DEFAULT_SETTINGS = {
    'cameras': {
        'siyi-a8': {
            'rtsp': 'rtsp://192.168.144.25:8554/main.264'
        },
        'siyi-zr10': {
            'rtsp': 'rtsp://192.168.144.25:8554/main.264'
        },
        'siyi-zt6-ir': {
            'rtsp': 'rtsp://192.168.144.25:8554/video1'
        },
        'siyi-zt6-rgb': {
            'rtsp': 'rtsp://192.168.144.25:8554/video2'
        }
    },
    'last_used': {
        'camera_type': 'siyi-a8',
        'rtsp': 'rtsp://192.168.144.25:8554/main.264'
    }
}


# get the dictionary of settings from the settings file
def get_settings():
    """
    Load settings from the settings file.
    Creates default settings file if it doesn't exist.

    Returns:
        dict: The settings dictionary
    """
    try:
        if not SETTINGS_FILE.exists():
            logger.info(f"Settings file not found, creating default at {SETTINGS_FILE}")
            save_settings(DEFAULT_SETTINGS)
            return DEFAULT_SETTINGS

        with open(SETTINGS_FILE, 'r') as f:
            settings = json.load(f)
            logger.debug(f"Loaded settings: {settings}")
            return settings
    except Exception as e:
        logger.error(f"Error loading settings: {e}")
        logger.info("Using default settings")
        # Try to save default settings for next time
        try:
            save_settings(DEFAULT_SETTINGS)
        except Exception:
            logger.exception("Failed to save default settings")

        return DEFAULT_SETTINGS


# save settings to the settings file
def save_settings(settings):
    """
    Save settings to the settings file

    Args:
        settings (dict): Settings dictionary to save
    """
    try:
        # Ensure parent directory exists
        os.makedirs(SETTINGS_FILE.parent, exist_ok=True)

        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
            logger.debug(f"Saved settings: {settings}")
    except Exception as e:
        logger.error(f"Error saving settings: {e}")


# update the camera RTSP URL in the settings file
def update_camera_rtsp(camera_type, rtsp):
    """
    Update the RTSP URL for a specific camera type

    Args:
        camera_type (str): The camera type ("siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb")
        rtsp (str): The RTSP URL

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        settings = get_settings()

        # Update camera IP
        if camera_type not in settings['cameras']:
            settings['cameras'][camera_type] = {}

        settings['cameras'][camera_type]['ip'] = ip

        # Update last used settings
        settings['last_used'] = {
            'camera_type': camera_type,
            'ip': ip
        }

        save_settings(settings)
        return True
    except Exception as e:
        logger.error(f"Error updating camera IP: {e}")
        return False


# get the latest IP address for a specific camera type
def get_camera_ip(camera_type):
    """
    Get the saved IP address for a camera type

    Args:
        camera_type (str): The camera type ("siyi" or "xfrobot")

    Returns:
        str: The saved IP address or default if not found
    """
    settings = get_settings()

    # Check if camera type exists in settings
    if camera_type in settings['cameras'] and 'ip' in settings['cameras'][camera_type]:
        return settings['cameras'][camera_type]['ip']

    # Return default IP if not found
    if camera_type == 'siyi':
        return DEFAULT_SETTINGS['cameras']['siyi']['ip']
    else:
        return DEFAULT_SETTINGS['cameras']['xfrobot']['ip']


# get the last used camera type and IP address
def get_last_used():
    """
    Get the last used camera type and IP

    Returns:
        dict: Dictionary with camera_type and ip
    """
    settings = get_settings()
    return settings.get('last_used', DEFAULT_SETTINGS['last_used'])
