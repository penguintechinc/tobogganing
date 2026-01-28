import * as React from 'react';
import { useEffect, useMemo, useState } from 'react';

/**
 * Version information structure
 */
export interface VersionInfo {
  /** Full version string (e.g., "1.0.0.1737727200") */
  full: string;
  /** Major version number */
  major: number;
  /** Minor version number */
  minor: number;
  /** Patch version number */
  patch: number;
  /** Build epoch timestamp (seconds since Unix epoch) */
  buildEpoch: number;
  /** Human-readable build date */
  buildDate: string;
  /** Semantic version without build (e.g., "1.0.0") */
  semver: string;
}

/**
 * Configuration for console output styling
 */
export interface ConsoleStyleConfig {
  /** Primary color for app name/banner (CSS color) */
  primaryColor?: string;
  /** Secondary color for version info (CSS color) */
  secondaryColor?: string;
  /** Accent color for highlights (CSS color) */
  accentColor?: string;
  /** Background color (CSS color) */
  backgroundColor?: string;
  /** Font family for console output */
  fontFamily?: string;
}

/**
 * Props for ConsoleVersion component
 */
export interface ConsoleVersionProps {
  /** Application name to display */
  appName: string;
  /** Version string in format "Major.Minor.Patch.Epoch" or "Major.Minor.Patch" */
  version: string;
  /** Optional build epoch override (if not included in version string) */
  buildEpoch?: number;
  /** Optional environment name (e.g., "development", "production") */
  environment?: string;
  /** Custom style configuration */
  styleConfig?: ConsoleStyleConfig;
  /** Whether to show banner/header (default: true) */
  showBanner?: boolean;
  /** Banner style: 'elder' for emoji+name (default), 'box' for ASCII art box */
  bannerStyle?: 'elder' | 'box';
  /** Emoji to display before app name (default: '🚀') */
  emoji?: string;
  /** Whether to output to console on mount (default: true) */
  logOnMount?: boolean;
  /** Additional metadata to display (e.g., API URL) */
  metadata?: Record<string, string | number>;
  /** Callback when version info is logged */
  onLog?: (info: VersionInfo) => void;
  /** Children to render (optional - component can be render-less) */
  children?: React.ReactNode;
}

// Elder-inspired default colors (amber/gold on dark)
// Matches Elder's App.tsx console output styling
const DEFAULT_STYLE: Required<ConsoleStyleConfig> = {
  primaryColor: '#f59e0b',      // Amber-500 (Elder's exact color)
  secondaryColor: '#64748b',    // Slate-500 (Elder's exact color)
  accentColor: '#60a5fa',       // Blue-400
  backgroundColor: '#0f172a',   // Dark-900
  fontFamily: 'Consolas, Monaco, "Courier New", monospace',
};

/**
 * Parse version string into structured VersionInfo
 */
export function parseVersion(version: string, buildEpochOverride?: number): VersionInfo {
  const parts = version.replace(/^v/, '').split('.');

  const major = parseInt(parts[0] || '0', 10);
  const minor = parseInt(parts[1] || '0', 10);
  const patch = parseInt(parts[2] || '0', 10);
  const buildEpoch = buildEpochOverride ?? parseInt(parts[3] || '0', 10);

  const buildDate = buildEpoch > 0
    ? new Date(buildEpoch * 1000).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, ' UTC')
    : 'Unknown';

  const semver = `${major}.${minor}.${patch}`;
  const full = buildEpoch > 0 ? `${semver}.${buildEpoch}` : semver;

  return {
    full,
    major,
    minor,
    patch,
    buildEpoch,
    buildDate,
    semver,
  };
}

/**
 * Generate ASCII art banner for console
 */
function generateBanner(appName: string): string {
  const maxWidth = Math.max(appName.length + 4, 20);
  const padding = Math.floor((maxWidth - appName.length) / 2);
  const leftPad = ' '.repeat(padding);
  const rightPad = ' '.repeat(maxWidth - appName.length - padding);

  return [
    '╔' + '═'.repeat(maxWidth) + '╗',
    '║' + leftPad + appName + rightPad + '║',
    '╚' + '═'.repeat(maxWidth) + '╝',
  ].join('\n');
}

/**
 * Log version information to browser console with styled output
 * Matches Elder's App.tsx console output pattern
 */
