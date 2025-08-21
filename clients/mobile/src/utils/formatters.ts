/**
 * Utility functions for formatting data display
 */

export const formatBytes = (bytes: number, decimals = 2): string => {
  if (bytes === 0) return '0 Bytes';

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
};

export const formatDuration = (milliseconds: number): string => {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) {
    return `${days}d ${hours % 24}h ${minutes % 60}m`;
  } else if (hours > 0) {
    return `${hours}h ${minutes % 60}m`;
  } else if (minutes > 0) {
    return `${minutes}m ${seconds % 60}s`;
  } else {
    return `${seconds}s`;
  }
};

export const formatUptime = (startTime: Date): string => {
  const now = new Date();
  const uptimeMs = now.getTime() - startTime.getTime();
  return formatDuration(uptimeMs);
};

export const formatPercentage = (value: number, total: number): string => {
  if (total === 0) return '0%';
  const percentage = (value / total) * 100;
  return `${percentage.toFixed(1)}%`;
};

export const formatLatency = (latencyMs: number): string => {
  if (latencyMs < 1) {
    return `${(latencyMs * 1000).toFixed(0)}μs`;
  } else if (latencyMs < 1000) {
    return `${latencyMs.toFixed(1)}ms`;
  } else {
    return `${(latencyMs / 1000).toFixed(2)}s`;
  }
};

export const formatBandwidth = (bytesPerSecond: number): string => {
  return formatBytes(bytesPerSecond) + '/s';
};