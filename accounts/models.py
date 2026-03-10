from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    is_handyman = models.BooleanField(default=False)
    is_client = models.BooleanField(default=False)
    is_email_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.username


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    bio = models.TextField(max_length=500, blank=True)
    skills = models.CharField(max_length=255, blank=True)
    experience_years = models.IntegerField(default=0)
    cv = models.FileField(upload_to='cvs/', blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    profile_photo = models.ImageField(upload_to='profile_photos/', null=True, blank=True)
    location = models.CharField(max_length=255, blank=True)  # Location field
    phone_number = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


class Job(models.Model):
    PAYMENT_CHOICES = [
        ('unpaid', 'Unpaid'),
        ('pending', 'Pending Payment'),
        ('escrow', 'Held in Escrow'),
        ('released', 'Released'),
        ('refunded', 'Refunded')
    ]

    STATUS_CHOICES = [
        ('open', 'Open for Bids'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('disputed', 'Disputed')
    ]

    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='jobs')
    title = models.CharField(max_length=200)
    description = models.TextField()
    location = models.CharField(max_length=255)  # Job location
    price = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    is_completed = models.BooleanField(default=False)
    applicants = models.ManyToManyField(User, related_name='applied_jobs', blank=True)
    hired_worker = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='hired_jobs')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='unpaid')

    # M-Pesa transaction details
    mpesa_transaction_id = models.CharField(max_length=100, blank=True, null=True)
    mpesa_receipt = models.CharField(max_length=100, blank=True, null=True)
    payment_date = models.DateTimeField(blank=True, null=True)

    # Completion tracking
    completion_requested = models.BooleanField(default=False)
    completion_date = models.DateTimeField(blank=True, null=True)
    client_confirmed = models.BooleanField(default=False)
    handyman_confirmed = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']


class Bid(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='bids')
    handyman = models.ForeignKey(User, on_delete=models.CASCADE, related_name='my_bids')
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.handyman.username} - KES {self.bid_amount}"

    class Meta:
        ordering = ['-bid_amount']


class Review(models.Model):
    client = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_given')
    handyman = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reviews_received')
    rating = models.IntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client.username} → {self.handyman.username}: {self.rating}★"

    class Meta:
        ordering = ['-created_at']
        unique_together = ['client', 'handyman']


class Transaction(models.Model):
    TRANSACTION_TYPES = [
        ('payment', 'Payment to Escrow'),
        ('release', 'Release to Handyman'),
        ('refund', 'Refund to Client'),
        ('withdrawal', 'Handyman Withdrawal'),
    ]

    TRANSACTION_STATUS = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    transaction_status = models.CharField(max_length=20, choices=TRANSACTION_STATUS, default='pending')

    # M-Pesa specific fields
    mpesa_receipt = models.CharField(max_length=100, blank=True, null=True)
    mpesa_checkout_id = models.CharField(max_length=100, blank=True, null=True)
    mpesa_merchant_request_id = models.CharField(max_length=100, blank=True, null=True)

    # Customer details
    phone_number = models.CharField(max_length=15)
    customer_name = models.CharField(max_length=100, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    # Additional info
    description = models.TextField(blank=True)
    failure_reason = models.TextField(blank=True)

    def __str__(self):
        return f"{self.transaction_type} - {self.mpesa_receipt or 'Pending'} - KES {self.amount}"

    class Meta:
        ordering = ['-created_at']


class Notification(models.Model):
    NOTIFICATION_TYPES = [
        ('bid', 'New Bid'),
        ('hire', 'You were hired'),
        ('payment', 'Payment Update'),
        ('review', 'New Review'),
        ('completion', 'Job Completion'),
        ('dispute', 'Dispute Filed'),
        ('system', 'System Update'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    link = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.recipient.username} - {self.title}"

    class Meta:
        ordering = ['-created_at']


class Dispute(models.Model):
    DISPUTE_STATUS = [
        ('open', 'Open'),
        ('under_review', 'Under Review'),
        ('resolved', 'Resolved'),
        ('dismissed', 'Dismissed'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='disputes')
    raised_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='disputes_raised')
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=DISPUTE_STATUS, default='open')
    resolution = models.TextField(blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name='disputes_resolved')
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Dispute on {self.job.title} - {self.status}"

    class Meta:
        ordering = ['-created_at']


class Withdrawal(models.Model):
    WITHDRAWAL_STATUS = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    handyman = models.ForeignKey(User, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    phone_number = models.CharField(max_length=15)
    status = models.CharField(max_length=20, choices=WITHDRAWAL_STATUS, default='pending')

    # M-Pesa B2C details
    mpesa_receipt = models.CharField(max_length=100, blank=True, null=True)
    mpesa_transaction_id = models.CharField(max_length=100, blank=True, null=True)

    # Timestamps
    requested_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    # Additional info
    failure_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.handyman.username} - KES {self.amount} - {self.status}"

    class Meta:
        ordering = ['-requested_at']


class EscrowLog(models.Model):
    ACTION_TYPES = [
        ('payment', 'Payment Received'),
        ('release', 'Payment Released'),
        ('refund', 'Payment Refunded'),
        ('hold', 'Payment Held'),
        ('dispute', 'Dispute Opened'),
    ]

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='escrow_logs')
    action = models.CharField(max_length=20, choices=ACTION_TYPES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    performed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    # Related transaction
    transaction = models.ForeignKey(Transaction, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.job.title} - {self.action} - KES {self.amount}"

    class Meta:
        ordering = ['-created_at']
