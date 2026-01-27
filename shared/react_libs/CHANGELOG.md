# Changelog

All notable changes to @penguin/react_libs will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-01-27

### Added
- **Multi-select checkbox support**: New `checkbox_multi` field type for FormModalBuilder
  - Allows users to select multiple options from a list of checkboxes
  - Returns an array of selected values
  - Supports required validation (must have at least one selection)
  - Includes scrollable container for long option lists
  - Example: See `examples/MultiSelectExample.tsx`

### Changed
- Updated field type union to include `checkbox_multi`
- Enhanced default value initialization to handle arrays for multi-select fields
- Improved Zod schema validation for multi-select arrays

## [1.0.0] - 2026-01-22

### Added
- Initial release of @penguin/react_libs
- FormModalBuilder component with comprehensive field types
- SidebarMenu component for navigation
- Dark mode theme with gold accents (default)
- Zod-based validation
- Conditional field visibility (showWhen, triggerField)
- Tab support for complex forms
- File upload with drag & drop
- Password generation
