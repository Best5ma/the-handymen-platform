from django import template
from django.db.models import Count, Q
from ..models import Profile, Job

register = template.Library()

@register.simple_tag
def get_location_cloud():
    """Get all locations with counts for handymen and jobs"""
    try:
        # Get handyman locations
        handyman_locations = Profile.objects.exclude(
            location=''
        ).values('location').annotate(
            count=Count('user', filter=Q(user__is_handyman=True, user__profile__is_verified=True))
        ).order_by('-count')[:10]
        
        # Get job locations
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
        
        return {
            'handyman_locations': formatted_handyman,
            'job_locations': formatted_jobs,
        }
    except Exception as e:
        # Return empty data if there's an error
        return {
            'handyman_locations': [],
            'job_locations': [],
        }