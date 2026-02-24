// Product Search with Autocomplete
(function() {
    const searchInput = document.getElementById('search-input');
    const autocompleteResults = document.getElementById('autocomplete-results');
    let debounceTimer = null;
    let currentFocus = -1;
    let suggestions = [];

    if (!searchInput || !autocompleteResults) {
        return; // Search not on this page
    }

    // Locale detection for zh-TW support
    const locale = (document.body && document.body.getAttribute('data-locale')) || 'en';
    const isZhtw = locale === 'zhtw';
    const urlPrefix = isZhtw ? '/zhtw' : '';

    // Debounce function to limit API calls
    function debounce(func, delay) {
        return function() {
            const context = this;
            const args = arguments;
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => func.apply(context, args), delay);
        };
    }

    // Fetch autocomplete suggestions
    async function fetchSuggestions(query) {
        if (query.length < 2) {
            hideAutocomplete();
            return;
        }

        try {
            const response = await fetch(`/api/products/autocomplete?q=${encodeURIComponent(query)}`);
            const data = await response.json();
            suggestions = data.suggestions || [];
            displaySuggestions(suggestions, query);
        } catch (error) {
            console.error('Error fetching autocomplete:', error);
            hideAutocomplete();
        }
    }

    // Display autocomplete suggestions
    function displaySuggestions(suggestions, query) {
        if (suggestions.length === 0) {
            hideAutocomplete();
            return;
        }

        let html = '<ul class="autocomplete-list">';
        suggestions.forEach((product, index) => {
            // Highlight matching text
            const displayName = getDisplayName(product);
            const highlightedName = highlightMatch(displayName, query);

            html += `
                <li class="autocomplete-item" data-index="${index}" data-category="${product.category}" data-slug="${product.slug}">
                    ${product.image ? `<img src="/static/images/products/${product.category}/${product.slug}/${product.image}" alt="${product.title}" class="autocomplete-image" onerror="this.style.display='none'">` : ''}
                    <div class="autocomplete-info">
                        <div class="autocomplete-title">${highlightedName}</div>
                        ${getSecondaryNames(product, query)}
                    </div>
                </li>
            `;
        });
        html += '</ul>';

        autocompleteResults.innerHTML = html;
        autocompleteResults.style.display = 'block';
        currentFocus = -1;

        // Add click handlers
        const items = autocompleteResults.querySelectorAll('.autocomplete-item');
        items.forEach(item => {
            item.addEventListener('click', function() {
                const category = this.getAttribute('data-category');
                const slug = this.getAttribute('data-slug');
                window.location.href = `${urlPrefix}/products/${category}/${slug}`;
            });

            item.addEventListener('mouseenter', function() {
                removeActiveClass();
                this.classList.add('active');
                currentFocus = parseInt(this.getAttribute('data-index'));
            });
        });
    }

    // Get display name (locale-aware)
    function getDisplayName(product) {
        if (isZhtw) {
            return product.zhtw_name || product.title || product.cn_name;
        }
        return product.title || product.cn_name || product.zhtw_name;
    }

    // Get secondary names to display
    function getSecondaryNames(product, query) {
        const names = [];
        if (product.cn_name && product.cn_name.toLowerCase().includes(query.toLowerCase())) {
            names.push(product.cn_name);
        }
        if (product.zhtw_name && product.zhtw_name.toLowerCase().includes(query.toLowerCase()) && product.zhtw_name !== product.cn_name) {
            names.push(product.zhtw_name);
        }

        if (names.length > 0) {
            return `<div class="autocomplete-secondary">${names.join(' · ')}</div>`;
        }
        return '';
    }

    // Highlight matching text
    function highlightMatch(text, query) {
        if (!text) return '';
        const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
        return text.replace(regex, '<strong>$1</strong>');
    }

    // Escape regex special characters
    function escapeRegex(str) {
        return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    // Hide autocomplete
    function hideAutocomplete() {
        autocompleteResults.style.display = 'none';
        autocompleteResults.innerHTML = '';
        currentFocus = -1;
    }

    // Remove active class from all items
    function removeActiveClass() {
        const items = autocompleteResults.querySelectorAll('.autocomplete-item');
        items.forEach(item => item.classList.remove('active'));
    }

    // Add active class to current item
    function addActiveClass() {
        const items = autocompleteResults.querySelectorAll('.autocomplete-item');
        removeActiveClass();
        if (currentFocus >= 0 && currentFocus < items.length) {
            items[currentFocus].classList.add('active');
        }
    }

    // Event listeners
    searchInput.addEventListener('input', debounce(function() {
        const query = this.value.trim();
        fetchSuggestions(query);
    }, 300));

    // Keyboard navigation
    searchInput.addEventListener('keydown', function(e) {
        const items = autocompleteResults.querySelectorAll('.autocomplete-item');

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            currentFocus++;
            if (currentFocus >= items.length) currentFocus = 0;
            addActiveClass();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            currentFocus--;
            if (currentFocus < 0) currentFocus = items.length - 1;
            addActiveClass();
        } else if (e.key === 'Enter') {
            if (currentFocus > -1 && items.length > 0) {
                e.preventDefault();
                items[currentFocus].click();
            }
        } else if (e.key === 'Escape') {
            hideAutocomplete();
            searchInput.blur();
        }
    });

    // Close autocomplete when clicking outside
    document.addEventListener('click', function(e) {
        if (!searchInput.contains(e.target) && !autocompleteResults.contains(e.target)) {
            hideAutocomplete();
        }
    });

    // Prevent form submission when selecting with Enter on autocomplete
    searchInput.closest('form').addEventListener('submit', function(e) {
        if (currentFocus > -1 && autocompleteResults.style.display === 'block') {
            e.preventDefault();
            const items = autocompleteResults.querySelectorAll('.autocomplete-item');
            if (items[currentFocus]) {
                items[currentFocus].click();
            }
        }
    });
})();
