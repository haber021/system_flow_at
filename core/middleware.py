"""
Custom middleware for mobile connection optimization
"""
from django.utils.deprecation import MiddlewareMixin
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware as DjangoSessionMiddleware
from django.shortcuts import redirect
from django.utils import timezone

try:
    from attendance.models import SystemSettings, Attendance
except Exception:
    SystemSettings = None
    Attendance = None


class SessionMiddleware(DjangoSessionMiddleware):
    """
    Custom SessionMiddleware that handles SessionInterrupted exceptions gracefully.
    This occurs when a session is deleted while a request is being processed
    (e.g., user logs out in another tab/window).
    """
    
    def process_response(self, request, response):
        try:
            # Call parent's process_response which may raise SessionInterrupted
            return super().process_response(request, response)
        except SessionInterrupted:
            # Session was deleted during request processing
            # If user was authenticated, clear them and redirect to login
            if hasattr(request, 'user') and request.user.is_authenticated:
                from django.contrib.auth import logout
                logout(request)
            # Return a redirect to login instead of raising the exception
            return redirect('login')


class MobileOptimizationMiddleware(MiddlewareMixin):
    """
    Enhanced middleware to optimize responses for mobile and network connections
    Adds cache headers, compression hints, and connection optimization for faster access
    """
    
    def process_request(self, request):
        # Log connection information for debugging (optional)
        # request.connection_host = request.get_host()
        # request.is_mobile = self._is_mobile_device(request)
        return None
    
    def _is_mobile_device(self, request):
        """Detect if the request is from a mobile device"""
        user_agent = request.META.get('HTTP_USER_AGENT', '').lower()
        mobile_keywords = ['mobile', 'android', 'iphone', 'ipad', 'tablet', 'windows phone']
        return any(keyword in user_agent for keyword in mobile_keywords)
    
    def process_response(self, request, response):
        # Add cache headers for static-like content (only if not already set)
        if request.path.startswith('/static/') and 'Cache-Control' not in response:
            response['Cache-Control'] = 'public, max-age=3600'
        
        # Note: Connection and Keep-Alive headers are hop-by-hop headers
        # managed by the WSGI server (Gunicorn, uWSGI) in production.
        # Django's development server doesn't allow setting them.
        
        # Add Vary header for proper caching
        if 'Vary' not in response:
            response['Vary'] = 'Accept-Encoding'
        
        # Optimize for mobile and network - add performance headers
        if 'Content-Type' in response:
            content_type = response['Content-Type']
            if 'text/html' in content_type or 'application/json' in content_type:
                # Add security headers if not already present
                if 'X-Content-Type-Options' not in response:
                    response['X-Content-Type-Options'] = 'nosniff'
                if 'X-Frame-Options' not in response:
                    response['X-Frame-Options'] = 'SAMEORIGIN'
                
                # Add resource hints for faster loading
                if 'text/html' in content_type:
                    # DNS prefetch for external resources
                    response['X-DNS-Prefetch-Control'] = 'on'
        
        # Add server timing header for performance monitoring (development only)
        if hasattr(request, '_start_time'):
            import time
            duration = (time.time() - request._start_time) * 1000
            response['Server-Timing'] = f'total;dur={duration:.2f}'
        
        return response


class AcademicYearRolloverMiddleware(MiddlewareMixin):
    """
    Middleware that checks if the academic year end date has passed and,
    if enabled, archives data and rolls to the next academic year.
    Runs once at first request after the end date.
    """

    def process_request(self, request):
        # Guard: models import availability
        if SystemSettings is None or Attendance is None:
            return None

        try:
            settings_obj = SystemSettings.get_settings()
        except Exception:
            return None

        # Only proceed if auto-archive is enabled and dates are configured
        if not getattr(settings_obj, 'auto_archive_on_year_end', False):
            return None

        ay_end = getattr(settings_obj, 'academic_year_end_date', None)
        ay_start = getattr(settings_obj, 'academic_year_start_date', None)
        if not ay_end or not ay_start:
            return None

        today = timezone.now().date()
        # Only run if we've crossed end date and haven't rolled over today
        if today <= ay_end:
            return None

        # Prevent repeated rollover within the same day
        last_rollover = getattr(settings_obj, 'last_rollover_at', None)
        if last_rollover and last_rollover.date() == today:
            return None

        # Archive current year's attendance
        current_year_label = settings_obj.get_current_year_label()
        try:
            now_ts = timezone.now()
            Attendance.objects.filter(academic_year=current_year_label, is_archived=False).update(
                is_archived=True,
                archive_year=current_year_label,
                archived_at=now_ts,
            )
        except Exception:
            # If archiving fails, do not proceed to rollover
            return None

        # Compute next academic year dates and label
        def _add_one_year_safe(d):
            try:
                return d.replace(year=d.year + 1)
            except Exception:
                # Fallback: +365 days
                from datetime import timedelta
                return d + timedelta(days=365)

        next_start = _add_one_year_safe(ay_start)
        next_end = _add_one_year_safe(ay_end)

        try:
            # Derive next label from next_start.year and next_end.year
            next_label = f"{next_start.year}-{next_end.year}"
        except Exception:
            # Fallback: increment parsed current label
            try:
                parts = current_year_label.split('-')
                y1 = int(parts[0]); y2 = int(parts[1])
                next_label = f"{y1+1}-{y2+1}"
            except Exception:
                next_label = current_year_label

        # Persist rollover
        try:
            settings_obj.academic_year_start_date = next_start
            settings_obj.academic_year_end_date = next_end
            settings_obj.current_academic_year = next_label
            settings_obj.last_rollover_at = timezone.now()
            settings_obj.save()
        except Exception:
            # If saving fails, swallow and continue; next request may retry
            return None

        return None


class SemesterRolloverMiddleware(MiddlewareMixin):
    """
    Middleware to archive the just-ended semester's attendance data so
    that current views start fresh at the next semester while keeping
    previous semester accessible.
    """

    def process_request(self, request):
        if SystemSettings is None or Attendance is None:
            return None

        try:
            settings_obj = SystemSettings.get_settings()
        except Exception:
            return None

        sem_end = getattr(settings_obj, 'semester_end_date', None)
        sem_start = getattr(settings_obj, 'semester_start_date', None)
        if not sem_end or not sem_start:
            return None

        today = timezone.now().date()
        # Only run after semester end and not more than once per day
        if today <= sem_end:
            return None

        last_sem_roll = getattr(settings_obj, 'last_semester_rollover_at', None)
        if last_sem_roll and last_sem_roll.date() == today:
            return None

        # Archive attendances within the semester window for the current academic year
        try:
            current_year_label = settings_obj.get_current_year_label()
            now_ts = timezone.now()
            Attendance.objects.filter(
                date__gte=sem_start,
                date__lte=sem_end,
                academic_year=current_year_label,
                is_archived=False,
            ).update(
                is_archived=True,
                archive_year=current_year_label,
                archived_at=now_ts,
            )
        except Exception:
            return None

        # Mark rollover
        try:
            settings_obj.last_semester_rollover_at = timezone.now()
            settings_obj.save()
        except Exception:
            return None

        return None

