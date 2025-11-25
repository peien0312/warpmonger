/**
 * Codex Tooltip System
 * Handles tooltip display for codex terms on both desktop (hover) and mobile (tap)
 */

(function() {
    'use strict';

    // Cache for codex entries to avoid repeated API calls
    const codexCache = {};

    // Currently active tooltip element
    let activeTooltip = null;

    // Detect if device supports touch
    const isTouchDevice = 'ontouchstart' in window || navigator.maxTouchPoints > 0;

    // Tooltip show delay for desktop (ms)
    const HOVER_DELAY = 300;

    // Hover timeout reference
    let hoverTimeout = null;

    /**
     * Fetch codex entry data from API
     */
    async function fetchCodexEntry(slug) {
        // Return cached entry if available
        if (codexCache[slug]) {
            return codexCache[slug];
        }

        try {
            const response = await fetch(`/api/codex/${slug}`);
            if (!response.ok) {
                throw new Error('Entry not found');
            }
            const data = await response.json();
            // Cache the result
            codexCache[slug] = data.entry;
            return data.entry;
        } catch (error) {
            console.error('Error fetching codex entry:', error);
            return null;
        }
    }

    /**
     * Create and position tooltip element
     */
    function createTooltip(entry, targetElement) {
        // Remove any existing tooltip
        removeTooltip();

        const tooltip = document.createElement('div');
        tooltip.className = 'codex-tooltip';
        tooltip.innerHTML = `
            <button class="codex-tooltip-close" aria-label="Close">&times;</button>
            <div class="codex-tooltip-title">${entry.title}</div>
            <div class="codex-tooltip-content">${truncateText(entry.content, 200)}</div>
            <a href="/codex/${entry.slug}" class="codex-tooltip-link">Read more &rarr;</a>
        `;

        document.body.appendChild(tooltip);

        // Position the tooltip
        positionTooltip(tooltip, targetElement);

        // Add close button handler
        const closeBtn = tooltip.querySelector('.codex-tooltip-close');
        closeBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            removeTooltip();
        });

        // Prevent tooltip click from closing it
        tooltip.addEventListener('click', (e) => {
            e.stopPropagation();
        });

        activeTooltip = tooltip;
        return tooltip;
    }

    /**
     * Position tooltip relative to target element
     */
    function positionTooltip(tooltip, targetElement) {
        const targetRect = targetElement.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const scrollY = window.scrollY;
        const padding = 10;

        // Calculate horizontal position
        let left = targetRect.left;

        // Adjust if tooltip would overflow right edge
        if (left + tooltipRect.width > viewportWidth - padding) {
            left = viewportWidth - tooltipRect.width - padding;
        }

        // Ensure it doesn't go off left edge
        if (left < padding) {
            left = padding;
        }

        // Calculate vertical position - prefer above, fallback to below
        let top;
        const spaceAbove = targetRect.top;
        const spaceBelow = viewportHeight - targetRect.bottom;

        if (spaceAbove >= tooltipRect.height + padding) {
            // Position above
            top = targetRect.top - tooltipRect.height - 10;
            tooltip.classList.add('tooltip-above');
            tooltip.classList.remove('tooltip-below');
        } else {
            // Position below
            top = targetRect.bottom + 10;
            tooltip.classList.add('tooltip-below');
            tooltip.classList.remove('tooltip-above');
        }

        tooltip.style.left = `${left}px`;
        tooltip.style.top = `${top}px`;
    }

    /**
     * Remove active tooltip
     */
    function removeTooltip() {
        if (activeTooltip) {
            activeTooltip.remove();
            activeTooltip = null;
        }
    }

    /**
     * Truncate text to specified length
     */
    function truncateText(text, maxLength) {
        if (text.length <= maxLength) return text;
        return text.substring(0, maxLength).trim() + '...';
    }

    /**
     * Handle mouse enter on codex term (desktop)
     */
    async function handleMouseEnter(e) {
        if (isTouchDevice) return;

        const target = e.target;
        const slug = target.dataset.codex;

        if (!slug) return;

        // Clear any pending timeout
        if (hoverTimeout) {
            clearTimeout(hoverTimeout);
        }

        // Delay before showing tooltip
        hoverTimeout = setTimeout(async () => {
            const entry = await fetchCodexEntry(slug);
            if (entry) {
                createTooltip(entry, target);
            }
        }, HOVER_DELAY);
    }

    /**
     * Handle mouse leave on codex term (desktop)
     */
    function handleMouseLeave(e) {
        if (isTouchDevice) return;

        // Clear pending timeout
        if (hoverTimeout) {
            clearTimeout(hoverTimeout);
            hoverTimeout = null;
        }

        // Check if we're moving to the tooltip itself
        const relatedTarget = e.relatedTarget;
        if (activeTooltip && activeTooltip.contains(relatedTarget)) {
            return;
        }

        removeTooltip();
    }

    /**
     * Handle click/tap on codex term
     */
    async function handleClick(e) {
        const target = e.target;
        const slug = target.dataset.codex;

        if (!slug) return;

        // On touch devices, first tap shows tooltip, second tap navigates
        if (isTouchDevice) {
            // If tooltip is already showing for this term, navigate
            if (activeTooltip && activeTooltip.querySelector('.codex-tooltip-link')?.getAttribute('href') === `/codex/${slug}`) {
                return; // Let the default link behavior happen
            }

            // Otherwise, show tooltip and prevent navigation
            e.preventDefault();
            const entry = await fetchCodexEntry(slug);
            if (entry) {
                createTooltip(entry, target);
            }
        }
        // On desktop, clicking always navigates (tooltip is on hover)
    }

    /**
     * Initialize codex tooltip system
     */
    function init() {
        // Event delegation for codex terms
        document.addEventListener('mouseenter', (e) => {
            if (e.target.classList.contains('codex-term')) {
                handleMouseEnter(e);
            }
        }, true);

        document.addEventListener('mouseleave', (e) => {
            if (e.target.classList.contains('codex-term')) {
                handleMouseLeave(e);
            }
        }, true);

        // Also handle leaving the tooltip itself
        document.addEventListener('mouseleave', (e) => {
            if (e.target.classList.contains('codex-tooltip')) {
                const relatedTarget = e.relatedTarget;
                if (!relatedTarget || !relatedTarget.classList.contains('codex-term')) {
                    removeTooltip();
                }
            }
        }, true);

        document.addEventListener('click', (e) => {
            if (e.target.classList.contains('codex-term')) {
                handleClick(e);
            } else if (activeTooltip && !activeTooltip.contains(e.target)) {
                // Click outside tooltip closes it
                removeTooltip();
            }
        });

        // Handle window resize - reposition tooltip
        window.addEventListener('resize', () => {
            if (activeTooltip) {
                removeTooltip();
            }
        });

        // Handle scroll - remove tooltip
        window.addEventListener('scroll', () => {
            if (activeTooltip) {
                removeTooltip();
            }
        }, { passive: true });

        // Handle escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && activeTooltip) {
                removeTooltip();
            }
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
