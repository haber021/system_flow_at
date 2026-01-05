"""
Email utility functions for sending emails in the attendance system.
"""
import logging
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from django.core.mail import EmailMessage, EmailMultiAlternatives, get_connection
from django.conf import settings
from django.utils import timezone
from .models import EmailLog

logger = logging.getLogger(__name__)

# ANSI color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def _print_email_info(status, recipient, subject, student_name, duration=None, error=None):
    """Print email sending information to terminal with colors"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if status == 'SENDING':
        print(f"{Colors.CYAN}[{timestamp}] {Colors.BOLD}→{Colors.RESET} {Colors.BLUE}Sending email...{Colors.RESET}")
        print(f"   {Colors.CYAN}Recipient:{Colors.RESET} {recipient}")
        print(f"   {Colors.CYAN}Student:{Colors.RESET} {student_name}")
        print(f"   {Colors.CYAN}Subject:{Colors.RESET} {subject}")
    elif status == 'SUCCESS':
        duration_str = f" ({duration:.2f}s)" if duration else ""
        print(f"{Colors.GREEN}[{timestamp}] {Colors.BOLD}✓{Colors.RESET} {Colors.GREEN}Email sent successfully{duration_str}{Colors.RESET}")
        print(f"   {Colors.GREEN}To:{Colors.RESET} {recipient}")
        print(f"   {Colors.GREEN}Student:{Colors.RESET} {student_name}")
        print(f"   {Colors.GREEN}Subject:{Colors.RESET} {subject}")
    elif status == 'FAILED':
        duration_str = f" ({duration:.2f}s)" if duration else ""
        print(f"{Colors.RED}[{timestamp}] {Colors.BOLD}✗{Colors.RESET} {Colors.RED}Email failed{duration_str}{Colors.RESET}")
        print(f"   {Colors.RED}To:{Colors.RESET} {recipient}")
        print(f"   {Colors.RED}Student:{Colors.RESET} {student_name}")
        print(f"   {Colors.RED}Subject:{Colors.RESET} {subject}")
        if error:
            print(f"   {Colors.RED}Error:{Colors.RESET} {error}")
    print()  # Empty line for readability


def send_attendance_email(
    student,
    email_to,
    subject,
    message_body,
    email_type='SEMESTER',
    email_cc=None,
    email_bcc=None,
    html_message=None,
    silent=False,
    check_duplicate=True,
    duplicate_window_hours=24
):
    """
    Send an attendance-related email and log it in the database.
    
    Args:
        student: Student model instance
        email_to: Recipient email address (string or list)
        subject: Email subject line
        message_body: Plain text email body
        email_type: Type of email (SEMESTER, WARNING, DAILY, CUSTOM)
        email_cc: CC recipients (string or list, optional)
        email_bcc: BCC recipients (string or list, optional)
        html_message: HTML version of the email (optional)
        silent: If True, don't print to terminal (default: False)
        check_duplicate: If True, check for duplicate emails before sending (default: True)
        duplicate_window_hours: Hours to look back for duplicates (default: 24)
    
    Returns:
        tuple: (success: bool, email_log: EmailLog instance, error_message: str)
        Note: If duplicate is found, returns (True, existing_email_log, "Duplicate email - already sent")
    """
    start_time = time.time()
    
    # Convert single email to list for consistency
    if isinstance(email_to, str):
        email_to_list = [email_to]
        email_to_display = email_to
        email_to_normalized = email_to.strip().lower()
    else:
        email_to_list = email_to
        email_to_display = ', '.join(email_to_list)
        # For duplicate check, use the first email address
        email_to_normalized = email_to_list[0].strip().lower() if email_to_list else ''
    
    # Check for duplicate emails before sending
    if check_duplicate:
        # Look for recently sent emails with same student, subject, and email_type
        time_threshold = timezone.now() - timedelta(hours=duplicate_window_hours)
        duplicate_query = EmailLog.objects.filter(
            student=student,
            subject=subject,
            email_type=email_type,
            status='SENT',
            sent_at__isnull=False,
            sent_at__gte=time_threshold
        ).order_by('-sent_at')
        
        duplicate_email = duplicate_query.first()
        
        if duplicate_email:
            # Check if the email_to matches (case-insensitive)
            # Extract first email from comma-separated list if multiple emails
            duplicate_email_to = duplicate_email.email_to.split(',')[0].strip().lower()
            if duplicate_email_to == email_to_normalized:
                duration = time.time() - start_time
                sent_time_str = duplicate_email.sent_at.strftime('%Y-%m-%d %H:%M:%S') if duplicate_email.sent_at else 'previously'
                duplicate_msg = f"Duplicate email - already sent at {sent_time_str}"
                
                if not silent:
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    print(f"{Colors.YELLOW}[{timestamp}] {Colors.BOLD}⚠{Colors.RESET} {Colors.YELLOW}Duplicate email skipped{Colors.RESET}")
                    print(f"   {Colors.YELLOW}Recipient:{Colors.RESET} {email_to_display}")
                    print(f"   {Colors.YELLOW}Student:{Colors.RESET} {student.name}")
                    print(f"   {Colors.YELLOW}Subject:{Colors.RESET} {subject}")
                    print(f"   {Colors.YELLOW}Reason:{Colors.RESET} {duplicate_msg}")
                    print()
                
                logger.info(f"Duplicate email skipped for {email_to_display} to student {student.name}: {duplicate_msg}")
                # Return success=True but with duplicate message to indicate it was skipped
                return True, duplicate_email, duplicate_msg
    
    # Convert CC and BCC to lists if provided as strings
    cc_list = []
    if email_cc:
        if isinstance(email_cc, str):
            # Handle comma-separated emails
            cc_list = [email.strip() for email in email_cc.split(',') if email.strip()]
        else:
            cc_list = email_cc
    
    bcc_list = []
    if email_bcc:
        if isinstance(email_bcc, str):
            # Handle comma-separated emails
            bcc_list = [email.strip() for email in email_bcc.split(',') if email.strip()]
        else:
            bcc_list = email_bcc
    
    # Create email log entry
    email_log = EmailLog.objects.create(
        student=student,
        email_to=', '.join(email_to_list) if isinstance(email_to_list, list) else email_to,
        email_cc=', '.join(cc_list) if cc_list else '',
        email_bcc=', '.join(bcc_list) if bcc_list else '',
        subject=subject,
        message_body=message_body,
        email_type=email_type,
        status='PENDING',
    )
    
    # Display sending information
    if not silent:
        _print_email_info('SENDING', email_to_display, subject, student.name)
    
    try:
        # Create email connection once for better performance
        connection = get_connection(
            username=settings.EMAIL_HOST_USER,
            password=settings.EMAIL_HOST_PASSWORD,
            fail_silently=False,
        )
        
        # Create email message
        if html_message:
            # Use EmailMultiAlternatives for HTML emails
            email = EmailMultiAlternatives(
                subject=subject,
                body=message_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=email_to_list,
                cc=cc_list if cc_list else None,
                bcc=bcc_list if bcc_list else None,
                connection=connection,
            )
            email.attach_alternative(html_message, "text/html")
        else:
            # Use EmailMessage for plain text emails
            email = EmailMessage(
                subject=subject,
                body=message_body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=email_to_list,
                cc=cc_list if cc_list else None,
                bcc=bcc_list if bcc_list else None,
                connection=connection,
            )
        
        # Send email
        email.send(fail_silently=False)
        connection.close()
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Update email log on success
        email_log.status = 'SENT'
        email_log.sent_at = timezone.now()
        email_log.error_message = ''
        email_log.save()
        
        # Display success information
        if not silent:
            _print_email_info('SUCCESS', email_to_display, subject, student.name, duration)
        
        logger.info(f"Email sent successfully to {email_to} for student {student.name} in {duration:.2f}s")
        return True, email_log, None
        
    except Exception as e:
        # Calculate duration
        duration = time.time() - start_time
        
        # Update email log on failure
        error_msg = str(e)
        email_log.status = 'FAILED'
        email_log.error_message = error_msg
        email_log.save()
        
        # Display failure information
        if not silent:
            _print_email_info('FAILED', email_to_display, subject, student.name, duration, error_msg)
        
        logger.error(f"Failed to send email to {email_to} for student {student.name}: {error_msg}")
        return False, email_log, error_msg


def resend_email(email_log, silent=False):
    """
    Resend an email from an existing EmailLog entry.
    
    Args:
        email_log: EmailLog model instance
        silent: If True, don't print to terminal (default: False)
    
    Returns:
        tuple: (success: bool, error_message: str)
    """
    start_time = time.time()
    
    if not silent:
        _print_email_info('SENDING', email_log.email_to, email_log.subject, email_log.student.name)
    
    try:
        # Parse email addresses
        email_to_list = [email.strip() for email in email_log.email_to.split(',') if email.strip()]
        cc_list = [email.strip() for email in email_log.email_cc.split(',')] if email_log.email_cc else []
        bcc_list = [email.strip() for email in email_log.email_bcc.split(',')] if email_log.email_bcc else []
        
        # Create email connection
        connection = get_connection(
            username=settings.EMAIL_HOST_USER,
            password=settings.EMAIL_HOST_PASSWORD,
            fail_silently=False,
        )
        
        # Create email message
        email = EmailMessage(
            subject=email_log.subject,
            body=email_log.message_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=email_to_list,
            cc=cc_list if cc_list else None,
            bcc=bcc_list if bcc_list else None,
            connection=connection,
        )
        
        # Send email
        email.send(fail_silently=False)
        connection.close()
        
        duration = time.time() - start_time
        
        # Update email log on success
        email_log.status = 'SENT'
        email_log.sent_at = timezone.now()
        email_log.error_message = ''
        email_log.save()
        
        if not silent:
            _print_email_info('SUCCESS', email_log.email_to, email_log.subject, email_log.student.name, duration)
        
        logger.info(f"Email resent successfully to {email_log.email_to} for student {email_log.student.name} in {duration:.2f}s")
        return True, None
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        email_log.status = 'FAILED'
        email_log.error_message = error_msg
        email_log.save()
        
        if not silent:
            _print_email_info('FAILED', email_log.email_to, email_log.subject, email_log.student.name, duration, error_msg)
        
        logger.error(f"Failed to resend email to {email_log.email_to} for student {email_log.student.name}: {error_msg}")
        return False, error_msg


def send_emails_bulk(email_tasks, max_workers=5, silent=False):
    """
    Send multiple emails concurrently using threading for faster processing.
    
    Args:
        email_tasks: List of tuples (student, email_to, subject, message_body, kwargs)
        max_workers: Maximum number of concurrent threads (default: 5)
        silent: If True, don't print to terminal (default: False)
    
    Returns:
        tuple: (success_count: int, failed_count: int, results: list)
    """
    if not email_tasks:
        return 0, 0, []
    
    total_emails = len(email_tasks)
    start_time = time.time()
    
    if not silent:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}[{timestamp}] Starting bulk email sending{Colors.RESET}")
        print(f"{Colors.CYAN}Total emails to send: {total_emails}{Colors.RESET}")
        print(f"{Colors.CYAN}Max concurrent workers: {max_workers}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")
    
    success_count = 0
    failed_count = 0
    results = []
    
    def send_single_email(task):
        """Wrapper function to send a single email"""
        student, email_to, subject, message_body, kwargs = task
        kwargs['silent'] = silent
        return send_attendance_email(
            student=student,
            email_to=email_to,
            subject=subject,
            message_body=message_body,
            **kwargs
        )
    
    # Use ThreadPoolExecutor for concurrent email sending
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_task = {
            executor.submit(send_single_email, task): task 
            for task in email_tasks
        }
        
        # Process completed tasks
        for future in as_completed(future_to_task):
            try:
                success, email_log, error_message = future.result()
                if success:
                    success_count += 1
                else:
                    failed_count += 1
                results.append((success, email_log, error_message))
            except Exception as e:
                failed_count += 1
                results.append((False, None, str(e)))
                if not silent:
                    task = future_to_task[future]
                    student = task[0]
                    _print_email_info('FAILED', task[1], task[2], student.name, error=str(e))
    
    total_duration = time.time() - start_time
    
    if not silent:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}[{timestamp}] Bulk email sending completed{Colors.RESET}")
        print(f"{Colors.GREEN}Success: {success_count}{Colors.RESET} | {Colors.RED}Failed: {failed_count}{Colors.RESET} | {Colors.CYAN}Total: {total_emails}{Colors.RESET}")
        print(f"{Colors.CYAN}Total time: {total_duration:.2f}s{Colors.RESET}")
        print(f"{Colors.CYAN}Average time per email: {total_duration/total_emails:.2f}s{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")
    
    return success_count, failed_count, results