export function logVersionToConsole(
  appName: string,
  versionInfo: VersionInfo,
  options: {
    environment?: string;
    styleConfig?: ConsoleStyleConfig;
    showBanner?: boolean;
    bannerStyle?: 'elder' | 'box';
    emoji?: string;
    metadata?: Record<string, string | number>;
  } = {}
): void {
  const {
    environment,
    styleConfig = {},
    showBanner = true,
    bannerStyle = 'elder',
    emoji = '🚀',
    metadata,
  } = options;

  const styles = { ...DEFAULT_STYLE, ...styleConfig };

  // Elder-style: simple bold header with emoji
  const headerStyle = `font-size: 16px; font-weight: bold; color: ${styles.primaryColor}`;
  const infoStyle = `color: ${styles.secondaryColor}`;

  // Log banner/header
  if (showBanner) {
    if (bannerStyle === 'box') {
      // ASCII box style
      const boxBannerStyle = `
        color: ${styles.primaryColor};
        font-family: ${styles.fontFamily};
        font-size: 14px;
        font-weight: bold;
      `.trim();
      console.log(`%c${generateBanner(appName)}`, boxBannerStyle);
    } else {
      // Elder style: emoji + app name (default)
      console.log(`%c${emoji} ${appName}`, headerStyle);
    }
  }

  // Log version info (Elder style: separate lines)
  console.log(`%cVersion: ${versionInfo.semver}`, infoStyle);
  console.log(`%cBuild Epoch: ${versionInfo.buildEpoch || 'dev'}`, infoStyle);
  console.log(`%cBuild Date: ${versionInfo.buildDate}`, infoStyle);

  // Log environment if provided
  if (environment) {
    console.log(`%cEnvironment: ${environment}`, infoStyle);
  }

  // Log additional metadata
  if (metadata && Object.keys(metadata).length > 0) {
    Object.entries(metadata).forEach(([key, value]) => {
      console.log(`%c${key}: ${value}`, infoStyle);
    });
  }
}

/**
 * ConsoleVersion Component
 *
 * Logs build version and epoch information to the browser console on mount.
 * Inspired by Elder's console output pattern with gold/dark theme styling.
 *
 * @example
 * // Basic usage - just logs to console
 * <ConsoleVersion appName="MyApp" version="1.0.0.1737727200" />
 *
 * @example
 * // With environment and metadata
 * <ConsoleVersion
 *   appName="MyApp"
 *   version="1.0.0.1737727200"
 *   environment="development"
 *   metadata={{ 'API URL': 'http://localhost:5000' }}
 * />
 *
 * @example
 * // With custom styling
 * <ConsoleVersion
 *   appName="MyApp"
 *   version="1.0.0"
 *   buildEpoch={1737727200}
 *   styleConfig={{ primaryColor: '#00ff00' }}
 * />
 */
export function ConsoleVersion({
  appName,
  version,
  buildEpoch,
  environment,
  styleConfig,
  showBanner = true,
  bannerStyle = 'elder',
  emoji = '🚀',
  logOnMount = true,
  metadata,
  onLog,
  children,
}: ConsoleVersionProps): React.ReactNode {
  // Parse version info
  const versionInfo = useMemo(
    () => parseVersion(version, buildEpoch),
    [version, buildEpoch]
  );

  // Log to console on mount
  useEffect(() => {
    if (logOnMount) {
      logVersionToConsole(appName, versionInfo, {
        environment,
        styleConfig,
        showBanner,
        bannerStyle,
        emoji,
        metadata,
      });

      onLog?.(versionInfo);
    }
  }, [appName, versionInfo, environment, styleConfig, showBanner, bannerStyle, emoji, metadata, logOnMount, onLog]);

  // Return children if provided, otherwise render nothing
  return children ?? null;
}

/**
 * Hook to get parsed version info without console output
 *
 * @example
 * const versionInfo = useVersionInfo("1.0.0.1737727200");
 * console.log(versionInfo.buildDate); // "2025-01-24 12:00:00 UTC"
 */
export function useVersionInfo(version: string, buildEpoch?: number): VersionInfo {
  return useMemo(() => parseVersion(version, buildEpoch), [version, buildEpoch]);
}

/**
 * API status response structure
 */
export interface ApiStatusResponse {
  /** API version string */
  version?: string;
  /** Build epoch timestamp */
  build_epoch?: number;
  /** Any additional fields */
  [key: string]: unknown;
}

/**
 * Props for AppConsoleVersion component
 */
export interface AppConsoleVersionProps {
  /** Application name (used as prefix for WebUI/API labels) */
  appName: string;
  /** WebUI version string */
  webuiVersion: string;
  /** WebUI build epoch (optional if included in version string) */
  webuiBuildEpoch?: number;
  /** Environment name (e.g., "development", "production") */
  environment?: string;
  /** API status endpoint URL (default: "/api/v1/status") */
  apiStatusUrl?: string;
  /** Custom style configuration */
  styleConfig?: ConsoleStyleConfig;
  /** Banner style: 'elder' for emoji+name (default), 'box' for ASCII art box */
  bannerStyle?: 'elder' | 'box';
  /** Emoji for WebUI version (default: '🖥️') */
  webuiEmoji?: string;
  /** Emoji for API version (default: '⚙️') */
  apiEmoji?: string;
  /** Additional metadata to display with WebUI version */
  metadata?: Record<string, string | number>;
  /** Callback when WebUI version is logged */
  onWebuiLog?: (info: VersionInfo) => void;
  /** Callback when API version is logged */
  onApiLog?: (info: VersionInfo) => void;
  /** Callback on API fetch error */
  onApiError?: (error: Error) => void;
  /** Children to render (optional) */
  children?: React.ReactNode;
}

