#!/usr/bin/env python3
"""
Validation script for Tobogganing Documentation
"""

import os
import sys
import yaml
from pathlib import Path

def main():
    """Main validation function"""
    print("🔍 Tobogganing Documentation Validation")
    print("=" * 40)
    
    errors = []
    warnings = []
    
    # Check if we're in the correct directory
    if not os.path.exists('mkdocs.yml'):
        print("❌ Error: mkdocs.yml not found. Run this script from docs-website/")
        sys.exit(1)
    
    # Validate mkdocs.yml
    print("\n📋 Validating MkDocs configuration...")
    try:
        with open('mkdocs.yml', 'r') as f:
            config = yaml.safe_load(f)
        print(f"   ✅ Site Name: {config['site_name']}")
        print(f"   ✅ Site URL: {config['site_url']}")
        print(f"   ✅ Theme: {config['theme']['name']}")
    except Exception as e:
        errors.append(f"Invalid mkdocs.yml: {e}")
        print(f"   ❌ {e}")
    
    # Check required files
    print("\n📁 Checking required files...")
    required_files = [
        'requirements.txt',
        'Dockerfile',
        'docker-compose.yml',
        'Makefile',
        'README.md',
        '.gitignore',
        'docs/index.md',
        'docs/stylesheets/extra.css',
        'docs/javascripts/extra.js',
    ]
    
    for file in required_files:
        if os.path.exists(file):
            print(f"   ✅ {file}")
        else:
            errors.append(f"Missing file: {file}")
            print(f"   ❌ {file}")
    
    # Check documentation files
    print("\n📖 Checking documentation files...")
    docs_dir = Path('docs')
    if docs_dir.exists():
        md_files = list(docs_dir.glob('*.md'))
        symlinks = [f for f in md_files if f.is_symlink()]
        regular_files = [f for f in md_files if not f.is_symlink()]
        
        print(f"   ✅ Total MD files: {len(md_files)}")
        print(f"   ✅ Symbolic links: {len(symlinks)}")
        print(f"   ✅ Regular files: {len(regular_files)}")
        
        # Check for broken symlinks
        broken_links = []
        for symlink in symlinks:
            if not symlink.exists():
                broken_links.append(str(symlink))
        
        if broken_links:
            errors.extend([f"Broken symlink: {link}" for link in broken_links])
            print(f"   ❌ Broken symlinks: {len(broken_links)}")
        else:
            print(f"   ✅ All symlinks valid")
    else:
        errors.append("docs/ directory not found")
        print("   ❌ docs/ directory not found")
    
    # Validate navigation structure
    print("\n🧭 Validating navigation...")
    if 'config' in locals():
        nav = config.get('nav', [])
        nav_files = []
        
        def extract_nav_files(items):
            for item in items:
                if isinstance(item, dict):
                    for key, value in item.items():
                        if isinstance(value, str):
                            nav_files.append(value)
                        elif isinstance(value, list):
                            extract_nav_files(value)
        
        extract_nav_files(nav)
        
        print(f"   ✅ Navigation items: {len(nav_files)}")
        
        # Check if nav files exist
        missing_nav_files = []
        for nav_file in nav_files:
            file_path = f"docs/{nav_file}"
            if not os.path.exists(file_path):
                missing_nav_files.append(nav_file)
        
        if missing_nav_files:
            errors.extend([f"Missing navigation file: {f}" for f in missing_nav_files])
            print(f"   ❌ Missing nav files: {len(missing_nav_files)}")
        else:
            print("   ✅ All navigation files exist")
    
    # Check Docker configuration
    print("\n🐳 Checking Docker configuration...")
    if os.path.exists('Dockerfile'):
        with open('Dockerfile', 'r') as f:
            dockerfile_content = f.read()
        
        if 'FROM python:3.12-slim as builder' in dockerfile_content:
            print("   ✅ Multi-stage build configured")
        else:
            warnings.append("Dockerfile may not use multi-stage build")
        
        if 'FROM nginx:alpine' in dockerfile_content:
            print("   ✅ Nginx production stage configured")
        else:
            warnings.append("Dockerfile may not have nginx stage")
    
    # Summary
    print("\n📊 Validation Summary")
    print("=" * 20)
    
    if errors:
        print(f"❌ Errors: {len(errors)}")
        for error in errors:
            print(f"   • {error}")
    else:
        print("✅ No errors found")
    
    if warnings:
        print(f"⚠️  Warnings: {len(warnings)}")
        for warning in warnings:
            print(f"   • {warning}")
    else:
        print("✅ No warnings")
    
    # Final status
    if errors:
        print("\n❌ Validation FAILED")
        sys.exit(1)
    else:
        print("\n✅ Validation PASSED")
        print("\n🚀 Ready to build and deploy!")
        print("   • Run 'make serve-dev' for development")
        print("   • Run 'make docker-run' for production")
        print("   • Run 'make test' for full validation")

if __name__ == '__main__':
    main()