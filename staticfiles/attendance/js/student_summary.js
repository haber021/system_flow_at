/**
 * Student Summary Page - Bulk Email Selection Functionality
 * Handles checkbox selection, select all/deselect all, and bulk email sending
 */

// Update selected count and hidden inputs
function updateSelectedCount() {
    const checkboxes = document.querySelectorAll('.student-checkbox:checked');
    const count = checkboxes.length;
    const selectedCountElement = document.getElementById('selectedCount');
    const bulkSendBtn = document.getElementById('bulkSendBtn');
    
    if (selectedCountElement) {
        selectedCountElement.textContent = count + ' student' + (count !== 1 ? 's' : '') + ' selected';
    }
    
    if (bulkSendBtn) {
        bulkSendBtn.disabled = count === 0;
    }
    
    // Update hidden inputs for selected students
    const container = document.getElementById('selectedStudentsContainer');
    if (container) {
        container.innerHTML = '';
        checkboxes.forEach(checkbox => {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'student_ids';
            input.value = checkbox.value;
            container.appendChild(input);
        });
    }
}

// Select all students across all subjects
function selectAllStudents() {
    document.querySelectorAll('.student-checkbox').forEach(cb => {
        cb.checked = true;
    });
    document.querySelectorAll('.select-all-checkbox').forEach(cb => {
        cb.checked = true;
    });
    updateSelectedCount();
}

// Deselect all students across all subjects
function deselectAllStudents() {
    document.querySelectorAll('.student-checkbox').forEach(cb => {
        cb.checked = false;
    });
    document.querySelectorAll('.select-all-checkbox').forEach(cb => {
        cb.checked = false;
    });
    updateSelectedCount();
}

// Show loading modal for email sending
function showEmailLoadingModal(count) {
    const modalHtml = `
        <div class="email-loading-overlay" id="emailLoadingOverlay">
            <div class="email-loading-modal">
                <div class="email-loading-header">
                    <h4><i class="bi bi-envelope-fill"></i> Sending Email Reports</h4>
                </div>
                <div class="email-loading-body">
                    <div class="text-center mb-4">
                        <div class="spinner-border text-primary" role="status" style="width: 4rem; height: 4rem;">
                            <span class="visually-hidden">Loading...</span>
                        </div>
                    </div>
                    <div class="loading-info">
                        <p class="mb-2"><strong>Sending email reports to <span id="loadingCount">${count}</span> student${count !== 1 ? 's' : ''}...</strong></p>
                        <p class="text-muted mb-3">Please wait while we process your request. This may take a few moments.</p>
                        <div class="progress mb-2" style="height: 25px;">
                            <div class="progress-bar progress-bar-striped progress-bar-animated bg-primary" 
                                 role="progressbar" 
                                 style="width: 100%" 
                                 aria-valuenow="100" 
                                 aria-valuemin="0" 
                                 aria-valuemax="100">
                                Processing...
                            </div>
                        </div>
                        <div class="loading-details mt-3">
                            <p class="mb-1"><i class="bi bi-info-circle"></i> <small>Emails are being sent concurrently for faster processing</small></p>
                            <p class="mb-0"><i class="bi bi-clock"></i> <small>Check the terminal/console for detailed sending progress</small></p>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    // Remove existing modal if any
    const existing = document.getElementById('emailLoadingOverlay');
    if (existing) {
        existing.remove();
    }
    
    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);
    
    // Prevent body scroll
    document.body.style.overflow = 'hidden';
}

// Hide loading modal
function hideEmailLoadingModal() {
    const overlay = document.getElementById('emailLoadingOverlay');
    if (overlay) {
        overlay.remove();
    }
    document.body.style.overflow = '';
}

// Confirm bulk send before submitting form
function confirmBulkSend() {
    const count = document.querySelectorAll('.student-checkbox:checked').length;
    if (count === 0) {
        alert('Please select at least one student.');
        return false;
    }
    
    const confirmed = confirm(`Are you sure you want to send email reports to ${count} student${count !== 1 ? 's' : ''}?`);
    if (confirmed) {
        // Show loading modal
        showEmailLoadingModal(count);
        
        // Disable submit button to prevent double submission
        const submitBtn = document.getElementById('bulkSendBtn');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Sending...';
        }
    }
    
    return confirmed;
}

// Initialize event listeners on page load
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to all student checkboxes
    document.querySelectorAll('.student-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', updateSelectedCount);
    });
    
    // Add event listeners to select-all checkboxes (per subject)
    document.querySelectorAll('.select-all-checkbox').forEach(selectAll => {
        const subjectId = selectAll.getAttribute('data-subject-id');
        selectAll.addEventListener('change', function() {
            const isChecked = this.checked;
            document.querySelectorAll(`.student-checkbox[data-subject-id="${subjectId}"]`).forEach(cb => {
                cb.checked = isChecked;
            });
            updateSelectedCount();
        });
    });
    
    // Update count when individual checkboxes change (to update select-all state)
    document.querySelectorAll('.student-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const subjectId = this.getAttribute('data-subject-id');
            const subjectCheckboxes = document.querySelectorAll(`.student-checkbox[data-subject-id="${subjectId}"]`);
            const checkedCheckboxes = document.querySelectorAll(`.student-checkbox[data-subject-id="${subjectId}"]:checked`);
            const selectAll = document.querySelector(`.select-all-checkbox[data-subject-id="${subjectId}"]`);
            if (selectAll) {
                selectAll.checked = subjectCheckboxes.length === checkedCheckboxes.length && subjectCheckboxes.length > 0;
            }
            updateSelectedCount();
        });
    });
    
    // Initial count update
    updateSelectedCount();
});

