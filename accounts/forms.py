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

# 2. PROFILE EDIT FORM (With Photo & CV)
class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['skills', 'experience_years', 'bio', 'cv', 'profile_photo']
        widgets = {
            'skills': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Plumber, Electrician'}),
            'experience_years': forms.NumberInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'cv': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'profile_photo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

# 3. JOB POSTING FORM
class JobForm(forms.ModelForm):
    class Meta:
        model = Job
        fields = ['title', 'description', 'location', 'price']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'location': forms.TextInput(attrs={'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control'}),
        }

# 4. BIDDING FORM
class BidForm(forms.ModelForm):
    class Meta:
        model = Bid
        fields = ['bid_amount', 'message']
        widgets = {
            'bid_amount': forms.NumberInput(attrs={'class': 'form-control'}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

# 5. REVIEW FORM
class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'comment']
        widgets = {
            'rating': forms.Select(attrs={'class': 'form-select'}),
            'comment': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }