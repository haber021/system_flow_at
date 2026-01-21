import os
import socket
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-change-me-in-production'

DEBUG = True

# Enhanced multi-host configuration for easy network access
# Automatically detects local IP and allows multiple access points
def get_local_ip():
    """Get the local IP address of the server"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return None

# Build comprehensive allowed hosts list
ALLOWED_HOSTS = [
    '*',  # Wildcard for development (remove in production)
    'localhost',
    '127.0.0.1',
    '0.0.0.0',
    'attendance-monitor.local',
    '10.251.88.18',
]

# Add local IP to allowed hosts
local_ip = get_local_ip()
if local_ip and local_ip not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(local_ip)

# Add environment-based hosts for production deployment
env_hosts = os.environ.get('ADDITIONAL_HOSTS', '')
if env_hosts:
    ALLOWED_HOSTS.extend([h.strip() for h in env_hosts.split(',') if h.strip()])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'attendance',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.middleware.gzip.GZipMiddleware',  # Compression for faster mobile connections
    'core.middleware.MobileOptimizationMiddleware',  # Custom mobile optimization
    'core.middleware.AcademicYearRolloverMiddleware',  # Auto-archive and rollover at academic year end
    'core.middleware.SemesterRolloverMiddleware',  # Archive at semester end to reset visible state
    'core.middleware.SessionMiddleware',  # Custom session middleware that handles SessionInterrupted
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'attendance.context_processors.adviser_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Enhanced database configuration for better data transfer
# Using custom backend with WAL mode and performance optimizations
DATABASES = {
    'default': {
        'ENGINE': 'core.db_backend',  # Custom backend with WAL mode
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 30,  # Increased timeout for network operations
            'check_same_thread': False,
        },
        'CONN_MAX_AGE': 600,  # Connection pooling - reuse connections for 10 minutes
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Media files (user uploads)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# WhiteNoise Configuration for optimized static file serving
WHITENOISE_USE_FINDERS = True
WHITENOISE_AUTOREFRESH = True
WHITENOISE_MAX_AGE = 31536000  # 1 year cache for static files

# Compression Settings
GZIP_MIDDLEWARE_COMPRESS_LEVEL = 6  # Balance between speed and compression

# File serving optimizations for faster image loading
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

# Cache Configuration for better performance
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'unique-snowflake',
        'TIMEOUT': 300,  # 5 minutes
        'OPTIONS': {
            'MAX_ENTRIES': 1000
        }
    },
    # Dedicated cache for media files (profile pictures)
    'media': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'media-cache',
        'TIMEOUT': 86400,  # 24 hours cache for media files
        'OPTIONS': {
            'MAX_ENTRIES': 500
        }
    }
}

# Session Configuration for mobile optimization
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS

# Security Headers for mobile
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'SAMEORIGIN'

# Performance optimizations for enhanced data transfer
DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10MB

# Connection and data transfer optimizations
DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000  # Allow more fields in POST requests
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # Support for reverse proxy
USE_X_FORWARDED_HOST = True  # Support for proxy forwarding
USE_X_FORWARDED_PORT = True  # Support for port forwarding

# Authentication
LOGIN_URL = '/'
LOGIN_REDIRECT_URL = '/dashboard/'
LOGOUT_REDIRECT_URL = '/'

# Email Configuration
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
EMAIL_PORT = int(os.environ.get('MAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
EMAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'  # set to True only when using SSL ports like 465
EMAIL_TIMEOUT = int(os.environ.get('MAIL_TIMEOUT', '10'))  # avoid long hangs that look like delivery delays
EMAIL_HOST_USER = os.environ.get('MAIL_USERNAME', 'habervincent21@gmail.com')
EMAIL_HOST_PASSWORD = os.environ.get('MAIL_PASSWORD', 'nvli tbsz atiz mqwc')
DEFAULT_FROM_EMAIL = os.environ.get('MAIL_DEFAULT_SENDER', 'DMMMSU ATTENDANCE MONITOR <habervincent21@gmail.com>')

# Optional: list of remote endpoints to replicate/forward attendance payloads to.
# Provide as a comma-separated list in env: ATTENDANCE_SAVE_HOSTS=https://host1/save,https://host2/save
ATTENDANCE_SAVE_HOSTS = [h.strip() for h in os.environ.get('ATTENDANCE_SAVE_HOSTS', '').split(',') if h.strip()]
# Mode: 'replicate' (save locally AND forward asynchronously) or 'forward_only' (forward-only behavior)
ATTENDANCE_SAVE_MODE = os.environ.get('ATTENDANCE_SAVE_MODE', 'replicate')
# Timeout in seconds for forwarding HTTP requests (used by async forwarder)
ATTENDANCE_FORWARD_TIMEOUT = int(os.environ.get('ATTENDANCE_FORWARD_TIMEOUT', '2'))
