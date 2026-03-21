"""
URL configuration for handyman_project project.
"""
from django.contrib import admin
from django.urls import path, include
from accounts import views
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from django.http import HttpResponse


# Test view to verify server is working
def test_view(request):
    return HttpResponse("✅ The Handymen is running! Server is working correctly.")


urlpatterns = [
    
    path('test/', views.test_view, name='test'),
    path('', views.home_view, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('admin/', admin.site.urls),
    path('accounts/signup/', views.SignUpView.as_view(), name='signup'),
    path('accounts/login/', auth_views.LoginView.as_view(
        template_name='registration/login.html',
        redirect_authenticated_user=True
    ), name='login'),
    path('accounts/', include('django.contrib.auth.urls')),

    # Email verification
    path('send-verification/', views.send_verification_email, name='send_verification_email'),
    path('verify-code/', views.verify_email_page, name='verify_email_page'),
    path('resend-verification/', views.resend_verification_email, name='resend_verification_email'),

    # Artisans and jobs
    path('artisans/', views.artisans_list, name='artisans_list'),
    path('jobs/', views.job_list, name='job_list'),
    path('location-search/', views.location_search, name='location_search'),

    # Job management
    path('post-job/', views.post_job, name='post_job'),
    path('job/<int:job_id>/', views.job_detail, name='job_detail'),
    path('job/<int:job_id>/bid/', views.place_bid, name='place_bid'),
    path('hire/<int:job_id>/<int:worker_id>/', views.hire_worker, name='hire_worker'),

    # Payments
    path('job/<int:job_id>/initiate-payment/', views.initiate_payment, name='initiate_payment'),
    path('job/<int:job_id>/payment-status/', views.payment_status, name='payment_status'),
    path('job/<int:job_id>/request-completion/', views.request_completion, name='request_completion'),
    path('job/<int:job_id>/confirm-completion/', views.confirm_completion, name='confirm_completion'),
    path('job/<int:job_id>/dispute/', views.dispute_job, name='dispute_job'),
    path('job/<int:job_id>/withdraw/', views.withdraw_funds, name='withdraw_funds'),

    # Profiles and reviews
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('profile/<int:user_id>/', views.view_public_profile, name='public_profile'),
    path('review/<int:handyman_id>/', views.leave_review, name='leave_review'),

    # Messaging and search
    path('send-message/', views.send_message, name='send_message'),
    path('search/', views.search, name='search'),
    path('notifications/', views.notifications, name='notifications'),
    path('notifications/mark-read/<int:notification_id>/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read, name='mark_all_notifications_read'),
]

# Media files
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)







