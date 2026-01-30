# 📱 Mobile App Standards - Flutter First

Part of [Development Standards](../STANDARDS.md)

Mobile apps are **not assumed by default**. Only create a mobile app when the project explicitly requires one. When you do, Flutter is your framework and you ship on both iOS and Android for phones and tablets.

> **Important**: Not every project needs a mobile app. If requirements don't mention mobile, don't build one. The standard three-container architecture (WebUI, API, Go backend) does not include a mobile client.

## Quick Decision Flowchart

```
Start: "Does this project need a mobile app?"
  ├─ Not mentioned in requirements → ❌ Don't build one
  ├─ User/requirements explicitly ask for mobile → ✅ Build with Flutter
  └─ Unsure → ❓ Ask before creating any mobile scaffolding
```

## 🦋 Flutter (Your Default Framework)

**Every mobile app uses Flutter.** Single Dart codebase, two platforms, four form factors (iOS phone, iOS tablet, Android phone, Android tablet).

### Why Flutter?

| Benefit | Detail |
|---------|--------|
| **Single codebase** | One Dart project for iOS + Android |
| **Phone + tablet** | Responsive layouts adapt to all form factors |
| **Hot reload** | Sub-second feedback during development |
| **Native performance** | Compiles to ARM, no JavaScript bridge |
| **Rich ecosystem** | pub.dev has packages for most needs |
| **Consistent UI** | Pixel-perfect control across platforms |

### Technology Stack

| Component | Choice |
|-----------|--------|
| Framework | Flutter (latest stable) |
| Language | Dart |
| State management | `provider` or `riverpod` (pick one per project) |
| HTTP client | `dio` |
| Secure storage | `flutter_secure_storage` |
| Local auth | `local_auth` (biometrics) |
| Navigation | `go_router` or Navigator 2.0 |
| Linting | `flutter_lints` + `flutter analyze` |

## 📐 Platform & Device Support

### Target Platforms

| Platform | Native Language (Modules) | Minimum Version |
|----------|--------------------------|-----------------|
| iOS | Swift | iOS 15+ |
| Android | Kotlin | API 24+ (Android 7.0) |

### Form Factors (ALL Required)

Every mobile app must support all four combinations:

| Device | Width | Layout Expectations |
|--------|-------|---------------------|
| Phone (portrait) | < 600dp | Single-column, bottom navigation |
| Phone (landscape) | Varies | Adapted single-column or compact two-pane |
| Tablet (portrait) | >= 600dp | Multi-pane, side navigation |
| Tablet (landscape) | >= 900dp | Full master-detail, side navigation, expanded content |

**Responsive layout is mandatory.** Use `LayoutBuilder` or `MediaQuery` to adapt UI. Never hardcode widths or assume a single device size.

### Testing Device Matrix

| Platform | Phone | Tablet |
|----------|-------|--------|
| iOS | iPhone 15 | iPad Pro 12.9" |
| Android | Pixel 8 | Pixel Tablet |

Test on all four emulator/simulator configurations before release.

## 🏗️ Project Structure

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
└── README.md                  # Mobile-specific setup docs
```

## 🔌 API Integration

The mobile app talks to the same Flask backend API as the WebUI. Same endpoints, same versioning, same auth flow.

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

**API versioning**: Use `/api/v{major}/endpoint`, same as web clients.

## 🔐 Authentication & Security

Uses the same Flask-Security-Too backend. Mobile-specific considerations:

| Concern | Approach |
|---------|----------|
| Token storage | `flutter_secure_storage` (Keychain on iOS, EncryptedSharedPreferences on Android) |
| Biometrics | `local_auth` plugin for fingerprint/face unlock |
| MFA/2FA | Same TOTP flow as web, adapted for mobile UI |
| Token refresh | Automatic on 401 via Dio interceptor |
| Certificate pinning | Enabled in production builds |
| Build obfuscation | `--obfuscate --split-debug-info` on release builds |

**Never store tokens in SharedPreferences.** Always use platform secure storage:

```dart
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

