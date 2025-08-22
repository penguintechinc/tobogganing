import React, { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/router';
import { Bars3Icon, XMarkIcon } from '@heroicons/react/24/outline';

const navigation = [
  { name: 'Features', href: '/#features' },
  { name: 'Architecture', href: '/#architecture' },
  { name: 'Embedded', href: '/#embedded' },
  { name: 'Pricing', href: '/#pricing' },
  { name: 'Documentation', href: '/docs' },
  { name: 'Downloads', href: '/downloads' },
  { name: 'Use Cases', href: '/use-cases' },
  { name: 'Community', href: '/community' },
];

const Header: React.FC = () => {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const router = useRouter();

  const isActive = (href: string) => {
    if (href.startsWith('/#')) {
      return router.pathname === '/' && router.asPath.includes(href.substring(1));
    }
    return router.pathname.startsWith(href);
  };

  return (
    <header className="bg-white/95 backdrop-blur-md shadow-lg border-b border-primary-200/30 sticky top-0 z-50">
      <nav className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8" aria-label="Global">
        <div className="flex h-18 items-center justify-between">
          {/* Logo */}
          <div className="flex items-center">
            <Link href="/" className="group flex items-center space-x-3 transition-all duration-300 hover:scale-105">
              <div className="h-10 w-10 bg-gradient-to-br from-primary-500 to-secondary-500 rounded-xl flex items-center justify-center shadow-lg group-hover:shadow-xl transition-all duration-300 group-hover:rotate-3">
                <span className="text-white font-bold text-lg">🛷</span>
              </div>
              <span className="text-2xl font-bold bg-gradient-to-r from-primary-600 to-secondary-600 bg-clip-text text-transparent">Tobogganing</span>
            </Link>
          </div>

          {/* Desktop navigation */}
          <div className="hidden lg:flex lg:items-center lg:space-x-2">
            {navigation.map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className={`relative px-4 py-2 text-sm font-medium rounded-xl transition-all duration-300 ${
                  isActive(item.href)
                    ? 'text-primary-600 bg-gradient-to-r from-primary-50 to-secondary-50 shadow-sm'
                    : 'text-gray-600 hover:text-primary-600 hover:bg-primary-50/50'
                }`}
              >
                {item.name}
                {isActive(item.href) && (
                  <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 w-1 h-1 bg-primary-500 rounded-full"></div>
                )}
              </Link>
            ))}
          </div>

          {/* CTA Button */}
          <div className="hidden lg:flex lg:items-center lg:space-x-3">
            <Link
              href="https://github.com/penguintechinc/tobogganing"
              target="_blank"
              rel="noopener noreferrer"
              className="group flex items-center px-3 py-2 text-sm font-medium text-gray-600 hover:text-primary-600 transition-all duration-300 rounded-xl hover:bg-gray-50"
            >
              <span className="mr-1">⭐</span>
              GitHub
            </Link>
            <Link
              href="/downloads"
              className="group relative bg-gradient-to-r from-primary-600 to-secondary-600 text-white px-6 py-2.5 rounded-xl text-sm font-bold hover:from-primary-700 hover:to-secondary-700 transition-all duration-300 shadow-lg hover:shadow-xl transform hover:scale-105"
            >
              <span className="relative z-10 flex items-center">
                🚀 Get Started
              </span>
              <div className="absolute inset-0 bg-gradient-to-r from-accent-600 to-primary-700 rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
            </Link>
          </div>

          {/* Mobile menu button */}
          <div className="lg:hidden">
            <button
              type="button"
              className="text-gray-600 hover:text-gray-900"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              <span className="sr-only">Open main menu</span>
              {mobileMenuOpen ? (
                <XMarkIcon className="h-6 w-6" aria-hidden="true" />
              ) : (
                <Bars3Icon className="h-6 w-6" aria-hidden="true" />
              )}
            </button>
          </div>
        </div>

        {/* Mobile navigation */}
        {mobileMenuOpen && (
          <div className="lg:hidden border-t border-primary-200/30 bg-white/95 backdrop-blur-md">
            <div className="space-y-2 px-4 pb-4 pt-4">
              {navigation.map((item) => (
                <Link
                  key={item.name}
                  href={item.href}
                  className={`block px-4 py-3 text-base font-medium rounded-xl transition-all duration-300 ${
                    isActive(item.href)
                      ? 'text-primary-600 bg-gradient-to-r from-primary-50 to-secondary-50 shadow-sm'
                      : 'text-gray-600 hover:text-primary-600 hover:bg-primary-50/50'
                  }`}
                  onClick={() => setMobileMenuOpen(false)}
                >
                  {item.name}
                </Link>
              ))}
              <div className="border-t border-primary-200/30 pt-4 mt-4 space-y-3">
                <Link
                  href="https://github.com/penguintechinc/tobogganing"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center px-4 py-3 text-base font-medium text-gray-600 hover:text-primary-600 rounded-xl hover:bg-primary-50/50 transition-all duration-300"
                >
                  <span className="mr-2">⭐</span>
                  GitHub
                </Link>
                <Link
                  href="/downloads"
                  className="block mx-2 bg-gradient-to-r from-primary-600 to-secondary-600 text-white px-6 py-3 rounded-xl text-base font-bold hover:from-primary-700 hover:to-secondary-700 transition-all duration-300 text-center shadow-lg"
                >
                  🚀 Get Started
                </Link>
              </div>
            </div>
          </div>
        )}
      </nav>
    </header>
  );
};

export default Header;