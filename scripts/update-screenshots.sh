#!/bin/bash

# SASEWaddle Screenshot Update Script
# Generates and updates application screenshots for the website

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
WEBSITE_DIR="$ROOT_DIR/website"
SCREENSHOTS_DIR="$WEBSITE_DIR/public/images/screenshots"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }

echo "==========================================="
echo "  SASEWaddle Screenshot Updater"
echo "==========================================="

# Check if website exists
if [ ! -d "$WEBSITE_DIR" ]; then
    log_error "Website directory not found at $WEBSITE_DIR"
    exit 1
fi

# Create screenshots directory
mkdir -p "$SCREENSHOTS_DIR"

# Update AppShowcase component with latest screenshots
log_info "Updating AppShowcase component..."

# Get list of actual screenshot files
cd "$SCREENSHOTS_DIR"
DESKTOP_SCREENSHOTS=$(ls *-desktop.png 2>/dev/null || echo "")
MOBILE_SCREENSHOTS=$(ls mobile-*.png 2>/dev/null || echo "")
TABLET_SCREENSHOTS=$(ls *-tablet.png 2>/dev/null || echo "")

# Create updated AppShowcase component
cat > "$WEBSITE_DIR/components/AppShowcase.tsx" << 'EOF'
import React, { useState } from 'react';
import Image from 'next/image';

interface ScreenshotItem {
    name: string;
    src: string;
    alt: string;
    category: 'desktop' | 'mobile' | 'tablet';
}

