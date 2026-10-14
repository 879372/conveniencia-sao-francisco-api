# Railway Deploy Trigger: 2026-05-14
from .base import *
from decouple import config as env_config

# PRODUCTION SPECIFIC SETTINGS

DEBUG = False
ALLOWED_HOSTS = ['*']  # Permitir domínios do Railway

def parse_origins(raw_str):
    if not raw_str:
        return []
    cleaned = raw_str.strip()
    if cleaned.startswith('[') and cleaned.endswith(']'):
        cleaned = cleaned[1:-1]
    return [item.strip().strip('"').strip("'").strip() for item in cleaned.split(',') if item.strip()]

# WhiteNoise for Static Files
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# CORS
cors_origins_env = env_config('CORS_ALLOWED_ORIGINS', default='')
if cors_origins_env:
    CORS_ALLOWED_ORIGINS = parse_origins(cors_origins_env)
else:
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:5173',
    ]

# Static Files (WhiteNoise)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"
WHITENOISE_MANIFEST_STRICT = False

# CSRF & Security
csrf_origins_env = env_config('CSRF_TRUSTED_ORIGINS', default='')
if csrf_origins_env:
    CSRF_TRUSTED_ORIGINS = parse_origins(csrf_origins_env)
else:
    CSRF_TRUSTED_ORIGINS = [
        'http://localhost:5173',
    ]
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Security headers
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = env_config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_HTTPONLY = True

# Throttling
REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = [
    "rest_framework.throttling.AnonRateThrottle",
    "rest_framework.throttling.UserRateThrottle",
]
REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'] = {
    "anon": "50/hour",
    "user": "500/hour",
}

# Optimized DB Connections
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True  # Verifica conexão antes de reusar
DATABASES['default']['OPTIONS'] = {
    'connect_timeout': 10,
}

# Cache: Redis se disponível, senão LocMem
_redis_url = env_config('REDIS_URL', default=None)
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": _redis_url,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "IGNORE_EXCEPTIONS": True,  # API continua mesmo se Redis cair
            }
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

# Logging estruturado (visível no painel Railway)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
