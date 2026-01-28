import React from 'react';
import {
  ConsoleVersion,
  AppConsoleVersion,
  useVersionInfo,
  useApiVersionInfo,
  parseVersion,
} from '../src/components';

/**
 * Example: Basic Elder-Style Console Version Output
 * Logs version info to browser console on mount with Elder styling
 */
export const BasicConsoleVersionExample: React.FC = () => {
  return (
    <ConsoleVersion
      appName="My Application"
      version="1.0.0.1737727200"
      environment="development"
    />
  );
};

/**
 * Example: With Custom Emoji and Metadata
 * Shows how to customize the emoji and add extra metadata
 */
export const CustomMetadataExample: React.FC = () => {
  return (
    <ConsoleVersion
      appName="Elder - Entity Tracking"
      version="2.1.0.1737727200"
      environment="production"
      emoji="🏛️"
      metadata={{
        'API URL': 'https://api.example.com',
        'WebSocket': 'wss://ws.example.com',
      }}
    />
  );
};

/**
 * Example: ASCII Box Banner Style
 * Uses the 'box' banner style for a more prominent display
 */
export const BoxBannerExample: React.FC = () => {
  return (
    <ConsoleVersion
      appName="Project Template"
      version="1.2.3.1737727200"
      bannerStyle="box"
      environment="staging"
    />
  );
};

/**
 * Example: Custom Colors
 * Demonstrates custom color configuration
 */
export const CustomColorsExample: React.FC = () => {
  return (
    <ConsoleVersion
      appName="Custom Styled App"
      version="1.0.0"
      buildEpoch={1737727200}
      styleConfig={{
        primaryColor: '#22c55e',    // Green
        secondaryColor: '#a1a1aa',  // Zinc
      }}
      emoji="🌿"
    />
  );
};

/**
 * Example: With Callback
 * Demonstrates using the onLog callback for additional actions
 */
export const CallbackExample: React.FC = () => {
  return (
    <ConsoleVersion
      appName="Callback Demo"
      version="1.0.0.1737727200"
      onLog={(info) => {
        // Send version info to analytics, Sentry, etc.
        console.log('Version info logged:', info.semver, info.buildDate);
      }}
    />
  );
};

/**
 * Example: Using the Hook
 * Demonstrates useVersionInfo hook for accessing version data without console output
 */
export const UseVersionInfoExample: React.FC = () => {
  const versionInfo = useVersionInfo('1.0.0.1737727200');

  return (
    <div className="p-4 bg-dark-900 text-slate-300">
      <h3 className="text-gold-400 font-bold mb-2">Version Info</h3>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-500">Version:</dt>
        <dd>{versionInfo.semver}</dd>
        <dt className="text-slate-500">Build:</dt>
        <dd>{versionInfo.buildEpoch}</dd>
        <dt className="text-slate-500">Build Date:</dt>
        <dd>{versionInfo.buildDate}</dd>
      </dl>
    </div>
  );
};

/**
 * Example: Standalone Parse Function
 * Shows how to use parseVersion outside of React
 */
export const ParseVersionExample = () => {
  const version = parseVersion('2.5.1.1737727200');

  console.log('Parsed version:', {
    full: version.full,        // "2.5.1.1737727200"
    semver: version.semver,    // "2.5.1"
    major: version.major,      // 2
    minor: version.minor,      // 5
    patch: version.patch,      // 1
    buildEpoch: version.buildEpoch,  // 1737727200
    buildDate: version.buildDate,    // "2025-01-24 12:00:00 UTC"
  });

  return null;
};

/**
 * Example: Vite Integration (Manual - Two Components)
 * Shows typical usage with Vite environment variables (like Elder's App.tsx)
 */
export const ViteIntegrationExample: React.FC = () => {
  // In a real app, these would come from import.meta.env
  const buildTime = /* import.meta.env.VITE_BUILD_TIME || */ String(Math.floor(Date.now() / 1000));
  const apiUrl = /* import.meta.env.VITE_API_URL || */ '(relative - using nginx proxy)';
  const mode = /* import.meta.env.MODE || */ 'development';

  return (
    <ConsoleVersion
      appName="Elder - Entity Relationship Tracking System"
      version={`1.0.0.${buildTime}`}
      environment={mode}
      emoji="🏛️"
      metadata={{
        'API URL': apiUrl,
      }}
    />
  );
};

/**
 * Example: AppConsoleVersion (RECOMMENDED)
 * Single component that logs both WebUI and API versions automatically.
 * This is the recommended approach for all React applications.
 */
export const AppConsoleVersionExample: React.FC = () => {
  // In a real app, these would come from import.meta.env
  const buildTime = /* import.meta.env.VITE_BUILD_TIME || */ String(Math.floor(Date.now() / 1000));
  const version = /* import.meta.env.VITE_VERSION || */ '1.0.0';
  const mode = /* import.meta.env.MODE || */ 'development';

  return (
    <AppConsoleVersion
      appName="Elder"
      webuiVersion={`${version}.${buildTime}`}
      environment={mode}
      apiStatusUrl="/api/v1/status"
      metadata={{
        'API URL': '(relative - using nginx proxy)',
      }}
    />
  );
};

/**
 * Example: AppConsoleVersion with Custom API Endpoint
 * Shows how to use a different API status endpoint
 */
export const CustomApiEndpointExample: React.FC = () => {
  return (
    <AppConsoleVersion
      appName="MyApp"
      webuiVersion="2.0.0.1737727200"
      environment="production"
      apiStatusUrl="/api/v2/health"
      webuiEmoji="🌐"
      apiEmoji="🔧"
      metadata={{
        'Region': 'us-east-1',
        'Cluster': 'prod-cluster-1',
      }}
      onApiError={(error) => {
        // Send to error tracking service
        console.error('API version fetch failed:', error);
      }}
    />
  );
};

/**
 * Example: Using the useApiVersionInfo Hook
 * Fetch API version info for custom display
 */
export const UseApiVersionInfoExample: React.FC = () => {
  const { apiVersion, loading, error } = useApiVersionInfo('/api/v1/status');

  if (loading) {
    return <div className="text-slate-400">Loading API version...</div>;
  }

  if (error) {
    return <div className="text-red-400">Failed to load API version</div>;
  }

  return (
    <div className="p-4 bg-dark-900 text-slate-300">
      <h3 className="text-gold-400 font-bold mb-2">API Version Info</h3>
      {apiVersion && (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-500">Version:</dt>
          <dd>{apiVersion.semver}</dd>
          <dt className="text-slate-500">Build:</dt>
          <dd>{apiVersion.buildEpoch}</dd>
          <dt className="text-slate-500">Build Date:</dt>
          <dd>{apiVersion.buildDate}</dd>
        </dl>
      )}
    </div>
  );
};

export default BasicConsoleVersionExample;
