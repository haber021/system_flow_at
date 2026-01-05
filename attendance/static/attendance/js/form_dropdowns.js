/**
 * Form Dropdowns - Dynamic Data Loading
 * Reusable functions to populate form dropdowns from API endpoints
 */

/**
 * Populate a dropdown select element from an API endpoint
 * @param {string} url - API endpoint URL
 * @param {string} selectId - ID of the select element
 * @param {string} defaultOption - Default option text (default: '-- Select --')
 * @param {function} onComplete - Optional callback when population is complete
 */
async function populateDropdown(url, selectId, defaultOption = '-- Select --', onComplete = null) {
    const select = document.getElementById(selectId);
    if (!select) {
        console.warn(`Select element with ID '${selectId}' not found`);
        return;
    }
    
    try {
        // Show loading state
        select.disabled = true;
        const originalHTML = select.innerHTML;
        select.innerHTML = `<option value="">Loading...</option>`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        if (data.success) {
            // Clear existing options
            select.innerHTML = `<option value="">${defaultOption}</option>`;
            
            // Add options from API
            const items = data.courses || data.sections || data.advisers || data.instructors || [];
            items.forEach(item => {
                const option = document.createElement('option');
                option.value = item.id;
                option.textContent = item.display || item.name || item.code || '';
                select.appendChild(option);
            });
            
            // Re-enable select
            select.disabled = false;
            
            // Call completion callback if provided
            if (onComplete && typeof onComplete === 'function') {
                onComplete(items);
            }
        } else {
            // Show error
            select.innerHTML = `<option value="">Error loading options</option>`;
            console.error(`Error loading ${selectId}:`, data.error);
        }
    } catch (error) {
        console.error(`Error loading ${selectId}:`, error);
        select.innerHTML = `<option value="">Error loading options</option>`;
    } finally {
        select.disabled = false;
    }
}

/**
 * Populate multiple dropdowns at once
 * @param {Array} dropdowns - Array of {url, selectId, defaultOption} objects
 * @param {function} onComplete - Optional callback when all are complete
 */
async function populateMultipleDropdowns(dropdowns, onComplete = null) {
    const promises = dropdowns.map(dropdown => 
        populateDropdown(dropdown.url, dropdown.selectId, dropdown.defaultOption)
    );
    
    try {
        await Promise.all(promises);
        if (onComplete && typeof onComplete === 'function') {
            onComplete();
        }
    } catch (error) {
        console.error('Error populating multiple dropdowns:', error);
    }
}

/**
 * Setup modal to populate dropdowns when shown
 * @param {string} modalId - ID of the modal element
 * @param {Array} dropdowns - Array of {url, selectId, defaultOption} objects
 */
function setupModalDropdowns(modalId, dropdowns) {
    const modalElement = document.getElementById(modalId);
    if (!modalElement) {
        console.warn(`Modal element with ID '${modalId}' not found`);
        return;
    }
    
    modalElement.addEventListener('show.bs.modal', function() {
        // Populate all dropdowns when modal opens
        populateMultipleDropdowns(dropdowns);
    });
}

