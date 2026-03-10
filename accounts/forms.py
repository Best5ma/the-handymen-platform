from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from .models import Profile, Job, Bid, Review

User = get_user_model()

# 1. SIGNUP FORM
class HandymanSignUpForm(UserCreationForm):
    is_handyman = forms.BooleanField(required=False, label="Register as a Handyman/Artisan")
    is_client = forms.BooleanField(required=False, label="Register as a Client (to hire)")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = UserCreationForm.Meta.fields + ('email', 'is_handyman', 'is_client')

# 2. PROFILE EDIT FORM (With location field)
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['skills', 'experience_years', 'bio', 'cv', 'profile_photo', 'location', 'phone_number']
        widgets = {
            'skills': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Plumber, Electrician'}),
            'experience_years': forms.NumberInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Tell clients about yourself...'}),
            'cv': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'profile_photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Nairobi, Ruiru, Mombasa'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 0712345678'}),
        }

# 3. JOB POSTING FORM (with location)
class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ['title', 'description', 'location', 'price']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Fix leaking kitchen pipe'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Describe the job in detail...'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Nairobi, Ruiru'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Amount in KES'}),
        }

# 4. BIDDING FORM
class BidForm(forms.ModelForm):
    class Meta:
        model = Bid
        fields = ['bid_amount', 'message']
        widgets = {
            'bid_amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Your bid amount in KES'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Why should you be hired?'}),
        }

# 5. REVIEW FORM
class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Share your experience...'}),
        }