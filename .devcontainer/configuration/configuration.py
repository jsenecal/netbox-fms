# Based on https://github.com/netbox-community/netbox-docker/blob/release/configuration/configuration.py
import re
from os import environ
from os.path import abspath, dirname, join


# Read secret from file
def _read_secret(secret_name, default=None):
    try:
        f = open(f"/run/secrets/{secret_name}", encoding="utf-8")
    except OSError:
        return default
    else:
        with f:
            return f.readline().strip()


_BASE_DIR = dirname(dirname(abspath(__file__)))

#########################
#                       #
#   Required settings   #
#                       #
#########################

ALLOWED_HOSTS = environ.get("ALLOWED_HOSTS", "*").split(" ")

# PostgreSQL database configuration — uses PostGIS engine for GIS support
DATABASE = {
    "ENGINE": "django.contrib.gis.db.backends.postgis",
    "NAME": environ.get("DB_NAME", "netbox"),
    "USER": environ.get("DB_USER", ""),
    "PASSWORD": _read_secret("db_password", environ.get("DB_PASSWORD", "")),
    "HOST": environ.get("DB_HOST", "localhost"),
    "PORT": environ.get("DB_PORT", ""),
    "OPTIONS": {"sslmode": environ.get("DB_SSLMODE", "prefer")},
    "CONN_MAX_AGE": int(environ.get("DB_CONN_MAX_AGE", "300")),
    "DISABLE_SERVER_SIDE_CURSORS": environ.get(
        "DB_DISABLE_SERVER_SIDE_CURSORS",
        "False",
    ).lower()
    == "true",
}

REDIS = {
    "tasks": {
        "HOST": environ.get("REDIS_HOST", "localhost"),
        "PORT": int(environ.get("REDIS_PORT", 6379)),
        "PASSWORD": _read_secret("redis_password", environ.get("REDIS_PASSWORD", "")),
        "DATABASE": int(environ.get("REDIS_DATABASE", 0)),
        "SSL": environ.get("REDIS_SSL", "False").lower() == "true",
        "INSECURE_SKIP_TLS_VERIFY": environ.get(
            "REDIS_INSECURE_SKIP_TLS_VERIFY",
            "False",
        ).lower()
        == "true",
    },
    "caching": {
        "HOST": environ.get("REDIS_CACHE_HOST", environ.get("REDIS_HOST", "localhost")),
        "PORT": int(environ.get("REDIS_CACHE_PORT", environ.get("REDIS_PORT", 6379))),
        "PASSWORD": _read_secret(
            "redis_cache_password",
            environ.get("REDIS_CACHE_PASSWORD", environ.get("REDIS_PASSWORD", "")),
        ),
        "DATABASE": int(environ.get("REDIS_CACHE_DATABASE", 1)),
        "SSL": environ.get("REDIS_CACHE_SSL", environ.get("REDIS_SSL", "False")).lower()
        == "true",
        "INSECURE_SKIP_TLS_VERIFY": environ.get(
            "REDIS_CACHE_INSECURE_SKIP_TLS_VERIFY",
            environ.get("REDIS_INSECURE_SKIP_TLS_VERIFY", "False"),
        ).lower()
        == "true",
    },
}

SECRET_KEY = _read_secret("secret_key", environ.get("SECRET_KEY", ""))


#########################
#                       #
#   Optional settings   #
#                       #
#########################

ADMINS = []

ALLOWED_URL_SCHEMES = (
    "file", "ftp", "ftps", "http", "https", "irc",
    "mailto", "sftp", "ssh", "tel", "telnet", "tftp", "vnc", "xmpp",
)

BANNER_TOP = environ.get("BANNER_TOP", "")
BANNER_BOTTOM = environ.get("BANNER_BOTTOM", "")
BANNER_LOGIN = environ.get("BANNER_LOGIN", "")
BASE_PATH = environ.get("BASE_PATH", "")
CHANGELOG_RETENTION = int(environ.get("CHANGELOG_RETENTION", 90))

CORS_ORIGIN_ALLOW_ALL = environ.get("CORS_ORIGIN_ALLOW_ALL", "False").lower() == "true"
CORS_ORIGIN_WHITELIST = list(
    filter(None, environ.get("CORS_ORIGIN_WHITELIST", "https://localhost").split(" ")),
)
CORS_ORIGIN_REGEX_WHITELIST = [
    re.compile(r)
    for r in list(
        filter(None, environ.get("CORS_ORIGIN_REGEX_WHITELIST", "").split(" ")),
    )
]

DEBUG = environ.get("DEBUG", "False").lower() == "true"
DEVELOPER = environ.get("DEVELOPER_MODE", "False").lower() == "true"

