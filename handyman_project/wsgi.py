import os
import sys

# Add your project to path
path = os.path.dirname(os.path.abspath(__file__))
if path not in sys.path:
    sys.path.append(path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'handyman_project.settings')

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()

# Debug print (will appear in logs)
print("✅ WSGI loaded successfully!")
