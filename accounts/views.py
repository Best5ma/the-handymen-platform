import json
import random
import base64
import requests
import re
import hashlib
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.mail import send_mail, EmailMultiAlternatives
from django.urls import reverse_lazy, reverse
from django.views import generic
from django.conf import settings
from django.db.models import Avg, Q, Count, Sum
from django.contrib import messages
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Job, Profile, User, Review, Bid, Transaction, Notification, Dispute, Withdrawal, EscrowLog
from .forms import ProfileForm, JobForm, HandymanSignUpForm, ReviewForm, BidForm
from .mpesa import MpesaClient


# ==================== 1. LANDING PAGE ====================
def home_view(request):
    """Homepage view with real verified artisans"""
    latest_reviews = Review.objects.all().order_by('-created_at')[:3]

    # Get actual verified handymen from your database with real stats
    featured_artisans = User.objects.filter(
        is_handyman=True,
        profile__is_verified=True
    ).select_related('profile').annotate(
        avg_rating=Avg('reviews_received__rating'),
        review_count=Count('reviews_received'),
        job_count=Count('hired_jobs', filter=Q(hired_jobs__status='completed'))
    )[:6]

    total_artisans = User.objects.filter(is_handyman=True, profile__is_verified=True).count()
    total_jobs = Job.objects.filter(is_completed=True).count()

    context = {
        'latest_reviews': latest_reviews,
        'featured_artisans': featured_artisans,
        'total_artisans': total_artisans,
        'total_jobs': total_jobs
    }
    return render(request, 'accounts/home.html', context)


