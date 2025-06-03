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
    },
    'precision_landing': {
        'enabled': False
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

        # Update camera RTSP URL
        if camera_type not in settings['cameras']:
            settings['cameras'][camera_type] = {}

        settings['cameras'][camera_type]['rtsp'] = rtsp

        # Update last used settings
        settings['last_used'] = {
            'camera_type': camera_type,
            'rtsp': rtsp
        }

        save_settings(settings)
        return True
    except Exception as e:
        logger.error(f"Error updating camera RTSP URL: {e}")
        return False


# get the latest RTSP URL for a specific camera type
def get_camera_rtsp(camera_type):
    """
    Get the saved RTSP URL for a camera type

    Args:
        camera_type (str): The camera type ("siyi-a8", "siyi-zr10", "siyi-zt6-ir", "siyi-zt6-rgb")

    Returns:
        str: The saved RTSP URL or default if not found
    """
    settings = get_settings()

    # Check if camera type exists in settings
    if camera_type in settings['cameras'] and 'rtsp' in settings['cameras'][camera_type]:
        return settings['cameras'][camera_type]['rtsp']

    # Return default RTSP URL if not found
    if camera_type in DEFAULT_SETTINGS['cameras']:
        return DEFAULT_SETTINGS['cameras'][camera_type]['rtsp']
    else:
        # Fallback to siyi-a8 if camera type not found
        return DEFAULT_SETTINGS['cameras']['siyi-a8']['rtsp']


# get the last used camera type and RTSP URL
def get_last_used():
    """
    Get the last used camera type and RTSP URL

    Returns:
        dict: Dictionary with camera_type and rtsp
    """
    settings = get_settings()
    return settings.get('last_used', DEFAULT_SETTINGS['last_used'])


# update the precision landing enabled state
def update_precision_landing_enabled(enabled):
    """
    Update the precision landing enabled state

    Args:
        enabled (bool): Whether precision landing is enabled

    Returns:
        bool: True if successful, False otherwise
    """
    try:
        settings = get_settings()

        # Ensure precision_landing section exists
        if 'precision_landing' not in settings:
            settings['precision_landing'] = {}

        settings['precision_landing']['enabled'] = enabled

        save_settings(settings)
        logger.debug(f"Updated precision landing enabled state to: {enabled}")
        return True
    except Exception as e:
        logger.error(f"Error updating precision landing enabled state: {e}")
        return False


# get the precision landing enabled state
def get_precision_landing_enabled():
    """
    Get the precision landing enabled state

    Returns:
        bool: True if precision landing is enabled, False otherwise
    """
    try:
        settings = get_settings()

        # Check if precision_landing section exists
        if 'precision_landing' in settings and 'enabled' in settings['precision_landing']:
            return settings['precision_landing']['enabled']

        # Return default if not found
        return DEFAULT_SETTINGS['precision_landing']['enabled']
    except Exception as e:
        logger.error(f"Error getting precision landing enabled state: {e}")
        return False