export const AppShowcase: React.FC = () => {
    const [activeCategory, setActiveCategory] = useState<'all' | 'desktop' | 'mobile' | 'tablet'>('all');
    
    const screenshots: ScreenshotItem[] = [
EOF

# Add desktop screenshots
if [ -n "$DESKTOP_SCREENSHOTS" ]; then
    echo "$DESKTOP_SCREENSHOTS" | while read -r screenshot; do
        if [ -n "$screenshot" ]; then
            name=$(echo "$screenshot" | sed 's/-desktop\.png//' | sed 's/-/ /g' | sed 's/\b\w/\U&/g')
            cat >> "$WEBSITE_DIR/components/AppShowcase.tsx" << EOF
        {
            name: '$name',
            src: '/images/screenshots/$screenshot',
            alt: 'SASEWaddle $name on desktop',
            category: 'desktop'
        },
EOF
        fi
    done
fi

# Add mobile screenshots  
if [ -n "$MOBILE_SCREENSHOTS" ]; then
    echo "$MOBILE_SCREENSHOTS" | while read -r screenshot; do
        if [ -n "$screenshot" ]; then
            name=$(echo "$screenshot" | sed 's/mobile-//' | sed 's/\.png//' | sed 's/-/ /g' | sed 's/\b\w/\U&/g')
            cat >> "$WEBSITE_DIR/components/AppShowcase.tsx" << EOF
        {
            name: 'Mobile - $name',
            src: '/images/screenshots/$screenshot',
            alt: 'SASEWaddle mobile app $name',
            category: 'mobile'
        },
EOF
        fi
    done
fi

# Add tablet screenshots
if [ -n "$TABLET_SCREENSHOTS" ]; then
    echo "$TABLET_SCREENSHOTS" | while read -r screenshot; do
        if [ -n "$screenshot" ]; then
            name=$(echo "$screenshot" | sed 's/-tablet\.png//' | sed 's/-/ /g' | sed 's/\b\w/\U&/g')
            cat >> "$WEBSITE_DIR/components/AppShowcase.tsx" << EOF
        {
            name: 'Tablet - $name',
            src: '/images/screenshots/$screenshot',
            alt: 'SASEWaddle $name on tablet',
            category: 'tablet'
        },
EOF
        fi
    done
fi

# Complete the component
cat >> "$WEBSITE_DIR/components/AppShowcase.tsx" << 'EOF'
    ];

    const filteredScreenshots = activeCategory === 'all' 
        ? screenshots 
        : screenshots.filter(s => s.category === activeCategory);

    const categories = [
        { id: 'all', label: 'All Platforms', count: screenshots.length },
        { id: 'desktop', label: 'Desktop', count: screenshots.filter(s => s.category === 'desktop').length },
        { id: 'mobile', label: 'Mobile', count: screenshots.filter(s => s.category === 'mobile').length },
        { id: 'tablet', label: 'Tablet', count: screenshots.filter(s => s.category === 'tablet').length }
    ].filter(cat => cat.count > 0);

    return (
        <section className="py-16 bg-gradient-to-br from-gray-50 to-gray-100">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                <div className="text-center mb-12">
                    <h2 className="text-4xl font-bold text-gray-900 mb-4">
                        Application Gallery
                    </h2>
                    <p className="text-xl text-gray-600 max-w-3xl mx-auto">
                        Experience SASEWaddle across all platforms with intuitive interfaces
                        and comprehensive security management tools.
                    </p>
                </div>

                {/* Category Filter */}
                <div className="flex justify-center mb-8">
                    <div className="bg-white rounded-lg p-1 shadow-lg">
                        {categories.map(category => (
                            <button
                                key={category.id}
                                onClick={() => setActiveCategory(category.id as any)}
                                className={`px-4 py-2 rounded-md font-medium transition-all ${
                                    activeCategory === category.id
                                        ? 'bg-blue-600 text-white shadow-md'
                                        : 'text-gray-600 hover:bg-gray-100'
                                }`}
                            >
                                {category.label}
                                {category.count > 0 && (
                                    <span className={`ml-2 text-xs px-2 py-1 rounded-full ${
                                        activeCategory === category.id
                                            ? 'bg-blue-500 text-white'
                                            : 'bg-gray-200 text-gray-600'
                                    }`}>
                                        {category.count}
                                    </span>
                                )}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Screenshots Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {filteredScreenshots.map((screenshot, index) => (
                        <div key={index} className="group bg-white rounded-xl shadow-md hover:shadow-xl transition-all duration-300 overflow-hidden">
                            <div className="aspect-w-16 aspect-h-10 bg-gray-100">
                                <Image
                                    src={screenshot.src}
                                    alt={screenshot.alt}
                                    width={600}
                                    height={400}
                                    className="object-cover w-full h-full group-hover:scale-105 transition-transform duration-300"
                                    onError={(e) => {
                                        // Handle missing images gracefully
                                        const target = e.target as HTMLImageElement;
                                        target.style.display = 'none';
                                        // Add placeholder
                                        const parent = target.parentElement;
                                        if (parent) {
                                            parent.innerHTML = `
                                                <div class="flex items-center justify-center h-full bg-gray-200">
                                                    <div class="text-center">
                                                        <div class="text-4xl mb-2">📱</div>
                                                        <div class="text-gray-500">Screenshot Coming Soon</div>
                                                    </div>
                                                </div>
                                            `;
                                        }
                                    }}
                                />
                            </div>
                            <div className="p-6">
                                <h3 className="text-lg font-semibold text-gray-900 mb-2">
                                    {screenshot.name}
                                </h3>
                                <p className="text-sm text-gray-600">
                                    {screenshot.alt}
                                </p>
                                <div className="mt-3">
                                    <span className={`inline-flex px-2 py-1 text-xs font-medium rounded-full ${
                                        screenshot.category === 'desktop' 
                                            ? 'bg-blue-100 text-blue-800'
                                            : screenshot.category === 'mobile'
                                            ? 'bg-green-100 text-green-800' 
                                            : 'bg-purple-100 text-purple-800'
                                    }`}>
                                        {screenshot.category}
                                    </span>
                                </div>
                            </div>
                        </div>
                    ))}
                </div>

                {filteredScreenshots.length === 0 && (
                    <div className="text-center py-12">
                        <div className="text-6xl mb-4">📷</div>
                        <h3 className="text-xl font-semibold text-gray-900 mb-2">No Screenshots Available</h3>
                        <p className="text-gray-600 mb-6">Screenshots are being generated. Please check back soon!</p>
                        <button 
                            onClick={() => setActiveCategory('all')}
                            className="bg-blue-600 text-white px-6 py-2 rounded-lg hover:bg-blue-700 transition-colors"
                        >
                            View All Screenshots
                        </button>
                    </div>
                )}
            </div>
        </section>
    );
};

export default AppShowcase;
EOF

log_success "AppShowcase component updated"

# Generate screenshot inventory
log_info "Generating screenshot inventory..."

cat > "$SCREENSHOTS_DIR/inventory.json" << EOF
{
    "generated": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "total_count": $(find "$SCREENSHOTS_DIR" -name "*.png" | wc -l),
    "categories": {
        "desktop": $(find "$SCREENSHOTS_DIR" -name "*-desktop.png" | wc -l),
        "mobile": $(find "$SCREENSHOTS_DIR" -name "mobile-*.png" | wc -l),  
        "tablet": $(find "$SCREENSHOTS_DIR" -name "*-tablet.png" | wc -l)
    },
    "screenshots": [
$(find "$SCREENSHOTS_DIR" -name "*.png" -exec basename {} \; | sort | sed 's/.*/"&"/' | sed '$!s/$/,/')
    ]
}
EOF

# Display summary
echo
log_success "Screenshot update completed!"
echo
log_info "Summary:"
echo "  • Desktop screenshots: $(find "$SCREENSHOTS_DIR" -name "*-desktop.png" | wc -l)"
echo "  • Mobile screenshots: $(find "$SCREENSHOTS_DIR" -name "mobile-*.png" | wc -l)"
echo "  • Tablet screenshots: $(find "$SCREENSHOTS_DIR" -name "*-tablet.png" | wc -l)"
echo "  • Total screenshots: $(find "$SCREENSHOTS_DIR" -name "*.png" | wc -l)"
echo
log_info "Files updated:"
echo "  • $WEBSITE_DIR/components/AppShowcase.tsx"
echo "  • $SCREENSHOTS_DIR/inventory.json"
echo
log_info "To regenerate screenshots, run:"
echo "  ./scripts/build-apps.sh --screenshots-only"
echo

cd "$ROOT_DIR"