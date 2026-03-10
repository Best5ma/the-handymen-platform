from django import template
from django.db.models import Count
from ..models import Profile, Job

register = template.Library()


@register.simple_tag
def get_location_cloud():
    """Get all locations with counts for handymen and jobs"""
    handyman_locations = Profile.objects.exclude(location='').values('location').annotate(
        count=Count('user', filter=models.Q(user__is_handyman=True, user__profile__is_verified=True))
    ).order_by('-count')[:10]

    job_locations = Job.objects.filter(status='open').exclude(location='').values('location').annotate(
        count=Count('id')
    ).order_by('-count')[:10]

    return {
        'handyman_locations': handyman_locations,
        'job_locations': job_locations,
    }