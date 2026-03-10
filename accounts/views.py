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
    )[:6]  # Show up to 6 artisans

    total_artisans = User.objects.filter(is_handyman=True, profile__is_verified=True).count()
    total_jobs = Job.objects.filter(is_completed=True).count()

    context = {
        'latest_reviews': latest_reviews,
        'featured_artisans': featured_artisans,
        'total_artisans': total_artisans,
        'total_jobs': total_jobs
    }
    return render(request, 'accounts/home.html', context)


# ==================== 2. EMAIL VERIFICATION (ENHANCED) ====================
@login_required
def send_verification_email(request):
    """Send email verification code with HTML template"""
    # Generate a 6-digit code
    code = str(random.randint(100000, 999999))

    # Create a verification token (for clickable link)
    token = hashlib.sha256(f"{request.user.email}{code}{timezone.now()}".encode()).hexdigest()[:20]

    # Store in session
    request.session['verification_code'] = code
    request.session['verification_token'] = token
    request.session['verification_sent_at'] = timezone.now().isoformat()

    # Create verification link
    verification_link = f"{settings.SITE_URL}{reverse('verify_email_page')}?token={token}&code={code}"

    # Prepare email content
    subject = '🔐 The Handymen - Verify Your Email Address'
    html_content = render_to_string('registration/verification_email.html', {
        'user': request.user,
        'verification_code': code,
        'verification_link': verification_link,
    })
    text_content = strip_tags(html_content)

    try:
        # Send email
        email = EmailMultiAlternatives(
            subject,
            text_content,
            settings.DEFAULT_FROM_EMAIL,
            [request.user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()

        messages.success(request, f"✅ Verification code sent to {request.user.email}")
        print(f"📧 Verification email sent to {request.user.email} with code: {code}")

    except Exception as e:
        messages.error(request, "❌ Failed to send verification email. Please try again.")
        print(f"❌ Email error: {e}")

    return redirect('verify_email_page')


@login_required
def verify_email_page(request):
    """Verify email with code"""
    # Check if user is already verified
    if request.user.is_email_verified:
        messages.info(request, "Your email is already verified.")
        return redirect('dashboard')

    # Auto-fill from URL parameters (for clickable link)
    token_code = request.GET.get('code', '')
    token = request.GET.get('token', '')

    if request.method == 'POST':
        entered_code = request.POST.get('code', '')
        stored_code = request.session.get('verification_code', '')

        # Verify code
        if entered_code == stored_code:
            # Mark email as verified
            request.user.is_email_verified = True
            request.user.save()

            # Clear session data
            if 'verification_code' in request.session:
                del request.session['verification_code']
            if 'verification_token' in request.session:
                del request.session['verification_token']

            messages.success(request, "🎉 Email verified successfully! Welcome to the marketplace.")

            # Send welcome email
            try:
                send_mail(
                    'Welcome to The Handymen!',
                    f'Hello {request.user.username},\n\nYour email has been verified. You can now start using the platform!\n\nBest regards,\nThe Handymen Team',
                    settings.DEFAULT_FROM_EMAIL,
                    [request.user.email],
                    fail_silently=True,
                )
            except:
                pass

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

        # Basic stats
        context['total_users'] = User.objects.count()
        context['total_jobs'] = Job.objects.count()
        context['jobs'] = Job.objects.all().order_by('-created_at')[:10]

        # Enhanced admin stats
        context['handyman_count'] = User.objects.filter(is_handyman=True).count()
        context['client_count'] = User.objects.filter(is_client=True).count()
        context['verified_handyman_count'] = User.objects.filter(is_handyman=True, profile__is_verified=True).count()
        context['completed_jobs'] = Job.objects.filter(status='completed').count()
        context['open_jobs'] = Job.objects.filter(status='open').count()
        context['in_progress_jobs'] = Job.objects.filter(status='in_progress').count()
        context['disputed_jobs'] = Job.objects.filter(status='disputed').count()
        context['total_bids'] = Bid.objects.count()
        context['total_reviews'] = Review.objects.count()
        context['total_transactions'] = Transaction.objects.count()
        context['total_escrow'] = Transaction.objects.filter(
            transaction_type='payment',
            transaction_status='completed'
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        context['avg_rating'] = Review.objects.aggregate(Avg('rating'))['rating__avg'] or 0

        # Calculate average bids per job
        if context['total_jobs'] > 0:
            context['avg_bid_per_job'] = context['total_bids'] / context['total_jobs']
        else:
            context['avg_bid_per_job'] = 0

        # Recent items
        context['recent_jobs'] = Job.objects.all().select_related('client').order_by('-created_at')[:10]
        context['recent_users'] = User.objects.all().order_by('-date_joined')[:10]
        context['recent_bids'] = Bid.objects.all().select_related('job', 'handyman').order_by('-created_at')[:10]
        context['recent_transactions'] = Transaction.objects.all().select_related('job').order_by('-created_at')[:10]
        context['pending_verifications'] = User.objects.filter(
            is_handyman=True,
            profile__is_verified=False
        ).order_by('-date_joined')[:10]

        # Disputes
        context['open_disputes'] = Dispute.objects.filter(status='open').count()

    elif request.user.is_handyman:
        context['role'] = "Handyman"

        # Available jobs (open for bidding)
        context['available_jobs'] = Job.objects.filter(
            status='open',
            hired_worker__isnull=True
        ).order_by('-created_at')

        # Jobs this handyman is working on (where they are hired and in progress)
        context['my_active_jobs'] = Job.objects.filter(
            hired_worker=request.user,
            status='in_progress'
        ).order_by('-created_at')

        # Jobs completed by this handyman
        context['my_completed_jobs'] = Job.objects.filter(
            hired_worker=request.user,
            status='completed'
        ).order_by('-created_at')[:5]

        # My bids
        context['my_bids'] = Bid.objects.filter(
            handyman=request.user
        ).select_related('job').order_by('-created_at')[:5]

        # Earnings
        context['total_earned'] = Transaction.objects.filter(
            job__hired_worker=request.user,
            transaction_type='release',
            transaction_status='completed'
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        # Pending withdrawals
        context['pending_withdrawals'] = Withdrawal.objects.filter(
            handyman=request.user,
            status='pending'
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        # Notifications
        context['unread_notifications'] = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

    elif request.user.is_client:
        context['role'] = "Client"

        # Jobs posted by this client
        context['my_jobs'] = Job.objects.filter(
            client=request.user
        ).order_by('-created_at')

        # Active jobs (in progress)
        context['active_jobs'] = context['my_jobs'].filter(status='in_progress').count()

        # Jobs with bids
        context['jobs_with_bids'] = Job.objects.filter(
            client=request.user,
            bids__isnull=False
        ).distinct().count()

        # Completed jobs
        context['completed_jobs'] = context['my_jobs'].filter(status='completed').count()

        # Jobs pending payment
        context['pending_payment_jobs'] = context['my_jobs'].filter(
            status='in_progress',
            payment_status='pending'
        ).count()

        # Total spent
        context['total_spent'] = Transaction.objects.filter(
            job__client=request.user,
            transaction_type='payment',
            transaction_status='completed'
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        # Money in escrow
        context['in_escrow'] = Job.objects.filter(
            client=request.user,
            payment_status='escrow',
            status='in_progress'
        ).aggregate(Sum('price'))['price__sum'] or 0

        # Notifications
        context['unread_notifications'] = Notification.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

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

    # Filter by location if provided
    location = request.GET.get('location', '')
    if location:
        artisans = artisans.filter(profile__location__icontains=location)

    # Filter by skill if provided
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

    # Add filtering
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

    # Get handyman locations with counts
    handyman_locations = Profile.objects.exclude(
        location=''
    ).values('location').annotate(
        count=Count('user', filter=Q(user__is_handyman=True, user__profile__is_verified=True))
    ).order_by('-count')[:10]

    # Get job locations with counts
    job_locations = Job.objects.filter(
        status='open'
    ).exclude(
        location=''
    ).values('location').annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    # Format handyman locations
    formatted_handyman = []
    for loc in handyman_locations:
        if loc['location']:
            formatted_handyman.append({
                'location': loc['location'],
                'count': loc['count']
            })

    # Format job locations
    formatted_jobs = []
    for loc in job_locations:
        if loc['location']:
            formatted_jobs.append({
                'location': loc['location'],
                'count': loc['count']
            })

    context = {
        'handyman_locations': formatted_handyman,
        'job_locations': formatted_jobs,
    }
    return render(request, 'accounts/location_search.html', context)


# ==================== 8. JOB DETAIL VIEW ====================
def job_detail(request, job_id):
    """View job details - public view for everyone"""
    job = get_object_or_404(Job, id=job_id)

    # Initialize variables
    can_bid = False
    has_bid = False
    is_owner = False
    is_hired_handyman = False
    bids = None
    transactions = None
    user_has_reviewed = False

    if request.user.is_authenticated:
        # Check if user is the job owner (client)
        if request.user == job.client:
            is_owner = True
            bids = job.bids.all().select_related('handyman__profile').order_by('-bid_amount')

            # Calculate average rating for each handyman in bids
            for bid in bids:
                avg_rating = Review.objects.filter(handyman=bid.handyman).aggregate(Avg('rating'))['rating__avg']
                bid.handyman_avg_rating = round(avg_rating, 1) if avg_rating else None

        # Check if user is the hired handyman
        elif request.user == job.hired_worker:
            is_hired_handyman = True

        # Check if user is a handyman and can bid (only if job is open)
        elif request.user.is_handyman and job.status == 'open' and not job.hired_worker:
            # Check if profile is verified
            try:
                if request.user.profile.is_verified:
                    can_bid = not Bid.objects.filter(job=job, handyman=request.user).exists()
                    has_bid = Bid.objects.filter(job=job, handyman=request.user).exists()
            except Profile.DoesNotExist:
                pass

    # Get number of bids
    bid_count = job.bids.count()

    # Get transaction history for involved users
    if is_owner or is_hired_handyman:
        transactions = job.transactions.all().order_by('-created_at')

    # Check if user has reviewed (for completed jobs)
    if request.user.is_authenticated and request.user.is_client and job.status == 'completed' and job.hired_worker:
        user_has_reviewed = Review.objects.filter(
            client=request.user,
            handyman=job.hired_worker
        ).exists()

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

    # Check if user is a verified handyman
    if not request.user.is_handyman:
        messages.error(request, "Only handymen can place bids.")
        return redirect('dashboard')

    # Check if profile is verified
    try:
        if not request.user.profile.is_verified:
            messages.error(request, "Your profile must be verified before you can bid.")
            return redirect('edit_profile')
    except Profile.DoesNotExist:
        messages.error(request, "Please complete your profile first.")
        return redirect('edit_profile')

    # Check if job is still available
    if job.status != 'open':
        messages.error(request, "This job is no longer open for bids.")
        return redirect('dashboard')

    # Check if job already has a hired worker
    if job.hired_worker:
        messages.error(request, "This job has already been assigned to someone.")
        return redirect('dashboard')

    # Check if handyman already bid
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

            # Notify the client about new bid
            try:
                send_mail(
                    'New Bid on Your Job',
                    f'A handyman has placed a bid on your job: {job.title}. Check your dashboard for details.',
                    settings.DEFAULT_FROM_EMAIL,
                    [job.client.email],
                    fail_silently=True,
                )

                # Create notification
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

    return render(request, 'accounts/place_bid.html', {
        'form': form,
        'job': job
    })


# ==================== 10. HIRE WORKER ====================
@login_required
def hire_worker(request, job_id, worker_id):
    """Hire a handyman for the job"""
    job = get_object_or_404(Job, id=job_id)
    worker = get_object_or_404(User, id=worker_id, is_handyman=True)

    # Verify the client owns this job
    if job.client != request.user:
        messages.error(request, "You don't have permission to hire for this job.")
        return redirect('dashboard')

    # Check if job is already assigned
    if job.hired_worker:
        messages.error(request, "This job has already been assigned to someone.")
        return redirect('dashboard')

    # Check if job is still open
    if job.status != 'open':
        messages.error(request, "Cannot hire for a job that is not open.")
        return redirect('dashboard')

    # Hire the worker
    job.hired_worker = worker
    job.status = 'in_progress'
    job.payment_status = 'pending'
    job.save()

    # Get worker's full name safely
    worker_name = worker.get_full_name() or worker.username
    messages.success(request, f"You have hired {worker_name}!")

    # Send notification email to the hired handyman
    try:
        send_mail(
            'You have been hired!',
            f'Congratulations! You have been hired for the job: {job.title}. Please wait for the client to make payment.',
            settings.DEFAULT_FROM_EMAIL,
            [worker.email],
            fail_silently=True,
        )

        # Create notification
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

    completed_jobs = Job.objects.filter(
        hired_worker=worker,
        status='completed'
    ).count()

    active_jobs = Job.objects.filter(
        hired_worker=worker,
        status='in_progress'
    ).count()

    # Get total earnings
    total_earned = Transaction.objects.filter(
        job__hired_worker=worker,
        transaction_type='release',
        transaction_status='completed'
    ).aggregate(Sum('amount'))['amount__sum'] or 0

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

    # Check if this client has hired this handyman before
    has_hired = Job.objects.filter(
        client=request.user,
        hired_worker=handyman,
        status='completed'
    ).exists()

    if not has_hired:
        messages.warning(request, "You can only leave reviews for handymen you've hired and completed jobs with.")
        return redirect('public_profile', user_id=handyman_id)

    existing_review = Review.objects.filter(
        client=request.user,
        handyman=handyman
    ).exists()

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

            # Create notification
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

    return render(request, 'accounts/leave_review.html', {
        'form': form,
        'handyman': handyman
    })


# ==================== 12. SEARCH FUNCTIONALITY ====================
def search(request):
    """Global search for jobs and artisans"""
    query = request.GET.get('q', '')

    if query:
        jobs = Job.objects.filter(
            Q(title__icontains=query) |
            Q(description__icontains=query) |
            Q(location__icontains=query),
            status='open'
        )[:5]

        artisans = User.objects.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query),
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
    """User signup view with redirect handling"""
    form_class = HandymanSignUpForm
    template_name = 'registration/signup.html'

    def get_success_url(self):
        """Redirect to login with next parameter if present"""
        next_url = self.request.GET.get('next', '')
        if next_url:
            return reverse_lazy('login') + f'?next={next_url}'
        return reverse_lazy('login')

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Account created successfully! Please log in.")
        return response


# ==================== 14. PAYMENTS ====================
@login_required
def pay_to_escrow(request, job_id):
    """Pay money into escrow"""
    job = get_object_or_404(Job, id=job_id)

    if job.client != request.user:
        messages.error(request, "You are not authorized to pay for this job.")
        return redirect('dashboard')

    if job.payment_status != 'pending':
        messages.error(request, f"Payment is already in {job.payment_status} status.")
        return redirect('dashboard')

    if not job.hired_worker:
        messages.error(request, "You need to hire a handyman before making payment.")
        return redirect('job_detail', job_id=job.id)

    if request.method == 'POST':
        # Here you would integrate with M-Pesa API
        job.payment_status = 'escrow'
        job.save()

        # Create transaction record
        Transaction.objects.create(
            job=job,
            amount=job.price,
            transaction_type='payment',
            transaction_status='completed',
            phone_number=request.user.profile.phone_number if hasattr(request.user, 'profile') else '',
            description=f'Payment for job: {job.title}'
        )

        # Create escrow log
        EscrowLog.objects.create(
            job=job,
            action='payment',
            amount=job.price,
            performed_by=request.user,
            description=f'Client paid KES {job.price} into escrow'
        )

        messages.success(request, f"KES {job.price} has been held in escrow successfully!")

        # Notify the handyman
        if job.hired_worker:
            try:
                send_mail(
                    'Payment Received',
                    f'Payment for job "{job.title}" has been placed in escrow. You can start working!',
                    settings.DEFAULT_FROM_EMAIL,
                    [job.hired_worker.email],
                    fail_silently=True,
                )

                Notification.objects.create(
                    recipient=job.hired_worker,
                    notification_type='payment',
                    title='Payment Received',
                    message=f'Payment of KES {job.price} has been placed in escrow for job: {job.title}',
                    link=f'/job/{job.id}/'
                )
            except:
                pass

        return redirect('job_detail', job_id=job.id)

    return render(request, 'accounts/payment_form.html', {'job': job})


@login_required
def release_payment(request, job_id):
    """Release payment from escrow to handyman"""
    job = get_object_or_404(Job, id=job_id)

    if job.client != request.user:
        messages.error(request, "You are not authorized to release payment.")
        return redirect('dashboard')

    if job.payment_status != 'escrow':
        messages.error(request, "Payment is not in escrow status.")
        return redirect('dashboard')

    if request.method == 'POST':
        job.payment_status = 'released'
        job.is_completed = True
        job.status = 'completed'
        job.completion_date = timezone.now()
        job.client_confirmed = True
        job.save()

        # Create transaction record for release
        Transaction.objects.create(
            job=job,
            amount=job.price,
            transaction_type='release',
            transaction_status='completed',
            phone_number=job.hired_worker.profile.phone_number if hasattr(job.hired_worker, 'profile') else '',
            description=f'Payment released for job: {job.title}'
        )

        # Create escrow log
        EscrowLog.objects.create(
            job=job,
            action='release',
            amount=job.price,
            performed_by=request.user,
            description=f'Client released KES {job.price} to handyman'
        )

        messages.success(request, "Payment released successfully! Job marked as complete.")

        # Notify the handyman
        if job.hired_worker:
            try:
                send_mail(
                    'Payment Released',
                    f'Payment for job "{job.title}" has been released to your account!',
                    settings.DEFAULT_FROM_EMAIL,
                    [job.hired_worker.email],
                    fail_silently=True,
                )

                Notification.objects.create(
                    recipient=job.hired_worker,
                    notification_type='payment',
                    title='Payment Released',
                    message=f'Payment of KES {job.price} has been released for job: {job.title}',
                    link=f'/job/{job.id}/'
                )
            except:
                pass

        return redirect('job_detail', job_id=job.id)

    return render(request, 'accounts/release_payment.html', {'job': job})


# ==================== 15. ESCROW FLOW ====================
@login_required
def initiate_payment(request, job_id):
    """Initiate M-Pesa payment to escrow"""
    job = get_object_or_404(Job, id=job_id)

    # Verify client owns the job
    if job.client != request.user:
        messages.error(request, "You are not authorized to pay for this job.")
        return redirect('dashboard')

    # Verify job is in correct state
    if job.payment_status != 'pending':
        messages.error(request, f"Cannot process payment. Current status: {job.payment_status}")
        return redirect('job_detail', job_id=job.id)

    if not job.hired_worker:
        messages.error(request, "You need to hire a handyman before making payment.")
        return redirect('job_detail', job_id=job.id)

    if request.method == 'POST':
        phone_number = request.POST.get('phone_number', '').strip()

        # Clean the phone number - remove any non-digit characters
        cleaned_number = re.sub(r'\D', '', phone_number)

        # Format validation for both simulation and live mode
        if settings.MPESA_SIMULATION_MODE:
            # In simulation mode, accept any number but format it properly
            if len(cleaned_number) == 9:  # 712345678
                formatted_number = '254' + cleaned_number
            elif len(cleaned_number) == 10 and cleaned_number.startswith('0'):  # 0712345678
                formatted_number = '254' + cleaned_number[1:]
            elif len(cleaned_number) == 12 and cleaned_number.startswith('254'):  # 254712345678
                formatted_number = cleaned_number
            elif len(cleaned_number) == 13 and cleaned_number.startswith('254'):  # 254712345678 with extra
                formatted_number = cleaned_number[:12]
            else:
                # Accept any number in simulation mode, just ensure it's 12 digits with 254 prefix
                if len(cleaned_number) > 12:
                    formatted_number = cleaned_number[:12]
                elif len(cleaned_number) < 12:
                    # Pad with zeros at the end to make 12 digits
                    formatted_number = cleaned_number.ljust(12, '0')
                else:
                    formatted_number = cleaned_number

                # Ensure it starts with 254
                if not formatted_number.startswith('254'):
                    formatted_number = '254' + formatted_number[-9:] if len(formatted_number) >= 9 else '254712345678'
        else:
            # Live mode - strict validation
            if len(cleaned_number) == 9:  # 712345678
                formatted_number = '254' + cleaned_number
            elif len(cleaned_number) == 10 and cleaned_number.startswith('0'):  # 0712345678
                formatted_number = '254' + cleaned_number[1:]
            elif len(cleaned_number) == 12 and cleaned_number.startswith('254'):  # 254712345678
                formatted_number = cleaned_number
            else:
                messages.error(request,
                               "Please enter a valid M-Pesa number (e.g., 712345678 or 0712345678 or 254712345678)")
                return render(request, 'accounts/initiate_payment.html', {'job': job, 'settings': settings})

            # Additional validation for live mode
            if not formatted_number.startswith('254') or len(formatted_number) != 12:
                messages.error(request, "Please enter a valid M-Pesa number (e.g., 254712345678)")
                return render(request, 'accounts/initiate_payment.html', {'job': job, 'settings': settings})

        try:
            # Show simulation message if in simulation mode
            if settings.MPESA_SIMULATION_MODE:
                messages.info(request,
                              "🔵 SIMULATION MODE: Payment is being simulated. No actual M-Pesa request will be sent.")

            # Initialize M-Pesa client
            mpesa = MpesaClient()

            # Callback URL
            callback_url = f"{settings.SITE_URL}{reverse('mpesa_callback')}"

            # Initiate STK Push
            response = mpesa.stk_push(
                phone_number=formatted_number,
                amount=int(job.price),
                account_reference=f"JOB{job.id}",
                transaction_desc=f"Payment for job: {job.title[:20]}",
                callback_url=callback_url
            )

            if response.get('ResponseCode') == '0':
                # Store checkout request ID in session
                request.session['checkout_request_id'] = response['CheckoutRequestID']
                request.session['job_id'] = job.id
                request.session['payment_phone'] = formatted_number

                # Create pending transaction
                Transaction.objects.create(
                    job=job,
                    amount=job.price,
                    transaction_type='payment',
                    transaction_status='pending',
                    phone_number=formatted_number,
                    mpesa_checkout_id=response['CheckoutRequestID'],
                    description=f'Pending payment for job: {job.title}'
                )

                if settings.MPESA_SIMULATION_MODE:
                    messages.info(request,
                                  "📱 SIMULATION: In simulation mode, the payment will auto-complete in 3 seconds.")

                return redirect('payment_status', job_id=job.id)
            else:
                messages.error(request, f"Payment failed: {response.get('errorMessage', 'Unknown error')}")

        except Exception as e:
            messages.error(request, f"Payment initiation failed: {str(e)}")
            print(f"Payment error: {e}")  # For debugging

    return render(request, 'accounts/initiate_payment.html', {'job': job, 'settings': settings})


@login_required
def payment_status(request, job_id):
    """Check payment status"""
    job = get_object_or_404(Job, id=job_id)

    checkout_request_id = request.session.get('checkout_request_id')

    if not checkout_request_id:
        messages.error(request, "No active payment session.")
        return redirect('job_detail', job_id=job.id)

    # Auto-success for simulation mode after a few seconds
    if settings.MPESA_SIMULATION_MODE and request.method == 'GET':
        # Check if this is a fresh page load
        if 'payment_attempted' not in request.session:
            request.session['payment_attempted'] = True
            # For simulation, we'll show processing state first

    if request.method == 'POST':
        try:
            mpesa = MpesaClient()
            response = mpesa.query_status(checkout_request_id)

            if response.get('ResultCode') == '0':
                # Payment successful
                job.payment_status = 'escrow'
                job.save()

                # Update transaction record
                transaction = Transaction.objects.filter(
                    job=job,
                    mpesa_checkout_id=checkout_request_id
                ).first()

                if transaction:
                    transaction.transaction_status = 'completed'
                    transaction.mpesa_receipt = response.get('MpesaReceiptNumber',
                                                             'SIM' + str(random.randint(100000, 999999)))
                    transaction.completed_at = timezone.now()
                    transaction.save()

                # Create escrow log
                EscrowLog.objects.create(
                    job=job,
                    action='payment',
                    amount=job.price,
                    performed_by=request.user,
                    description=f'Payment received. Receipt: {response.get("MpesaReceiptNumber", "SIM123456")}'
                )

                # Notify handyman
                if job.hired_worker:
                    Notification.objects.create(
                        recipient=job.hired_worker,
                        notification_type='payment',
                        title='Payment Received',
                        message=f'Payment of KES {job.price} has been placed in escrow for job: {job.title}',
                        link=f'/job/{job.id}/'
                    )

                messages.success(request, "✅ Payment successful! Funds are now held in escrow.")

                # Clear session
                if 'checkout_request_id' in request.session:
                    del request.session['checkout_request_id']
                if 'payment_attempted' in request.session:
                    del request.session['payment_attempted']

                return redirect('job_detail', job_id=job.id)
            else:
                messages.error(request, f"Payment failed: {response.get('ResultDesc', 'Unknown error')}")

        except Exception as e:
            messages.error(request, f"Error checking payment status: {str(e)}")

    context = {
        'job': job,
        'simulation_mode': settings.MPESA_SIMULATION_MODE
    }
    return render(request, 'accounts/payment_status.html', context)


@login_required
def start_job(request, job_id):
    """Handyman starts working on the job"""
    job = get_object_or_404(Job, id=job_id)

    # Verify handyman is the hired worker
    if request.user != job.hired_worker:
        messages.error(request, "Only the hired handyman can start this job.")
        return redirect('job_detail', job_id=job.id)

    # Verify payment is in escrow
    if job.payment_status != 'escrow':
        messages.error(request, "Payment must be in escrow before starting the job.")
        return redirect('job_detail', job_id=job.id)

    # Update job status
    job.status = 'in_progress'
    job.save()

    # Notify client
    Notification.objects.create(
        recipient=job.client,
        notification_type='system',
        title='Job Started',
        message=f'{request.user.username} has started working on job: {job.title}',
        link=f'/job/{job.id}/'
    )

    messages.success(request, "You have started working on this job. Good luck!")
    return redirect('job_detail', job_id=job.id)


@login_required
def request_completion(request, job_id):
    """Handyman requests completion of job"""
    job = get_object_or_404(Job, id=job_id)

    # Verify handyman is the hired worker
    if request.user != job.hired_worker:
        messages.error(request, "Only the hired handyman can request completion.")
        return redirect('job_detail', job_id=job.id)

    # Verify job is in correct state
    if job.status != 'in_progress':
        messages.error(request, "This job is not in progress.")
        return redirect('job_detail', job_id=job.id)

    if job.payment_status != 'escrow':
        messages.error(request, "Payment must be in escrow before requesting completion.")
        return redirect('job_detail', job_id=job.id)

    if request.method == 'POST':
        # Mark completion requested
        job.completion_requested = True
        job.save()

        # Get completion message from form
        message = request.POST.get('message', '')

        # Notify client
        send_mail(
            'Job Completion Requested',
            f'{job.hired_worker.username} has marked job "{job.title}" as complete.\n\nMessage: {message}\n\nPlease review and release payment.',
            settings.DEFAULT_FROM_EMAIL,
            [job.client.email],
            fail_silently=True,
        )

        # Create notification
        Notification.objects.create(
            recipient=job.client,
            notification_type='completion',
            title='Job Completion Requested',
            message=f'{request.user.username} has completed job: {job.title}. Please review and release payment.',
            link=f'/job/{job.id}/'
        )

        messages.success(request, "Completion request sent to client. They will review and release payment.")
        return redirect('job_detail', job_id=job.id)

    return render(request, 'accounts/request_completion.html', {'job': job})


@login_required
def confirm_completion(request, job_id):
    """Client confirms job completion and releases payment automatically"""
    job = get_object_or_404(Job, id=job_id)

    # Verify client owns the job
    if job.client != request.user:
        messages.error(request, "You are not authorized to confirm completion.")
        return redirect('job_detail', job_id=job.id)

    # Verify job is in correct state
    if job.payment_status != 'escrow':
        messages.error(request, "Payment must be in escrow to confirm completion.")
        return redirect('job_detail', job_id=job.id)

    if request.method == 'POST':
        # Get review data
        rating = request.POST.get('rating')
        review_comment = request.POST.get('review_comment')

        # Automatically release payment and mark as complete
        job.payment_status = 'released'
        job.status = 'completed'
        job.is_completed = True
        job.completion_date = timezone.now()
        job.client_confirmed = True
        job.save()

        # Create transaction record for release
        transaction = Transaction.objects.create(
            job=job,
            amount=job.price,
            transaction_type='release',
            transaction_status='completed',
            phone_number=job.hired_worker.profile.phone_number if hasattr(job.hired_worker, 'profile') else '',
            description=f'Payment released for job: {job.title}'
        )

        # Create escrow log
        EscrowLog.objects.create(
            job=job,
            action='release',
            amount=job.price,
            performed_by=request.user,
            description=f'Client confirmed completion and released KES {job.price}'
        )

        # Create review if provided
        if rating:
            Review.objects.create(
                client=request.user,
                handyman=job.hired_worker,
                rating=int(rating),
                comment=review_comment or ''
            )

        # Notify handyman
        if job.hired_worker:
            send_mail(
                'Payment Released - Job Complete!',
                f'Great news! Client has confirmed job completion for "{job.title}".\n\nKES {job.price} has been released to your M-Pesa.',
                settings.DEFAULT_FROM_EMAIL,
                [job.hired_worker.email],
                fail_silently=True,
            )

            Notification.objects.create(
                recipient=job.hired_worker,
                notification_type='payment',
                title='Payment Released!',
                message=f'Payment of KES {job.price} has been released for job: {job.title}',
                link=f'/job/{job.id}/'
            )

        messages.success(request, "✅ Job marked complete! Payment automatically released to handyman.")
        return redirect('job_detail', job_id=job.id)

    return render(request, 'accounts/confirm_completion.html', {'job': job})


@login_required
def dispute_job(request, job_id):
    """Client or handyman can dispute the job"""
    job = get_object_or_404(Job, id=job_id)

    # Verify user is involved in the job
    if request.user not in [job.client, job.hired_worker]:
        messages.error(request, "You are not involved in this job.")
        return redirect('job_detail', job_id=job.id)

    if request.method == 'POST':
        reason = request.POST.get('reason')

        # Create dispute
        dispute = Dispute.objects.create(
            job=job,
            raised_by=request.user,
            reason=reason,
            status='open'
        )

        # Update job status
        job.status = 'disputed'
        job.save()

        # Create escrow log
        EscrowLog.objects.create(
            job=job,
            action='dispute',
            amount=job.price,
            performed_by=request.user,
            description=f'Dispute raised: {reason[:100]}'
        )

        # Notify admins
        send_mail(
            'New Job Dispute',
            f'Job "{job.title}" (ID: {job.id}) has been disputed by {request.user.username}.\n\nReason: {reason}',
            settings.DEFAULT_FROM_EMAIL,
            [admin[1] for admin in settings.ADMINS],
            fail_silently=True,
        )

        # Notify the other party
        other_party = job.hired_worker if request.user == job.client else job.client
        if other_party:
            Notification.objects.create(
                recipient=other_party,
                notification_type='dispute',
                title='Job Disputed',
                message=f'A dispute has been raised on job: {job.title}. Admin will review.',
                link=f'/job/{job.id}/'
            )

        messages.warning(request, "Job has been marked as disputed. Admin will review and contact you.")
        return redirect('job_detail', job_id=job.id)

    return render(request, 'accounts/dispute_job.html', {'job': job})


@login_required
def withdraw_funds(request, job_id):
    """Handyman withdraws funds after job completion"""
    job = get_object_or_404(Job, id=job_id)

    # Verify handyman is the hired worker
    if request.user != job.hired_worker:
        messages.error(request, "Only the hired handyman can withdraw funds.")
        return redirect('job_detail', job_id=job.id)

    # Verify payment is released
    if job.payment_status != 'released':
        messages.error(request, "Payment has not been released yet.")
        return redirect('job_detail', job_id=job.id)

    # Check if already withdrawn
    existing_withdrawal = Withdrawal.objects.filter(
        handyman=request.user,
        job=job,
        status='completed'
    ).exists()

    if existing_withdrawal:
        messages.error(request, "You have already withdrawn funds for this job.")
        return redirect('job_detail', job_id=job.id)

    if request.method == 'POST':
        phone_number = request.POST.get('phone_number')

        # Validate phone number
        cleaned_number = re.sub(r'\D', '', phone_number)
        if len(cleaned_number) == 9:
            formatted_number = '254' + cleaned_number
        elif len(cleaned_number) == 10 and cleaned_number.startswith('0'):
            formatted_number = '254' + cleaned_number[1:]
        elif len(cleaned_number) == 12 and cleaned_number.startswith('254'):
            formatted_number = cleaned_number
        else:
            messages.error(request,
                           "Please enter a valid M-Pesa number (e.g., 712345678 or 0712345678 or 254712345678)")
            return render(request, 'accounts/withdraw_funds.html', {'job': job})

        # Create withdrawal request
        withdrawal = Withdrawal.objects.create(
            handyman=request.user,
            amount=job.price,
            phone_number=formatted_number,
            status='pending'
        )

        # Here you would integrate with M-Pesa B2C API to send money

        messages.success(request,
                         f"Withdrawal request for KES {job.price} submitted. Funds will be sent to {formatted_number}")
        return redirect('dashboard')

    return render(request, 'accounts/withdraw_funds.html', {'job': job})


# ==================== 16. NOTIFICATIONS ====================
@login_required
def notifications(request):
    """View all notifications"""
    user_notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')

    # Mark as read when viewed
    unread_count = user_notifications.filter(is_read=False).count()

    context = {
        'notifications': user_notifications,
        'unread_count': unread_count
    }
    return render(request, 'accounts/notifications.html', context)


@login_required
def mark_notification_read(request, notification_id):
    """Mark a single notification as read"""
    notification = get_object_or_404(Notification, id=notification_id, recipient=request.user)
    notification.is_read = True
    notification.save()

    if request.GET.get('redirect'):
        return redirect(request.GET.get('redirect'))
    return redirect('notifications')


@login_required
def mark_all_notifications_read(request):
    """Mark all notifications as read"""
    Notification.objects.filter(recipient=request.user, is_read=False).update(is_read=True)
    messages.success(request, "All notifications marked as read.")
    return redirect('notifications')


# ==================== 17. MESSAGING ====================
@login_required
def send_message(request):
    """Send a message to an artisan"""
    if request.method == 'POST' and request.user.is_client:
        artisan_id = request.POST.get('artisan_id')
        subject = request.POST.get('subject')
        message = request.POST.get('message')
        phone = request.POST.get('phone', '')

        artisan = get_object_or_404(User, id=artisan_id, is_handyman=True)

        try:
            # Send email to artisan
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

            # Also send a confirmation to the client
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

            messages.success(
                request,
                f"✅ Your message has been sent to {artisan.get_full_name() or artisan.username}! They will contact you soon."
            )
        except Exception as e:
            print(f"Error sending message: {e}")
            messages.error(request, "❌ Failed to send message. Please try again later.")

    return redirect('artisans_list')


# ==================== 18. M-PESA CALLBACK ====================
@csrf_exempt
def mpesa_callback(request):
    """M-Pesa API callback URL"""
    if request.method == 'POST':
        try:
            # Get the callback data
            data = json.loads(request.body.decode('utf-8'))
            print("M-Pesa Callback Data:", json.dumps(data, indent=2))

            # Extract transaction details
            if 'Body' in data and 'stkCallback' in data['Body']:
                callback = data['Body']['stkCallback']
                checkout_id = callback['CheckoutRequestID']
                result_code = callback['ResultCode']
                result_desc = callback['ResultDesc']

                # Find the pending transaction
                transaction = Transaction.objects.filter(
                    mpesa_checkout_id=checkout_id,
                    transaction_status='pending'
                ).first()

                if transaction:
                    if result_code == 0:
                        # Payment successful
                        if 'CallbackMetadata' in callback:
                            metadata = callback['CallbackMetadata']['Item']
                            receipt = ''
                            for item in metadata:
                                if item.get('Name') == 'MpesaReceiptNumber':
                                    receipt = item.get('Value', '')

                            # Update transaction
                            transaction.transaction_status = 'completed'
                            transaction.mpesa_receipt = receipt
                            transaction.completed_at = timezone.now()
                            transaction.save()

                            # Update job
                            job = transaction.job
                            job.payment_status = 'escrow'
                            job.save()

                            # Create escrow log
                            EscrowLog.objects.create(
                                job=job,
                                action='payment',
                                amount=transaction.amount,
                                performed_by=job.client,
                                description=f'M-Pesa payment confirmed. Receipt: {receipt}'
                            )

                            # Notify handyman
                            if job.hired_worker:
                                Notification.objects.create(
                                    recipient=job.hired_worker,
                                    notification_type='payment',
                                    title='Payment Received',
                                    message=f'Payment of KES {transaction.amount} has been placed in escrow',
                                    link=f'/job/{job.id}/'
                                )
                    else:
                        # Payment failed
                        transaction.transaction_status = 'failed'
                        transaction.failure_reason = result_desc
                        transaction.save()

                        # Create escrow log for failure
                        EscrowLog.objects.create(
                            job=transaction.job,
                            action='payment',
                            amount=transaction.amount,
                            performed_by=transaction.job.client,
                            description=f'M-Pesa payment failed: {result_desc}'
                        )

            return JsonResponse({
                "ResultCode": 0,
                "ResultDesc": "Success"
            })
        except Exception as e:
            print(f"Error processing callback: {e}")
            return JsonResponse({
                "ResultCode": 1,
                "ResultDesc": f"Failed: {str(e)}"
            })

    return JsonResponse({
        "ResultCode": 1,
        "ResultDesc": "Method not allowed"
    })


# ==================== 19. M-PESA TIMEOUT ====================
@csrf_exempt
def mpesa_timeout(request):
    """M-Pesa timeout URL"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            print("M-Pesa Timeout Data:", data)

            # Handle timeout logic here
            # Find pending transactions and mark as failed

            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
        except Exception as e:
            print(f"Error processing timeout: {e}")
            return JsonResponse({"ResultCode": 1, "ResultDesc": "Failed"})
    return JsonResponse({"ResultCode": 1, "ResultDesc": "Method not allowed"})


# ==================== 20. M-PESA RESULT ====================
@csrf_exempt
def mpesa_result(request):
    """M-Pesa result URL for B2C transactions"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body.decode('utf-8'))
            print("M-Pesa Result Data:", data)

            # Handle B2C result here (payments to handymen)
            # Update withdrawal requests based on result

            return JsonResponse({"ResultCode": 0, "ResultDesc": "Success"})
        except Exception as e:
            print(f"Error processing result: {e}")
            return JsonResponse({"ResultCode": 1, "ResultDesc": "Failed"})
    return JsonResponse({"ResultCode": 1, "ResultDesc": "Method not allowed"})