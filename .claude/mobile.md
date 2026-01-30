# Mobile App Standards

## ⚠️ CRITICAL RULES

- **DO NOT assume a mobile app exists** - only build one when explicitly requested
- **Flutter is the DEFAULT framework** for all mobile applications - no exceptions unless stated
- **Target BOTH iOS and Android** - every mobile app ships on both platforms
- **Support phones AND tablets** - all layouts must be responsive across phone and tablet form factors on both platforms
- **Native modules are permitted** only when Flutter lacks support for a specific capability
- **Dart linting required** - all code must pass `flutter analyze` before commit
- **Platform testing required** - test on iOS and Android devices/emulators for both phone and tablet screen sizes

## When to Build a Mobile App

**Only build a mobile app when the user or project requirements explicitly call for one.** Mobile apps are not part of the default project template. The standard three-container architecture (WebUI, API, Go backend) does not include a mobile client.

**Indicators that a mobile app is needed:**
- User explicitly requests a mobile app
- Requirements document specifies iOS/Android support
- Project scope includes native device features (push notifications, camera, biometrics, etc.)

**If unclear, ask before creating any mobile app scaffolding.**

## Technology Stack

**Framework: Flutter (Default)**
- Flutter SDK (latest stable channel)
- Dart language (version aligned with Flutter SDK)
- Cross-platform: single codebase for iOS and Android

**When to Use Native Modules:**
- Flutter has no plugin or package for the required functionality
- Existing Flutter plugins are unmaintained, unstable, or lack critical features
- Performance-critical operations that require direct platform API access (e.g., low-level Bluetooth, custom camera pipelines, real-time audio processing)
- Platform-specific APIs with no Flutter equivalent (e.g., certain HealthKit/Health Connect features, NFC advanced modes, platform-specific accessibility APIs)

**Native module approach:**
- Use Flutter platform channels (`MethodChannel`, `EventChannel`) to bridge native code
- Write native code in Swift for iOS, Kotlin for Android
- Keep native code minimal - only what Flutter cannot do
- Document every native module with justification for why Flutter was insufficient

## Project Structure

```
services/mobile/
├── lib/
│   ├── main.dart              # App entry point
│   ├── app.dart               # App widget, routing, theme
│   ├── config/                # Environment, constants
│   ├── models/                # Data models
│   ├── services/              # API client, auth, storage
│   ├── providers/             # State management
│   ├── screens/               # Page-level widgets
│   ├── widgets/               # Reusable UI components
│   └── utils/                 # Helpers, extensions
├── android/                   # Android native project
├── ios/                       # iOS native project
├── test/                      # Unit and widget tests
├── integration_test/          # Integration tests
├── pubspec.yaml               # Dependencies
├── analysis_options.yaml      # Lint rules
└── Dockerfile                 # CI build environment
```

## Platform & Device Support

**Platforms:**
| Platform | Language (Native Modules) | Min Version |
|----------|--------------------------|-------------|
| iOS      | Swift                    | iOS 15+     |
| Android  | Kotlin                   | API 24+ (Android 7.0) |

**Form Factors:**
| Device  | Breakpoint    | Layout Expectations |
|---------|---------------|---------------------|
| Phone   | < 600dp wide  | Single-column, bottom navigation |
| Tablet  | >= 600dp wide | Multi-pane, side navigation, master-detail |

**Responsive layout is mandatory.** Use `LayoutBuilder` or `MediaQuery` to adapt UI across form factors. Never hardcode widths or assume a single device size.

## API Integration

The mobile app communicates with the same Flask backend API used by the WebUI:

```dart
// lib/services/api_client.dart
import 'package:dio/dio.dart';

class ApiClient {
  final Dio _dio;

  ApiClient({required String baseUrl})
      : _dio = Dio(BaseOptions(
          baseUrl: baseUrl,
          headers: {'Content-Type': 'application/json'},
        )) {
    _dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) {
        final token = AuthService.instance.token;
        if (token != null) {
          options.headers['Authorization'] = 'Bearer $token';
        }
        handler.next(options);
      },
      onError: (error, handler) {
        if (error.response?.statusCode == 401) {
          AuthService.instance.logout();
        }
        handler.next(error);
      },
    ));
  }
}
```

