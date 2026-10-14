web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --worker-class gevent --worker-connections 1000 --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 50 --log-level info --access-logfile - --error-logfile -
release: python manage.py migrate --noinput && python manage.py collectstatic --noinput
