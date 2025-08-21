import React from 'react';
import Link from 'next/link';

const navigation = {
  product: [
    { name: 'Features', href: '/#features' },
    { name: 'Architecture', href: '/#architecture' },
    { name: 'Use Cases', href: '/use-cases' },
    { name: 'Pricing', href: '/pricing' },
  ],
  resources: [
    { name: 'Documentation', href: '/docs' },
    { name: 'API Reference', href: '/docs/api' },
    { name: 'Downloads', href: '/downloads' },
    { name: 'Examples', href: '/docs/examples' },
  ],
  community: [
    { name: 'GitHub', href: 'https://github.com/your-org/sasewaddle' },
    { name: 'Discord', href: 'https://discord.gg/sasewaddle' },
    { name: 'Forum', href: 'https://community.sasewaddle.com' },
    { name: 'Roadmap', href: 'https://github.com/your-org/sasewaddle/projects' },
  ],
  company: [
    { name: 'About', href: '/about' },
    { name: 'Blog', href: '/blog' },
    { name: 'Security', href: '/security' },
    { name: 'Contact', href: '/contact' },
  ],
};

const Footer: React.FC = () => {
  return (
    <footer className="bg-gray-900" aria-labelledby="footer-heading">
      <h2 id="footer-heading" className="sr-only">
        Footer
      </h2>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 lg:py-16">
        <div className="xl:grid xl:grid-cols-3 xl:gap-8">
          {/* Brand Section */}
          <div className="xl:col-span-1">
            <Link href="/" className="flex items-center space-x-2 mb-6">
              <div className="h-8 w-8 bg-primary-600 rounded-lg flex items-center justify-center">
                <span className="text-white font-bold text-sm">SW</span>
              </div>
              <span className="text-xl font-bold text-white">SASEWaddle</span>
            </Link>
            <p className="text-gray-400 text-base max-w-md">
              Open Source SASE solution implementing Zero Trust Network Architecture. 
              Secure, scalable, and enterprise-ready.
            </p>
            <div className="mt-6">
              <p className="text-sm text-gray-500">
                Made with ❤️ by the open source community
              </p>
            </div>
          </div>

          {/* Navigation Links */}
          <div className="mt-12 xl:mt-0 xl:col-span-2">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-8">
              <div>
                <h3 className="text-sm font-semibold text-gray-300 tracking-wider uppercase mb-4">
                  Product
                </h3>
                <ul className="space-y-3">
                  {navigation.product.map((item) => (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        className="text-gray-400 hover:text-white transition-colors duration-200 text-base"
                      >
                        {item.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
              
              <div>
                <h3 className="text-sm font-semibold text-gray-300 tracking-wider uppercase mb-4">
                  Resources
                </h3>
                <ul className="space-y-3">
                  {navigation.resources.map((item) => (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        className="text-gray-400 hover:text-white transition-colors duration-200 text-base"
                      >
                        {item.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
              
              <div>
                <h3 className="text-sm font-semibold text-gray-300 tracking-wider uppercase mb-4">
                  Community
                </h3>
                <ul className="space-y-3">
                  {navigation.community.map((item) => (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        target={item.href.startsWith('http') ? '_blank' : undefined}
                        rel={item.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                        className="text-gray-400 hover:text-white transition-colors duration-200 text-base"
                      >
                        {item.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
              
              <div>
                <h3 className="text-sm font-semibold text-gray-300 tracking-wider uppercase mb-4">
                  Company
                </h3>
                <ul className="space-y-3">
                  {navigation.company.map((item) => (
                    <li key={item.name}>
                      <Link
                        href={item.href}
                        className="text-gray-400 hover:text-white transition-colors duration-200 text-base"
                      >
                        {item.name}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Newsletter Signup */}
        <div className="mt-12 pt-8 border-t border-gray-800">
          <div className="md:flex md:items-center md:justify-between">
            <div className="md:flex-1">
              <h3 className="text-lg font-semibold text-white mb-2">
                Stay updated
              </h3>
              <p className="text-gray-400 text-base">
                Get notified about new releases and security updates.
              </p>
            </div>
            <div className="mt-6 md:mt-0 md:ml-8">
              <form className="flex flex-col sm:flex-row gap-3">
                <input
                  type="email"
                  placeholder="Enter your email"
                  className="min-w-0 flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-400 focus:border-primary-500 focus:ring-1 focus:ring-primary-500 focus:outline-none"
                />
                <button
                  type="submit"
                  className="bg-primary-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-primary-700 transition-colors duration-200 whitespace-nowrap"
                >
                  Subscribe
                </button>
              </form>
            </div>
          </div>
        </div>

        {/* Bottom Section */}
        <div className="mt-12 pt-8 border-t border-gray-800">
          <div className="md:flex md:items-center md:justify-between">
            <div className="flex space-x-6 md:order-2">
              <Link
                href="https://github.com/your-org/sasewaddle"
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-400 hover:text-white transition-colors duration-200"
              >
                <span className="sr-only">GitHub</span>
                <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24">
                  <path
                    fillRule="evenodd"
                    d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                    clipRule="evenodd"
                  />
                </svg>
              </Link>
              
              <Link
                href="https://twitter.com/sasewaddle"
                target="_blank"
                rel="noopener noreferrer"
                className="text-gray-400 hover:text-white transition-colors duration-200"
              >
                <span className="sr-only">Twitter</span>
                <svg className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M8.29 20.251c7.547 0 11.675-6.253 11.675-11.675 0-.178 0-.355-.012-.53A8.348 8.348 0 0022 5.92a8.19 8.19 0 01-2.357.646 4.118 4.118 0 001.804-2.27 8.224 8.224 0 01-2.605.996 4.107 4.107 0 00-6.993 3.743 11.65 11.65 0 01-8.457-4.287 4.106 4.106 0 001.27 5.477A4.072 4.072 0 012.8 9.713v.052a4.105 4.105 0 003.292 4.022 4.095 4.095 0 01-1.853.07 4.108 4.108 0 003.834 2.85A8.233 8.233 0 012 18.407a11.616 11.616 0 006.29 1.84" />
                </svg>
              </Link>
            </div>
            
            <div className="mt-8 md:mt-0 md:order-1">
              <div className="flex flex-col sm:flex-row sm:items-center space-y-2 sm:space-y-0 sm:space-x-6">
                <p className="text-base text-gray-400">
                  &copy; 2024 SASEWaddle. Open Source under MIT License.
                </p>
                <div className="flex space-x-6">
                  <Link
                    href="/privacy"
                    className="text-gray-400 hover:text-white transition-colors duration-200 text-sm"
                  >
                    Privacy
                  </Link>
                  <Link
                    href="/terms"
                    className="text-gray-400 hover:text-white transition-colors duration-200 text-sm"
                  >
                    Terms
                  </Link>
                  <Link
                    href="/security"
                    className="text-gray-400 hover:text-white transition-colors duration-200 text-sm"
                  >
                    Security
                  </Link>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
};

export default Footer;