EMAIL = {
    "SERVER": environ.get("EMAIL_SERVER", "localhost"),
    "PORT": int(environ.get("EMAIL_PORT", 25)),
    "USERNAME": environ.get("EMAIL_USERNAME", ""),
    "PASSWORD": _read_secret("email_password", environ.get("EMAIL_PASSWORD", "")),
    "USE_SSL": environ.get("EMAIL_USE_SSL", "False").lower() == "true",
    "USE_TLS": environ.get("EMAIL_USE_TLS", "False").lower() == "true",
    "SSL_CERTFILE": environ.get("EMAIL_SSL_CERTFILE", ""),
    "SSL_KEYFILE": environ.get("EMAIL_SSL_KEYFILE", ""),
    "TIMEOUT": int(environ.get("EMAIL_TIMEOUT", 10)),
    "FROM_EMAIL": environ.get("EMAIL_FROM", ""),
}

ENFORCE_GLOBAL_UNIQUE = environ.get("ENFORCE_GLOBAL_UNIQUE", "False").lower() == "true"
EXEMPT_VIEW_PERMISSIONS = list(
    filter(None, environ.get("EXEMPT_VIEW_PERMISSIONS", "").split(" ")),
)
GRAPHQL_ENABLED = environ.get("GRAPHQL_ENABLED", "True").lower() == "true"
LOGGING = {}
LOGIN_REQUIRED = environ.get("LOGIN_REQUIRED", "False").lower() == "true"
LOGIN_TIMEOUT = int(environ.get("LOGIN_TIMEOUT", 1209600))
MAINTENANCE_MODE = environ.get("MAINTENANCE_MODE", "False").lower() == "true"
MAX_PAGE_SIZE = int(environ.get("MAX_PAGE_SIZE", 1000))
MEDIA_ROOT = environ.get("MEDIA_ROOT", join(_BASE_DIR, "media"))
METRICS_ENABLED = environ.get("METRICS_ENABLED", "False").lower() == "true"

NAPALM_USERNAME = environ.get("NAPALM_USERNAME", "")
NAPALM_PASSWORD = _read_secret("napalm_password", environ.get("NAPALM_PASSWORD", ""))
NAPALM_TIMEOUT = int(environ.get("NAPALM_TIMEOUT", 30))
NAPALM_ARGS = {}

PAGINATE_COUNT = int(environ.get("PAGINATE_COUNT", 50))

PLUGINS = []
PLUGINS_CONFIG = {}

PREFER_IPV4 = environ.get("PREFER_IPV4", "False").lower() == "true"

RACK_ELEVATION_DEFAULT_UNIT_HEIGHT = int(
    environ.get("RACK_ELEVATION_DEFAULT_UNIT_HEIGHT", 22),
)
RACK_ELEVATION_DEFAULT_UNIT_WIDTH = int(
    environ.get("RACK_ELEVATION_DEFAULT_UNIT_WIDTH", 220),
)

REMOTE_AUTH_ENABLED = environ.get("REMOTE_AUTH_ENABLED", "False").lower() == "true"
REMOTE_AUTH_BACKEND = environ.get(
    "REMOTE_AUTH_BACKEND",
    "netbox.authentication.RemoteUserBackend",
)
REMOTE_AUTH_HEADER = environ.get("REMOTE_AUTH_HEADER", "HTTP_REMOTE_USER")
REMOTE_AUTH_AUTO_CREATE_USER = (
    environ.get("REMOTE_AUTH_AUTO_CREATE_USER", "True").lower() == "true"
)
REMOTE_AUTH_DEFAULT_GROUPS = list(
    filter(None, environ.get("REMOTE_AUTH_DEFAULT_GROUPS", "").split(" ")),
)

RELEASE_CHECK_URL = environ.get("RELEASE_CHECK_URL", None)
REPORTS_ROOT = environ.get("REPORTS_ROOT", "/etc/netbox/reports")
RQ_DEFAULT_TIMEOUT = int(environ.get("RQ_DEFAULT_TIMEOUT", 300))
SCRIPTS_ROOT = environ.get("SCRIPTS_ROOT", "/etc/netbox/scripts")
SESSION_FILE_PATH = environ.get("SESSIONS_ROOT", None)

TIME_ZONE = environ.get("TIME_ZONE", "UTC")
DATE_FORMAT = environ.get("DATE_FORMAT", "N j, Y")
SHORT_DATE_FORMAT = environ.get("SHORT_DATE_FORMAT", "Y-m-d")
TIME_FORMAT = environ.get("TIME_FORMAT", "g:i a")
SHORT_TIME_FORMAT = environ.get("SHORT_TIME_FORMAT", "H:i:s")
DATETIME_FORMAT = environ.get("DATETIME_FORMAT", "N j, Y g:i a")
SHORT_DATETIME_FORMAT = environ.get("SHORT_DATETIME_FORMAT", "Y-m-d H:i")

if DEBUG:
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS = [ip[: ip.rfind(".")] + ".1" for ip in ips] + [
        "127.0.0.1",
        "10.0.2.2",
    ]
