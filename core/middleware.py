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
    Middleware to optimize responses for mobile connections
    Adds cache headers and compression hints for faster mobile access
    """
    
    def process_response(self, request, response):
        # Add cache headers for static-like content (only if not already set)
        if request.path.startswith('/static/') and 'Cache-Control' not in response:
            response['Cache-Control'] = 'public, max-age=3600'
        
        # Note: Connection header is managed by the WSGI server, not set here
        # Django's development server and production servers handle this automatically
        
        # Add Vary header for proper caching
        if 'Vary' not in response:
            response['Vary'] = 'Accept-Encoding'
        
        # Optimize for mobile networks - add performance headers
        if 'Content-Type' in response:
            content_type = response['Content-Type']
            if 'text/html' in content_type or 'application/json' in content_type:
                # Add security headers if not already present
                if 'X-Content-Type-Options' not in response:
                    response['X-Content-Type-Options'] = 'nosniff'
                if 'X-Frame-Options' not in response:
                    response['X-Frame-Options'] = 'SAMEORIGIN'
        
        return response

