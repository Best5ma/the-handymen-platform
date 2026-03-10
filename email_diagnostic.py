import os
import sys
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'handyman_project.settings')
django.setup()

from django.conf import settings
from django.core.mail import send_mail, get_connection
import socket

print("=" * 60)
print("EMAIL DIAGNOSTIC TOOL")
print("=" * 60)

# 1. Check Django settings
print("\n1. CHECKING DJANGO SETTINGS:")
print(f"   EMAIL_BACKEND: {settings.EMAIL_BACKEND}")
print(f"   EMAIL_HOST: {settings.EMAIL_HOST}")
print(f"   EMAIL_PORT: {settings.EMAIL_PORT}")
print(f"   EMAIL_USE_TLS: {settings.EMAIL_USE_TLS}")
print(f"   EMAIL_HOST_USER: {settings.EMAIL_HOST_USER}")
print(f"   EMAIL_HOST_PASSWORD: {'*' * len(settings.EMAIL_HOST_PASSWORD) if settings.EMAIL_HOST_PASSWORD else 'Not set'}")
print(f"   DEFAULT_FROM_EMAIL: {settings.DEFAULT_FROM_EMAIL}")

# 2. Check if we can connect to Gmail SMTP
print("\n2. TESTING SMTP CONNECTION:")
try:
    connection = get_connection(
        backend=settings.EMAIL_BACKEND,
        host=settings.EMAIL_HOST,
        port=settings.EMAIL_PORT,
        username=settings.EMAIL_HOST_USER,
        password=settings.EMAIL_HOST_PASSWORD,
        use_tls=settings.EMAIL_USE_TLS,
    )
    connection.open()
    print("   ✅ SMTP Connection successful!")
    connection.close()
except Exception as e:
    print(f"   ❌ SMTP Connection failed: {e}")

# 3. Test DNS resolution
print("\n3. TESTING DNS RESOLUTION:")
try:
    ip = socket.gethostbyname(settings.EMAIL_HOST)
    print(f"   ✅ {settings.EMAIL_HOST} resolves to: {ip}")
except Exception as e:
    print(f"   ❌ DNS resolution failed: {e}")

# 4. Test sending a simple email
print("\n4. TESTING EMAIL SENDING:")
try:
    sent = send_mail(
        'Diagnostic Test Email',
        'This is a test email from The Handymen diagnostic tool.',
        settings.DEFAULT_FROM_EMAIL,
        [settings.EMAIL_HOST_USER],  # Send to yourself
        fail_silently=False,
    )
    print(f"   ✅ Email sent successfully! Result: {sent}")
except Exception as e:
    print(f"   ❌ Email sending failed: {e}")
    print(f"   Error type: {type(e).__name__}")
    print(f"   Error details: {str(e)}")

print("\n" + "=" * 60)
print("DIAGNOSTIC COMPLETE")
print("=" * 60)