final storage = FlutterSecureStorage();
await storage.write(key: 'authToken', value: token);
final token = await storage.read(key: 'authToken');
```

## 🎨 Design & Theming

Follow the same design language as the WebUI where it makes sense:

- **Dark theme default** with gold/amber accents
- **Material Design 3** as the base design system
- Use `ThemeData` for consistent styling across the app
- Platform-adaptive widgets are acceptable (e.g., Cupertino switches on iOS)

### Layout by Form Factor

| Form Factor | Navigation | Content |
|-------------|------------|---------|
| Phone | Bottom navigation bar | Single-column, scrollable |
| Tablet | Navigation rail or side drawer | Multi-pane, master-detail |

Phone and tablet layouts **must differ**. A phone layout stretched to a tablet is not acceptable.

## 🔧 Native Modules (When Flutter Isn't Enough)

Flutter handles the vast majority of use cases. Native modules are the exception, not the rule.

### When Native Modules Are Justified

- Flutter has **no plugin or package** for the feature
- Existing plugins are **unmaintained, unstable, or missing critical functionality**
- **Performance-critical** operations requiring direct platform API access (low-level Bluetooth, custom camera pipelines, real-time audio processing)
- **Platform-specific APIs** with no Flutter equivalent (certain HealthKit/Health Connect features, advanced NFC modes, platform-specific accessibility APIs)

### When Native Modules Are NOT Justified

- A Flutter plugin exists and works, even if imperfect
- "It would be faster in native" without measured proof
- Developer preference or familiarity with native code
- Features that can be achieved with platform channels + existing plugins

### Native Module Rules

1. **Document the justification** - comment in native code + note in `APP_STANDARDS.md` explaining why Flutter was insufficient
2. **Keep native code minimal** - only what Flutter cannot do; all other logic stays in Dart
3. **Use platform channels** - `MethodChannel` for request/response, `EventChannel` for streams
4. **Write for both platforms** - every native module needs both Swift (iOS) and Kotlin (Android) implementations
5. **Test native code** - XCTest for iOS, JUnit for Android

### Platform Channel Example

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

## 🧪 Testing

### Required Test Coverage

| Test Type | Scope | Tool |
|-----------|-------|------|
| Unit tests | Models, services, business logic | `flutter test` |
| Widget tests | UI components render correctly | `flutter test` |
| Integration tests | Critical user flows end-to-end | `flutter test integration_test/` |
| Platform tests | Native modules (if any) | XCTest (iOS), JUnit (Android) |

### Running Tests

```bash
flutter test                       # Unit + widget tests
flutter test integration_test/     # Integration tests
flutter analyze                    # Static analysis
dart format --set-exit-if-changed . # Formatting check
```

Test on **all four device configurations** (iOS phone, iOS tablet, Android phone, Android tablet) before release.

## 📦 Build & Distribution

```bash
# Android
flutter build apk --release            # APK for direct install
flutter build appbundle --release       # AAB for Play Store

# iOS (requires macOS)
flutter build ipa --release             # IPA for App Store

# Obfuscated release (recommended)
flutter build apk --release --obfuscate --split-debug-info=build/debug-info
flutter build ipa --release --obfuscate --split-debug-info=build/debug-info
```

### CI Considerations

- **Android builds**: Debian-based Docker image with Flutter SDK
- **iOS builds**: macOS runner required (GitHub Actions `macos-latest`)
- Both platforms built and tested on every PR

## ✅ Pre-Commit Checklist (Mobile)

Before committing mobile code:

```bash
flutter analyze                    # No lint warnings
dart format --set-exit-if-changed . # Formatting correct
flutter test                       # All tests pass
```

No commits with analyzer warnings or failing tests.

## 💡 Tips & FAQ

**Q: Should I use Flutter or React Native?**
A: Flutter. Always. This is the standard. No exceptions unless explicitly overridden.

**Q: Can I use platform-specific UI (Cupertino on iOS)?**
A: Yes, for platform-adaptive widgets (switches, date pickers, navigation transitions). The core app structure and business logic stay in Flutter/Material.

**Q: Do I need to support both phone and tablet from day one?**
A: Yes. Both form factors on both platforms. Design responsive layouts from the start - retrofitting tablet support is painful.

**Q: When should I consider a native module?**
A: When you've confirmed Flutter can't do it. Check pub.dev first, try the available plugins, and only go native as a last resort. Document your reasoning.

**Q: How does the mobile app relate to the WebUI?**
A: They're separate clients hitting the same backend API. Same endpoints, same auth, different UI. The mobile app lives in `services/mobile/`, the WebUI in `services/webui/`.

---

*Flutter first, native only when necessary. Ship on both platforms, support all screen sizes, and keep the codebase unified.*
