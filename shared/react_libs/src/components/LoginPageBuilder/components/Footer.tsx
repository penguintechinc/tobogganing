import React from 'react';
import type { FooterProps, LoginColorConfig } from '../types';
import { ELDER_LOGIN_THEME } from '../themes/elderTheme';

/**
 * Footer component for login page.
 *
 * Features:
 * - "A Penguin Technologies Inc. Application" attribution
 * - Link to LICENSE.md on GitHub repository
 * - Auto-generated copyright year
 */
export const Footer: React.FC<FooterProps> = ({ githubRepo, colors }) => {
  const theme: LoginColorConfig = { ...ELDER_LOGIN_THEME, ...colors };
  const currentYear = new Date().getFullYear();

  // Build LICENSE URL from GitHub repo
  const licenseUrl = githubRepo
    ? `https://github.com/${githubRepo}/blob/main/LICENSE.md`
    : null;

  return (
    <footer className={`mt-8 text-center ${theme.footerText}`}>
      <p className="text-sm">
        A{' '}
        <a
          href="https://www.penguintech.io"
          className={`${theme.footerLinkText} hover:underline`}
          target="_blank"
          rel="noopener noreferrer"
        >
          Penguin Technologies Inc.
        </a>{' '}
        Application
      </p>

      <p className="text-xs mt-2">
        &copy; {currentYear} Penguin Technologies Inc.
        {licenseUrl && (
          <>
            {' | '}
            <a
              href={licenseUrl}
              className={`${theme.footerLinkText} hover:underline`}
              target="_blank"
              rel="noopener noreferrer"
            >
              License
            </a>
          </>
        )}
      </p>
    </footer>
  );
};
