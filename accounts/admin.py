from django.contrib import admin
from .models import User, Job, Profile

# This lets the Admin see everything in one place
admin.site.register(User)
admin.site.register(Job)
admin.site.register(Profile)
