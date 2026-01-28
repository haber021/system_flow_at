"""
Signal handlers for attendance app
"""
from django.contrib.auth.signals import user_logged_in
from django.contrib.sessions.models import Session
from django.dispatch import receiver
from django.utils import timezone


# Signal handler disabled - using login view checking instead
# This prevents automatic session invalidation and requires manual logout
# 
# @receiver(user_logged_in)
# def invalidate_other_sessions(sender, request, user, **kwargs):
#     """
#     Signal handler to invalidate all other sessions for a user when they log in.
#     This ensures only one active session per user account for security.
#     
#     NOTE: This is currently disabled in favor of preventing login when
#     an active session exists on another device.
#     """
#     pass