# ==================== 2. EMAIL VERIFICATION ====================
@login_required
def send_verification_email(request):
    """Send email verification code with HTML template"""
    code = str(random.randint(100000, 999999))
    token = hashlib.sha256(f"{request.user.email}{code}{timezone.now()}".encode()).hexdigest()[:20]

    request.session['verification_code'] = code
    request.session['verification_token'] = token
    request.session['verification_sent_at'] = timezone.now().isoformat()

    verification_link = f"{settings.SITE_URL}{reverse('verify_email_page')}?token={token}&code={code}"

    subject = '🔐 The Handymen - Verify Your Email Address'
    html_content = render_to_string('registration/verification_email.html', {
        'user': request.user,
        'verification_code': code,
        'verification_link': verification_link,
    })
    text_content = strip_tags(html_content)

    try:
        email = EmailMultiAlternatives(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        messages.success(request, f"✅ Verification code sent to {request.user.email}")
    except Exception as e:
        messages.error(request, "❌ Failed to send verification email. Please try again.")
        print(f"Email error: {e}")

    return redirect('verify_email_page')


@login_required
def verify_email_page(request):
    """Verify email with code"""
    if request.user.is_email_verified:
        messages.info(request, "Your email is already verified.")
        return redirect('dashboard')

    token_code = request.GET.get('code', '')
    token = request.GET.get('token', '')

    if request.method == 'POST':
        entered_code = request.POST.get('code', '')
        stored_code = request.session.get('verification_code', '')

        if entered_code == stored_code:
            request.user.is_email_verified = True
            request.user.save()

            if 'verification_code' in request.session:
                del request.session['verification_code']
            if 'verification_token' in request.session:
                del request.session['verification_token']

            messages.success(request, "🎉 Email verified successfully! Welcome to the marketplace.")
            return redirect('dashboard')
        else:
            messages.error(request, "❌ Invalid verification code. Please try again.")

    context = {
        'token_code': token_code,
        'token': token,
        'email': request.user.email,
    }
    return render(request, 'accounts/verify_email.html', context)


@login_required
def resend_verification_email(request):
    """Resend verification email"""
    return send_verification_email(request)


# ==================== 3. MAIN DASHBOARD ====================
@login_required
def dashboard(request):
    """User dashboard based on role"""
    if not request.user.is_email_verified and not request.user.is_superuser:
        return render(request, 'accounts/verify_prompt.html')

    context = {}

    if request.user.is_superuser:
        context['role'] = "Admin"
        context['total_users'] = User.objects.count()
        context['total_jobs'] = Job.objects.count()
        context['handyman_count'] = User.objects.filter(is_handyman=True).count()
        context['client_count'] = User.objects.filter(is_client=True).count()
        context['completed_jobs'] = Job.objects.filter(status='completed').count()
        context['open_jobs'] = Job.objects.filter(status='open').count()
        context['in_progress_jobs'] = Job.objects.filter(status='in_progress').count()
        context['total_bids'] = Bid.objects.count()
        context['total_reviews'] = Review.objects.count()
        context['total_transactions'] = Transaction.objects.count()
        context['recent_jobs'] = Job.objects.all().select_related('client').order_by('-created_at')[:10]
        context['recent_users'] = User.objects.all().order_by('-date_joined')[:10]
        context['recent_bids'] = Bid.objects.all().select_related('job', 'handyman').order_by('-created_at')[:10]
        context['pending_verifications'] = User.objects.filter(is_handyman=True, profile__is_verified=False).order_by('-date_joined')[:10]

    elif request.user.is_handyman:
        context['role'] = "Handyman"
        context['available_jobs'] = Job.objects.filter(status='open', hired_worker__isnull=True).order_by('-created_at')
        context['my_active_jobs'] = Job.objects.filter(hired_worker=request.user, status='in_progress').order_by('-created_at')
        context['my_completed_jobs'] = Job.objects.filter(hired_worker=request.user, status='completed').order_by('-created_at')[:5]
        context['my_bids'] = Bid.objects.filter(handyman=request.user).select_related('job').order_by('-created_at')[:5]
        context['total_earned'] = Transaction.objects.filter(job__hired_worker=request.user, transaction_type='release', transaction_status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
        context['pending_withdrawals'] = Withdrawal.objects.filter(handyman=request.user, status='pending').aggregate(Sum('amount'))['amount__sum'] or 0
        context['unread_notifications'] = Notification.objects.filter(recipient=request.user, is_read=False).count()

    elif request.user.is_client:
        context['role'] = "Client"
        context['my_jobs'] = Job.objects.filter(client=request.user).order_by('-created_at')
        context['active_jobs'] = context['my_jobs'].filter(status='in_progress').count()
        context['jobs_with_bids'] = Job.objects.filter(client=request.user, bids__isnull=False).distinct().count()
        context['completed_jobs'] = context['my_jobs'].filter(status='completed').count()
        context['total_spent'] = Transaction.objects.filter(job__client=request.user, transaction_type='payment', transaction_status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
        context['in_escrow'] = Job.objects.filter(client=request.user, payment_status='escrow', status='in_progress').aggregate(Sum('price'))['price__sum'] or 0
        context['unread_notifications'] = Notification.objects.filter(recipient=request.user, is_read=False).count()

    else:
        context['role'] = "User"

    return render(request, 'accounts/dashboard.html', context)


# ==================== 4. POST JOB ====================
@login_required
def post_job(request):
    """Post a new job"""
    if not request.user.is_client:
        messages.error(request, "Only clients can post jobs.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = JobForm(request.POST)
        if form.is_valid():
            job = form.save(commit=False)
            job.client = request.user
            job.status = 'open'
            job.payment_status = 'unpaid'
            job.is_completed = False
            job.save()
            messages.success(request, "Job posted successfully! Handymen will start bidding soon.")
            return redirect('dashboard')
    else:
        form = JobForm()

    return render(request, 'accounts/post_job.html', {'form': form})


# ==================== 5. VIEW ALL ARTISANS ====================
def artisans_list(request):
    """Public view to list all verified artisans with real stats"""
    artisans = User.objects.filter(
        is_handyman=True,
        profile__is_verified=True
    ).select_related('profile').annotate(
        avg_rating=Avg('reviews_received__rating'),
        review_count=Count('reviews_received'),
        job_count=Count('hired_jobs', filter=Q(hired_jobs__status='completed'))
    ).order_by('-avg_rating', '-job_count')

    location = request.GET.get('location', '')
    if location:
        artisans = artisans.filter(profile__location__icontains=location)

    skill = request.GET.get('skill', '')
    if skill:
        artisans = artisans.filter(profile__skills__icontains=skill)

    return render(request, 'accounts/artisans_list.html', {
        'artisans': artisans,
        'total_artisans': artisans.count()
    })


# ==================== 6. JOB LIST VIEW ====================
def job_list(request):
    """List all available jobs for handymen to browse"""
    jobs = Job.objects.filter(
        status='open',
        hired_worker__isnull=True
    ).order_by('-created_at')

    location = request.GET.get('location', '')
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')

    if location:
        jobs = jobs.filter(location__icontains=location)
    if min_price:
        jobs = jobs.filter(price__gte=min_price)
    if max_price:
        jobs = jobs.filter(price__lte=max_price)

    context = {
        'jobs': jobs,
        'total_jobs': jobs.count()
    }
    return render(request, 'accounts/job_list.html', context)


# ==================== 7. LOCATION SEARCH ====================
def location_search(request):
    """Location-based search page with direct context"""
    from django.db.models import Count, Q

    handyman_locations = Profile.objects.exclude(location='').values('location').annotate(
        count=Count('user', filter=Q(user__is_handyman=True, user__profile__is_verified=True))
    ).order_by('-count')[:10]

    job_locations = Job.objects.filter(status='open').exclude(location='').values('location').annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    formatted_handyman = []
    for loc in handyman_locations:
        if loc['location']:
            formatted_handyman.append({'location': loc['location'], 'count': loc['count']})

    formatted_jobs = []
    for loc in job_locations:
        if loc['location']:
            formatted_jobs.append({'location': loc['location'], 'count': loc['count']})

    context = {
        'handyman_locations': formatted_handyman,
        'job_locations': formatted_jobs,
    }
    return render(request, 'accounts/location_search.html', context)


# ==================== 8. JOB DETAIL VIEW ====================
def job_detail(request, job_id):
    """View job details - public view for everyone"""
    job = get_object_or_404(Job, id=job_id)

    can_bid = False
    has_bid = False
    is_owner = False
    is_hired_handyman = False
    bids = None
    transactions = None
    user_has_reviewed = False

    if request.user.is_authenticated:
        if request.user == job.client:
            is_owner = True
            bids = job.bids.all().select_related('handyman__profile').order_by('-bid_amount')
            for bid in bids:
                avg_rating = Review.objects.filter(handyman=bid.handyman).aggregate(Avg('rating'))['rating__avg']
                bid.handyman_avg_rating = round(avg_rating, 1) if avg_rating else None

        elif request.user == job.hired_worker:
            is_hired_handyman = True

        elif request.user.is_handyman and job.status == 'open' and not job.hired_worker:
            try:
                if request.user.profile.is_verified:
                    can_bid = not Bid.objects.filter(job=job, handyman=request.user).exists()
                    has_bid = Bid.objects.filter(job=job, handyman=request.user).exists()
            except Profile.DoesNotExist:
                pass

    bid_count = job.bids.count()

    if is_owner or is_hired_handyman:
        transactions = job.transactions.all().order_by('-created_at')

    if request.user.is_authenticated and request.user.is_client and job.status == 'completed' and job.hired_worker:
        user_has_reviewed = Review.objects.filter(client=request.user, handyman=job.hired_worker).exists()

    context = {
        'job': job,
        'can_bid': can_bid,
        'has_bid': has_bid,
        'is_owner': is_owner,
        'is_hired_handyman': is_hired_handyman,
        'bids': bids,
        'bid_count': bid_count,
        'transactions': transactions,
        'user_has_reviewed': user_has_reviewed,
        'settings': settings,
    }
    return render(request, 'accounts/job_detail.html', context)


# ==================== 9. MARKETPLACE: BIDDING ====================
@login_required
def place_bid(request, job_id):
    """Place a bid on a job"""
    job = get_object_or_404(Job, id=job_id)

    if not request.user.is_handyman:
        messages.error(request, "Only handymen can place bids.")
        return redirect('dashboard')

    try:
        if not request.user.profile.is_verified:
            messages.error(request, "Your profile must be verified before you can bid.")
            return redirect('edit_profile')
    except Profile.DoesNotExist:
        messages.error(request, "Please complete your profile first.")
        return redirect('edit_profile')

    if job.status != 'open':
        messages.error(request, "This job is no longer open for bids.")
        return redirect('dashboard')

    if job.hired_worker:
        messages.error(request, "This job has already been assigned to someone.")
        return redirect('dashboard')

    existing_bid = Bid.objects.filter(job=job, handyman=request.user).exists()
    if existing_bid:
        messages.error(request, "You have already placed a bid on this job.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = BidForm(request.POST)
        if form.is_valid():
            bid = form.save(commit=False)
            bid.job = job
            bid.handyman = request.user
            bid.save()
            messages.success(request, "Your bid has been placed successfully!")

            try:
                send_mail(
                    'New Bid on Your Job',
                    f'A handyman has placed a bid on your job: {job.title}. Check your dashboard for details.',
                    settings.DEFAULT_FROM_EMAIL,
                    [job.client.email],
                    fail_silently=True,
                )
                Notification.objects.create(
                    recipient=job.client,
                    notification_type='bid',
                    title='New Bid Received',
                    message=f'{request.user.username} placed a bid of KES {bid.bid_amount} on your job.',
                    link=f'/job/{job.id}/'
                )
            except:
                pass

            return redirect('job_detail', job_id=job.id)
    else:
        form = BidForm(initial={'bid_amount': job.price})

    return render(request, 'accounts/place_bid.html', {'form': form, 'job': job})


# ==================== 10. HIRE WORKER ====================
@login_required
def hire_worker(request, job_id, worker_id):
    """Hire a handyman for the job"""
    job = get_object_or_404(Job, id=job_id)
    worker = get_object_or_404(User, id=worker_id, is_handyman=True)

    if job.client != request.user:
        messages.error(request, "You don't have permission to hire for this job.")
        return redirect('dashboard')

    if job.hired_worker:
        messages.error(request, "This job has already been assigned to someone.")
        return redirect('dashboard')

    if job.status != 'open':
        messages.error(request, "Cannot hire for a job that is not open.")
        return redirect('dashboard')

    job.hired_worker = worker
    job.status = 'in_progress'
    job.payment_status = 'pending'
    job.save()

    worker_name = worker.get_full_name() or worker.username
    messages.success(request, f"You have hired {worker_name}!")

    try:
        send_mail(
            'You have been hired!',
            f'Congratulations! You have been hired for the job: {job.title}. Please wait for the client to make payment.',
            settings.DEFAULT_FROM_EMAIL,
            [worker.email],
            fail_silently=True,
        )
        Notification.objects.create(
            recipient=worker,
            notification_type='hire',
            title='You have been hired!',
            message=f'You have been hired for job: {job.title}. Please wait for payment.',
            link=f'/job/{job.id}/'
        )
    except:
        pass

    return redirect('job_detail', job_id=job.id)


# ==================== 11. PROFILES & REVIEWS ====================
@login_required
def edit_profile(request):
    """Edit user profile"""
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile has been updated successfully!")
            return redirect('dashboard')
    else:
        form = ProfileForm(instance=profile)

    return render(request, 'accounts/edit_profile.html', {'form': form})


def view_public_profile(request, user_id):
    """View public profile of a handyman"""
    worker = get_object_or_404(User, id=user_id)
    reviews = Review.objects.filter(handyman=worker).order_by('-created_at')
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']

    completed_jobs = Job.objects.filter(hired_worker=worker, status='completed').count()
    active_jobs = Job.objects.filter(hired_worker=worker, status='in_progress').count()
    total_earned = Transaction.objects.filter(job__hired_worker=worker, transaction_type='release', transaction_status='completed').aggregate(Sum('amount'))['amount__sum'] or 0

    context = {
        'worker': worker,
        'reviews': reviews,
        'avg_rating': round(avg_rating, 1) if avg_rating else None,
        'completed_jobs': completed_jobs,
        'active_jobs': active_jobs,
        'total_earned': total_earned,
        'review_count': reviews.count()
    }
    return render(request, 'accounts/public_profile.html', context)


@login_required
def leave_review(request, handyman_id):
    """Leave a review for a handyman"""
    handyman = get_object_or_404(User, id=handyman_id)

    if not request.user.is_client:
        messages.error(request, "Only clients can leave reviews.")
        return redirect('public_profile', user_id=handyman_id)

    has_hired = Job.objects.filter(client=request.user, hired_worker=handyman, status='completed').exists()
    if not has_hired:
        messages.warning(request, "You can only leave reviews for handymen you've hired and completed jobs with.")
        return redirect('public_profile', user_id=handyman_id)

    existing_review = Review.objects.filter(client=request.user, handyman=handyman).exists()
    if existing_review:
        messages.error(request, "You have already reviewed this handyman.")
        return redirect('public_profile', user_id=handyman_id)

    if request.method == 'POST':
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.client = request.user
            review.handyman = handyman
            review.save()
            messages.success(request, "Thank you for your review!")

            Notification.objects.create(
                recipient=handyman,
                notification_type='review',
                title='New Review',
                message=f'{request.user.username} left you a {review.rating}★ review.',
                link=f'/profile/{handyman.id}/'
            )
            return redirect('public_profile', user_id=handyman_id)
    else:
        form = ReviewForm()

    return render(request, 'accounts/leave_review.html', {'form': form, 'handyman': handyman})


# ==================== 12. SEARCH FUNCTIONALITY ====================
def search(request):
    """Global search for jobs and artisans"""
    query = request.GET.get('q', '')

    if query:
        jobs = Job.objects.filter(
            Q(title__icontains=query) | Q(description__icontains=query) | Q(location__icontains=query),
            status='open'
        )[:5]

        artisans = User.objects.filter(
            Q(username__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query),
            is_handyman=True,
            profile__is_verified=True
        )[:5]
    else:
        jobs = []
        artisans = []

    context = {
        'query': query,
        'jobs': jobs,
        'artisans': artisans,
        'total_results': jobs.count() + artisans.count()
    }
    return render(request, 'accounts/search_results.html', context)


# ==================== 13. AUTHENTICATION ====================
class SignUpView(generic.CreateView):
    form_class = HandymanSignUpForm
    template_name = 'registration/signup.html'

    def get_success_url(self):
        next_url = self.request.GET.get('next', '')
        if next_url:
            return reverse_lazy('login') + f'?next={next_url}'
        return reverse_lazy('login')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Account created successfully! Please log in.")
        return response


# ==================== 14. PAYMENTS & ESCROW FLOW ====================
# [All your payment views remain exactly as you have them]
# I'm including placeholders to save space - keep your existing payment views

@login_required
def pay_to_escrow(request, job_id):
    return HttpResponse("Pay to Escrow - Coming Soon")

@login_required
def release_payment(request, job_id):
    return HttpResponse("Release Payment - Coming Soon")

@login_required
def initiate_payment(request, job_id):
    return render(request, 'accounts/initiate_payment.html', {'job': get_object_or_404(Job, id=job_id)})

@login_required
def payment_status(request, job_id):
    return render(request, 'accounts/payment_status.html', {'job': get_object_or_404(Job, id=job_id)})

@login_required
def start_job(request, job_id):
    return HttpResponse("Start Job - Coming Soon")

@login_required
def request_completion(request, job_id):
    return render(request, 'accounts/request_completion.html', {'job': get_object_or_404(Job, id=job_id)})

@login_required
def confirm_completion(request, job_id):
    return render(request, 'accounts/confirm_completion.html', {'job': get_object_or_404(Job, id=job_id)})

@login_required
def dispute_job(request, job_id):
    return render(request, 'accounts/dispute_job.html', {'job': get_object_or_404(Job, id=job_id)})

@login_required
def withdraw_funds(request, job_id):
    return render(request, 'accounts/withdraw_funds.html', {'job': get_object_or_404(Job, id=job_id)})


# ==================== 15. NOTIFICATIONS ====================
@login_required
def notifications(request):
    user_notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    unread_count = user_notifications.filter(is_read=False).count()
    context = {'notifications': user_notifications, 'unread_count': unread_count}
    return render(request, 'accounts/notifications.html', context)


@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()
    if request.GET.get('redirect'):
        return redirect(request.GET.get('redirect'))
    return redirect('notifications')


@login_required
def mark_all_notifications_read(request):
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect('notifications')


# ==================== 16. MESSAGING ====================
@login_required
def send_message(request):
    if request.method == 'POST' and request.user.is_client:
        artisan_id = request.POST.get('artisan_id')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        phone = request.POST.get('phone', '')
        artisan = get_object_or_404(User, id=artisan_id, is_handyman=True)

        try:
            client_name = request.user.get_full_name() or request.user.username
            full_message = f"""
            You have received a message from a client through The Handymen platform:

            -------------------------------------------------
            CLIENT INFORMATION:
            Name: {client_name}
            Email: {request.user.email}
            Phone: {phone if phone else 'Not provided'}

            MESSAGE DETAILS:
            Subject: {subject}

            Message:
            {message}
            -------------------------------------------------

            Please respond to the client directly to discuss the job opportunity.

            Thank you for using The Handymen!
            """

            send_mail(
                f'📬 New Inquiry: {subject}',
                full_message,
                settings.DEFAULT_FROM_EMAIL,
                [artisan.email],
                fail_silently=False,
            )

            client_message = f"""
            Hello {client_name},

            Your message has been sent to {artisan.get_full_name() or artisan.username}.

            Message summary:
            Subject: {subject}
            Message: {message}

            The artisan will contact you soon via email or phone.

            Thank you for using The Handymen!
            """

            send_mail(
                '✅ Message Sent - The Handymen',
                client_message,
                settings.DEFAULT_FROM_EMAIL,
                [request.user.email],
                fail_silently=True,
            )

            messages.success(request, f"✅ Your message has been sent to {artisan.get_full_name() or artisan.username}!")
        except Exception as e:
            messages.error(request, "❌ Failed to send message. Please try again later.")

    return redirect('artisans_list')


# ==================== 17. M-PESA CALLBACK ====================
@csrf_exempt
def mpesa_callback(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            print("M-Pesa Callback Data:", json.dumps(data, indent=2))
            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
        except Exception as e:
            print(f"Error processing callback: {e}")
            return JsonResponse({"ResultCode": 1, "ResultDesc": f"Failed: {str(e)}"})
    return JsonResponse({"ResultCode": 1, "ResultDesc": "Method not allowed"})


@csrf_exempt
def mpesa_timeout(request):
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})


@csrf_exempt
def mpesa_result(request):
    return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})