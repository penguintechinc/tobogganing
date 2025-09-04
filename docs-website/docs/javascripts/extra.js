// Custom JavaScript for Tobogganing Documentation

document.addEventListener("DOMContentLoaded", function() {
    // Initialize Mermaid diagrams
    if (typeof mermaid !== 'undefined') {
        mermaid.initialize({
            startOnLoad: true,
            theme: 'default',
            flowchart: {
                useMaxWidth: true,
                htmlLabels: true
            }
        });
    }
    
    // Add copy functionality to code blocks
    addCopyButtons();
    
    // Add status indicators
    addStatusIndicators();
    
    // Smooth scrolling for anchor links
    addSmoothScrolling();
    
    // Add search shortcuts
    addKeyboardShortcuts();
});

// Add copy buttons to code blocks
function addCopyButtons() {
    const codeBlocks = document.querySelectorAll('pre code');
    codeBlocks.forEach(function(codeBlock) {
        const button = document.createElement('button');
        button.className = 'copy-button';
        button.textContent = '📋';
        button.title = 'Copy to clipboard';
        button.style.cssText = `
            position: absolute;
            top: 5px;
            right: 5px;
            background: var(--md-primary-fg-color);
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
            opacity: 0.7;
            transition: opacity 0.3s;
        `;
        
        button.addEventListener('click', function() {
            navigator.clipboard.writeText(codeBlock.textContent).then(function() {
                button.textContent = '✅';
                setTimeout(function() {
                    button.textContent = '📋';
                }, 2000);
            });
        });
        
        const pre = codeBlock.parentElement;
        pre.style.position = 'relative';
        pre.appendChild(button);
        
        // Show/hide button on hover
        pre.addEventListener('mouseenter', function() {
            button.style.opacity = '1';
        });
        
        pre.addEventListener('mouseleave', function() {
            button.style.opacity = '0.7';
        });
    });
}

// Add status indicators for system components
function addStatusIndicators() {
    const statusElements = document.querySelectorAll('[data-status]');
    statusElements.forEach(function(element) {
        const status = element.getAttribute('data-status');
        const indicator = document.createElement('span');
        indicator.className = 'status-indicator';
        indicator.style.cssText = `
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 5px;
        `;
        
        switch(status) {
            case 'online':
                indicator.style.backgroundColor = '#4caf50';
                break;
            case 'warning':
                indicator.style.backgroundColor = '#ff9800';
                break;
            case 'offline':
                indicator.style.backgroundColor = '#f44336';
                break;
        }
        
        element.insertBefore(indicator, element.firstChild);
    });
}

// Add smooth scrolling for anchor links
function addSmoothScrolling() {
    const links = document.querySelectorAll('a[href^="#"]');
    links.forEach(function(link) {
        link.addEventListener('click', function(e) {
            e.preventDefault();
            const target = document.querySelector(this.getAttribute('href'));
            if (target) {
                target.scrollIntoView({
                    behavior: 'smooth'
                });
            }
        });
    });
}

// Add keyboard shortcuts
function addKeyboardShortcuts() {
    document.addEventListener('keydown', function(e) {
        // Ctrl/Cmd + K for search
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            const searchInput = document.querySelector('.md-search__input');
            if (searchInput) {
                searchInput.focus();
            }
        }
        
        // Escape to close search
        if (e.key === 'Escape') {
            const searchInput = document.querySelector('.md-search__input');
            if (searchInput && searchInput === document.activeElement) {
                searchInput.blur();
            }
        }
    });
}

// Add table of contents highlighting
function addTocHighlighting() {
    const observer = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
            if (entry.isIntersecting) {
                const id = entry.target.getAttribute('id');
                const tocLink = document.querySelector(`a[href="#${id}"]`);
                if (tocLink) {
                    // Remove active class from all toc links
                    document.querySelectorAll('.md-nav__link--active').forEach(function(link) {
                        link.classList.remove('md-nav__link--active');
                    });
                    // Add active class to current link
                    tocLink.classList.add('md-nav__link--active');
                }
            }
        });
    }, {
        rootMargin: '-20% 0% -80% 0%'
    });
    
    // Observe all headings
    document.querySelectorAll('h1, h2, h3, h4, h5, h6').forEach(function(heading) {
        if (heading.getAttribute('id')) {
            observer.observe(heading);
        }
    });
}

// Add print functionality
function addPrintFunctionality() {
    const printButton = document.createElement('button');
    printButton.innerHTML = '🖨️ Print';
    printButton.className = 'print-button';
    printButton.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: var(--md-primary-fg-color);
        color: white;
        border: none;
        padding: 10px 15px;
        border-radius: 20px;
        cursor: pointer;
        z-index: 1000;
        font-weight: 600;
        opacity: 0.8;
        transition: opacity 0.3s;
    `;
    
    printButton.addEventListener('click', function() {
        window.print();
    });
    
    printButton.addEventListener('mouseenter', function() {
        this.style.opacity = '1';
    });
    
    printButton.addEventListener('mouseleave', function() {
        this.style.opacity = '0.8';
    });
    
    document.body.appendChild(printButton);
}

// Add version info tooltip
function addVersionInfo() {
    const versionBadges = document.querySelectorAll('.version-badge');
    versionBadges.forEach(function(badge) {
        badge.addEventListener('mouseenter', function() {
            const tooltip = document.createElement('div');
            tooltip.className = 'version-tooltip';
            tooltip.textContent = 'Latest stable version';
            tooltip.style.cssText = `
                position: absolute;
                background: black;
                color: white;
                padding: 5px 10px;
                border-radius: 4px;
                font-size: 12px;
                z-index: 1000;
                top: -30px;
                left: 50%;
                transform: translateX(-50%);
                white-space: nowrap;
            `;
            this.style.position = 'relative';
            this.appendChild(tooltip);
        });
        
        badge.addEventListener('mouseleave', function() {
            const tooltip = this.querySelector('.version-tooltip');
            if (tooltip) {
                tooltip.remove();
            }
        });
    });
}

// Initialize additional features when DOM is ready
document.addEventListener("DOMContentLoaded", function() {
    setTimeout(function() {
        addTocHighlighting();
        addPrintFunctionality();
        addVersionInfo();
    }, 1000);
});