/**
 * AppConsoleVersion Component
 *
 * Logs both WebUI and API build version/epoch information to the browser console.
 * WebUI version logs immediately on mount. API version is fetched and logged after.
 *
 * @example
 * // Basic usage - logs both WebUI and API versions
 * <AppConsoleVersion
 *   appName="Elder"
 *   webuiVersion={import.meta.env.VITE_VERSION || '0.0.0'}
 *   webuiBuildEpoch={Number(import.meta.env.VITE_BUILD_TIME) || 0}
 *   environment={import.meta.env.MODE}
 * />
 *
 * @example
 * // With custom API endpoint and metadata
 * <AppConsoleVersion
 *   appName="MyApp"
 *   webuiVersion="1.0.0.1737727200"
 *   environment="production"
 *   apiStatusUrl="/api/v2/health"
 *   metadata={{ 'API URL': 'https://api.example.com' }}
 * />
 */
export function AppConsoleVersion({
  appName,
  webuiVersion,
  webuiBuildEpoch,
  environment,
  apiStatusUrl = '/api/v1/status',
  styleConfig,
  bannerStyle = 'elder',
  webuiEmoji = '🖥️',
  apiEmoji = '⚙️',
  metadata,
  onWebuiLog,
  onApiLog,
  onApiError,
  children,
}: AppConsoleVersionProps): React.ReactNode {
  // Parse WebUI version info
  const webuiVersionInfo = useMemo(
    () => parseVersion(webuiVersion, webuiBuildEpoch),
    [webuiVersion, webuiBuildEpoch]
  );

  // Log WebUI version on mount
  useEffect(() => {
    logVersionToConsole(`${appName} - WebUI`, webuiVersionInfo, {
      environment,
      styleConfig,
      showBanner: true,
      bannerStyle,
      emoji: webuiEmoji,
      metadata,
    });

    onWebuiLog?.(webuiVersionInfo);
  }, [appName, webuiVersionInfo, environment, styleConfig, bannerStyle, webuiEmoji, metadata, onWebuiLog]);

  // Fetch and log API version
  useEffect(() => {
    const fetchApiVersion = async () => {
      try {
        const response = await fetch(apiStatusUrl);
        if (!response.ok) {
          throw new Error(`API status request failed: ${response.status}`);
        }

        const data: ApiStatusResponse = await response.json();
        const apiVersion = data.version || 'unknown';
        const apiBuildEpoch = data.build_epoch;

        const apiVersionInfo = parseVersion(apiVersion, apiBuildEpoch);

        logVersionToConsole(`${appName} - API`, apiVersionInfo, {
          styleConfig,
          showBanner: true,
          bannerStyle,
          emoji: apiEmoji,
        });

        onApiLog?.(apiVersionInfo);
      } catch (error) {
        const err = error instanceof Error ? error : new Error(String(error));
        console.warn(`%cFailed to fetch API version: ${err.message}`, `color: #f59e0b`);
        onApiError?.(err);
      }
    };

    fetchApiVersion();
  }, [appName, apiStatusUrl, styleConfig, bannerStyle, apiEmoji, onApiLog, onApiError]);

  return children ?? null;
}

/**
 * Hook to fetch and parse API version info
 *
 * @example
 * const { apiVersion, loading, error } = useApiVersionInfo('/api/v1/status');
 */
export function useApiVersionInfo(apiStatusUrl: string = '/api/v1/status'): {
  apiVersion: VersionInfo | null;
  loading: boolean;
  error: Error | null;
} {
  const [apiVersion, setApiVersion] = useState<VersionInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    const fetchApiVersion = async () => {
      try {
        setLoading(true);
        const response = await fetch(apiStatusUrl);
        if (!response.ok) {
          throw new Error(`API status request failed: ${response.status}`);
        }

        const data: ApiStatusResponse = await response.json();
        const version = data.version || 'unknown';
        const buildEpoch = data.build_epoch;

        setApiVersion(parseVersion(version, buildEpoch));
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err : new Error(String(err)));
        setApiVersion(null);
      } finally {
        setLoading(false);
      }
    };

    fetchApiVersion();
  }, [apiStatusUrl]);

  return { apiVersion, loading, error };
}

export default ConsoleVersion;
