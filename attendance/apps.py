from django.apps import AppConfig
import os

class AttendanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'attendance'

    def ready(self):
        """
        Called when the app is ready.
        - Imports signal handlers
        - Clears all sessions on server restart for security
        """
        import attendance.signals  # noqa
        
        # Clear all sessions when server starts/restarts
        # This logs out all users when the server is killed and restarted
        # Only run once per server start (not on code reloads)
        if not hasattr(self, '_sessions_cleared'):
            self.clear_all_sessions_on_startup()
            self.__class__._sessions_cleared = True
    
    def clear_all_sessions_on_startup(self):
        """
        Clear all active sessions when the server starts.
        This ensures all users are logged out when the server is killed and restarted.
        
        Security benefit: Prevents session hijacking and ensures clean state after restart.
        """
        try:
            # Only run in main process, not in Django's auto-reloader child process
            run_main = os.environ.get('RUN_MAIN')
            
            # Skip if we're in the reloader process
            if run_main != 'true' and self._is_dev_server():
                return
            
            from django.contrib.sessions.models import Session
            
            # Delete all sessions
            session_count = Session.objects.all().count()
            if session_count > 0:
                Session.objects.all().delete()
                print(f"\n{'='*70}")
                print(f"[SECURITY] Server restart detected")
                print(f"[SECURITY] Cleared {session_count} session(s) - All users logged out")
                print(f"{'='*70}\n")
            
        except Exception as e:
            # Silently fail if there's an issue (e.g., during migrations, db not ready)
            pass
    
    def _is_dev_server(self):
        """Check if running under Django development server"""
        import sys
        return 'runserver' in sys.argv
