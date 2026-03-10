import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'handyman_project.settings')
django.setup()

from django.core.mail import send_mail

try:
    sent = send_mail(
        'Test Email from The Handymen',
        'This is a test email to verify SMTP is working.',
        'your-email@gmail.com',  # Replace with YOUR email
        ['your-email@gmail.com'],  # Send to yourself for testing
        fail_silently=False,
    )
    print(f"✅ Email sent successfully! Message ID: {sent}")
except Exception as e:
    print(f"❌ Failed to send email: {e}")