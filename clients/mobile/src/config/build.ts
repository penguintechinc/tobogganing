// Build configuration - This file is auto-generated during CI/CD builds
// Default configuration for development

export const BUILD_CONFIG = {
  VERSION: '1.0.0',
  BUILD_TYPE: 'development',
  API_ENDPOINT: 'https://api-dev.sasewaddle.com'
};

export const API_ENDPOINTS = {
  development: 'https://api-dev.sasewaddle.com',
  staging: 'https://api-staging.sasewaddle.com', 
  production: 'https://api.sasewaddle.com'
};

export const getApiEndpoint = (buildType: string = BUILD_CONFIG.BUILD_TYPE) => {
  return API_ENDPOINTS[buildType as keyof typeof API_ENDPOINTS] || API_ENDPOINTS.development;
};