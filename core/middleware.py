"""
Custom middleware for mobile connection optimization
"""
from django.utils.deprecation import MiddlewareMixin
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.middleware import SessionMiddleware as DjangoSessionMiddleware
from django.shortcuts import redirect


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

