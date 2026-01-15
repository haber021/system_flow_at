"""
Custom SQLite database backend with WAL mode and optimizations
"""
from django.db.backends.sqlite3 import base


class DatabaseWrapper(base.DatabaseWrapper):
    """
    Custom SQLite wrapper that enables WAL mode and performance optimizations
    """
    
    def get_new_connection(self, conn_params):
        """Override to set WAL mode and optimizations after connection"""
        conn = super().get_new_connection(conn_params)
        
        # Enable WAL mode for better concurrent access
        conn.execute('PRAGMA journal_mode=WAL;')
        
        # Set synchronous mode for balance between speed and safety
        conn.execute('PRAGMA synchronous=NORMAL;')
        
        # Additional performance optimizations
        conn.execute('PRAGMA cache_size=-64000;')  # 64MB cache
        conn.execute('PRAGMA temp_store=MEMORY;')  # Store temp tables in memory
        
        return conn
