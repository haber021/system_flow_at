from .models import Student, EnrollmentRequest

def adviser_context(request):
    """Context processor to add adviser information to all templates"""
    is_adviser = False
    adviser_name = None
    pending_enrollments = 0
    
    if request.user.is_authenticated:
        # Check if user is an adviser (has adviser_profile and assigned students)
        if hasattr(request.user, 'adviser_profile'):
            has_assigned_students = Student.objects.filter(
                adviser=request.user.adviser_profile
            ).exists()
            
            if has_assigned_students:
                is_adviser = True
                adviser_name = request.user.adviser_profile.name
                # Count pending enrollment requests for subjects where instructor belongs to this adviser
                pending_enrollments = EnrollmentRequest.objects.filter(
                    status='PENDING',
                    subject__instructor__adviser=request.user.adviser_profile
                ).count()
            elif request.user.is_staff or request.user.is_superuser:
                # Staff/superuser who is not an active adviser - show all pending requests
                pending_enrollments = EnrollmentRequest.objects.filter(status='PENDING').count()
        elif request.user.is_staff or request.user.is_superuser:
            # Staff/superuser (not an adviser) - show all pending enrollment requests
            pending_enrollments = EnrollmentRequest.objects.filter(status='PENDING').count()
    
    return {
        'is_adviser': is_adviser,
        'adviser_name': adviser_name if is_adviser else None,
        'pending_enrollments': pending_enrollments,
    }