**API versioning:** Use the same `/api/v{major}/endpoint` pattern as web clients.

## State Management

**Recommended:** `provider` or `riverpod` for state management. Choose one per project and use it consistently.

- `provider` - simpler apps with straightforward state
- `riverpod` - complex apps needing compile-safe dependency injection

## Authentication

Use the same Flask-Security-Too backend as the WebUI. The mobile app should support:
- JWT token storage (secure storage, not shared preferences)
- Biometric authentication (fingerprint, face) via `local_auth` plugin
- MFA/2FA support matching the web flow
- Token refresh on 401 responses

**Secure storage:**
```dart
// Use flutter_secure_storage for tokens - never SharedPreferences
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final storage = FlutterSecureStorage();
await storage.write(key: 'authToken', value: token);
```

## Design & Theming

Follow the same design language as the WebUI where appropriate:
- Dark theme default with gold/amber accents
- Use `ThemeData` for consistent styling
- Material Design 3 as the base design system
- Platform-adaptive widgets where appropriate (Cupertino on iOS for native feel is acceptable)

**Tablet layouts must differ from phone layouts.** Use adaptive layouts:
- Phone: bottom navigation bar, single-column content
- Tablet: navigation rail or side drawer, multi-pane layouts, master-detail patterns

## Testing

**Required test coverage:**
- Unit tests for models, services, and business logic
- Widget tests for UI components
- Integration tests for critical user flows
- Test on both phone and tablet emulators for each platform

```bash
# Run all tests
flutter test

# Run integration tests
flutter test integration_test/

# Analyze code
flutter analyze
```

**Device matrix for testing:**
| Platform | Phone Emulator       | Tablet Emulator      |
|----------|----------------------|----------------------|
| iOS      | iPhone 15            | iPad Pro 12.9"       |
| Android  | Pixel 8              | Pixel Tablet         |

## Build & Distribution

```bash
# Build for both platforms
flutter build apk --release          # Android APK
flutter build appbundle --release    # Android App Bundle (Play Store)
flutter build ipa --release          # iOS (requires macOS)
```

**CI builds** use a Debian-based Docker image with Flutter SDK for Android builds. iOS builds require a macOS runner (GitHub Actions `macos-latest`).

## Linting & Code Quality

**analysis_options.yaml:**
```yaml
include: package:flutter_lints/flutter.yaml

linter:
  rules:
    prefer_const_constructors: true
    prefer_const_literals_to_create_immutables: true
    avoid_print: true
    prefer_single_quotes: true
    sort_child_properties_last: true
    use_build_context_synchronously: true
```

**Run before every commit:**
```bash
flutter analyze          # Static analysis
dart format --set-exit-if-changed .  # Formatting
flutter test             # All tests
```

## Native Module Guidelines

When a native module is necessary:

1. **Document the justification** - add a comment in the native code and a note in the project's `APP_STANDARDS.md` explaining why Flutter alone is insufficient
2. **Keep native code minimal** - only implement what Flutter cannot handle; all other logic stays in Dart
3. **Use platform channels** - `MethodChannel` for request/response, `EventChannel` for streams
4. **Write for both platforms** - every native module must have both Swift (iOS) and Kotlin (Android) implementations
5. **Test native code** - include platform-specific tests (XCTest for iOS, JUnit for Android)

**Example platform channel:**
```dart
// lib/services/native_bridge.dart
import 'package:flutter/services.dart';

class NativeBridge {
  static const _channel = MethodChannel('com.penguintech.app/native');

  static Future<String?> getPlatformSpecificData() async {
    return await _channel.invokeMethod('getPlatformSpecificData');
  }
}
```

## Security

- Store tokens in platform secure storage (Keychain on iOS, EncryptedSharedPreferences on Android)
- Enable certificate pinning for API connections in production
- Obfuscate release builds (`flutter build apk --obfuscate --split-debug-info=build/debug-info`)
- No hardcoded secrets, API keys, or credentials in Dart or native code
- Use environment configuration for API URLs and feature flags
