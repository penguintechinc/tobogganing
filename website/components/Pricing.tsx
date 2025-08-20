import React from 'react';
import {
  CheckIcon,
  XMarkIcon,
  StarIcon,
  ShieldCheckIcon,
  CloudIcon,
  PhoneIcon,
  EnvelopeIcon,
} from '@heroicons/react/24/outline';

const pricingTiers = [
  {
    name: 'Community',
    id: 'community',
    href: 'https://github.com/your-org/sasewaddle',
    price: '$0',
    period: 'forever',
    description: 'Perfect for personal projects, small teams, and getting started with SASE.',
    features: [
      'Up to 10 users',
      'Basic WireGuard VPN',
      'Community support',
      'Docker deployment',
      'Basic monitoring',
      'Open source license',
    ],
    notIncluded: [
      'Enterprise support',
      'Advanced features',
      'SLA guarantees',
      'Priority updates',
    ],
    buttonText: 'Get Started Free',
    buttonVariant: 'secondary',
    popular: false,
  },
  {
    name: 'Enterprise',
    id: 'enterprise',
    href: 'mailto:sales@penguintech.io?subject=SASEWaddle Enterprise License Inquiry',
    price: '$5',
    period: 'per user/month',
    description: 'Full-featured enterprise deployment with support and advanced security.',
    features: [
      'Unlimited users',
      'Advanced security features',
      'Multi-datacenter support',
      'Priority support & SLA',
      'Advanced monitoring',
      'Compliance reporting',
      'SSO/SAML integration',
      'Traffic mirroring',
      'Custom integrations',
      'Regular security updates',
    ],
    notIncluded: [],
    buttonText: 'Contact Sales',
    buttonVariant: 'primary',
    popular: true,
    bulkDiscount: true,
  },
  {
    name: 'Embedded',
    id: 'embedded',
    href: 'mailto:sales@penguintech.io?subject=SASEWaddle Embedded Solutions Inquiry',
    price: 'Custom',
    period: 'pricing',
    description: 'Custom SASEWaddle implementations for embedded systems and IoT devices.',
    features: [
      'Hardware integration',
      'Custom firmware',
      'Edge-to-cloud security',
      'Hardware certification',
      'Dedicated engineering',
      'Custom development',
      'Long-term support',
      'Hardware partnerships',
    ],
    notIncluded: [],
    buttonText: 'Contact Sales',
    buttonVariant: 'secondary',
    popular: false,
  },
];

const Pricing: React.FC = () => {
  return (
    <div id="pricing" className="bg-white py-20 sm:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            💰 Simple, Transparent Pricing
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            Start free with our open source community edition, or choose enterprise for advanced features and support.
          </p>
        </div>

        {/* Pricing Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-16">
          {pricingTiers.map((tier) => (
            <div
              key={tier.id}
              className={`relative rounded-2xl border ${
                tier.popular
                  ? 'border-primary-300 ring-2 ring-primary-600 shadow-lg'
                  : 'border-gray-200 shadow-sm'
              } bg-white p-8 hover:shadow-lg transition-shadow duration-300`}
            >
              {/* Popular Badge */}
              {tier.popular && (
                <div className="absolute -top-4 left-1/2 transform -translate-x-1/2">
                  <div className="inline-flex items-center px-4 py-2 bg-primary-600 text-white text-sm font-medium rounded-full">
                    <StarIcon className="h-4 w-4 mr-1" />
                    Most Popular
                  </div>
                </div>
              )}

              {/* Header */}
              <div className="text-center mb-8">
                <h3 className="text-2xl font-bold text-gray-900 mb-2">{tier.name}</h3>
                <div className="mb-4">
                  <span className="text-4xl font-bold text-gray-900">{tier.price}</span>
                  {tier.period && (
                    <span className="text-lg text-gray-500 ml-1">/{tier.period}</span>
                  )}
                </div>
                <p className="text-gray-600">{tier.description}</p>
              </div>

              {/* Bulk Discount Notice */}
              {tier.bulkDiscount && (
                <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg">
                  <div className="flex items-center">
                    <div className="flex-shrink-0">
                      <CheckIcon className="h-5 w-5 text-green-600" />
                    </div>
                    <div className="ml-3">
                      <p className="text-sm font-medium text-green-800">
                        Bulk Discounts Available
                      </p>
                      <p className="text-sm text-green-700">
                        Special pricing for 100+ users. Contact sales for volume discounts.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Features */}
              <div className="mb-8">
                <ul className="space-y-3">
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex items-start">
                      <CheckIcon className="h-5 w-5 text-green-500 mt-0.5 mr-3 flex-shrink-0" />
                      <span className="text-gray-700 text-sm">{feature}</span>
                    </li>
                  ))}
                  {tier.notIncluded.map((feature) => (
                    <li key={feature} className="flex items-start">
                      <XMarkIcon className="h-5 w-5 text-gray-400 mt-0.5 mr-3 flex-shrink-0" />
                      <span className="text-gray-400 text-sm">{feature}</span>
                    </li>
                  ))}
                </ul>
              </div>

              {/* CTA Button */}
              <a
                href={tier.href}
                className={`block w-full text-center px-6 py-3 rounded-lg font-medium transition-colors duration-200 ${
                  tier.buttonVariant === 'primary'
                    ? 'bg-primary-600 text-white hover:bg-primary-700'
                    : 'bg-gray-100 text-gray-900 hover:bg-gray-200 border border-gray-300'
                }`}
              >
                {tier.buttonText}
              </a>
            </div>
          ))}
        </div>

        {/* Enterprise Contact Section */}
        <div className="bg-gradient-to-r from-primary-600 to-blue-600 rounded-2xl p-8 lg:p-12">
          <div className="max-w-4xl mx-auto text-center text-white">
            <h3 className="text-2xl sm:text-3xl font-bold mb-4">
              🏢 Enterprise Solutions & Volume Discounts
            </h3>
            <p className="text-lg text-blue-100 mb-8 max-w-3xl mx-auto">
              Need custom deployment, integration support, or volume licensing? 
              Our enterprise team provides tailored solutions for organizations of all sizes.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
              <div className="text-center">
                <div className="w-16 h-16 bg-white bg-opacity-20 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <ShieldCheckIcon className="h-8 w-8 text-white" />
                </div>
                <h4 className="text-lg font-semibold mb-2">Volume Discounts</h4>
                <p className="text-blue-100 text-sm">
                  Special pricing for 100+ users with tiered discounts up to 40% off
                </p>
              </div>

              <div className="text-center">
                <div className="w-16 h-16 bg-white bg-opacity-20 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <CloudIcon className="h-8 w-8 text-white" />
                </div>
                <h4 className="text-lg font-semibold mb-2">Custom Deployments</h4>
                <p className="text-blue-100 text-sm">
                  Multi-cloud, hybrid, and air-gapped deployment options available
                </p>
              </div>

              <div className="text-center">
                <div className="w-16 h-16 bg-white bg-opacity-20 rounded-2xl flex items-center justify-center mx-auto mb-4">
                  <PhoneIcon className="h-8 w-8 text-white" />
                </div>
                <h4 className="text-lg font-semibold mb-2">Dedicated Support</h4>
                <p className="text-blue-100 text-sm">
                  24/7 support, SLA guarantees, and dedicated customer success manager
                </p>
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
              {/* Email Contact */}
              <a
                href="mailto:sales@penguintech.io?subject=SASEWaddle Enterprise Pricing Inquiry"
                className="inline-flex items-center px-6 py-3 bg-white text-primary-600 font-semibold rounded-lg hover:bg-blue-50 transition-colors group"
              >
                <EnvelopeIcon className="h-5 w-5 mr-2 group-hover:scale-110 transition-transform" />
                sales@penguintech.io
              </a>

              {/* Schedule Demo */}
              <a
                href="mailto:sales@penguintech.io?subject=SASEWaddle Demo Request"
                className="inline-flex items-center px-6 py-3 bg-transparent border-2 border-white text-white font-semibold rounded-lg hover:bg-white hover:text-primary-600 transition-colors"
              >
                Schedule Demo
              </a>
            </div>

            <div className="mt-8 text-sm text-blue-200">
              <p>
                ✓ Free consultation • ✓ Proof of concept • ✓ Migration assistance • ✓ Training included
              </p>
            </div>
          </div>
        </div>

        {/* Volume Pricing Table */}
        <div className="mt-20">
          <div className="text-center mb-12">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Volume Pricing Tiers</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              Enterprise licensing includes volume discounts for larger deployments
            </p>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 overflow-hidden">
            <div className="grid grid-cols-1 lg:grid-cols-4 divide-y lg:divide-y-0 lg:divide-x divide-gray-200">
              <div className="p-6 text-center">
                <h4 className="text-lg font-semibold text-gray-900 mb-2">Starter</h4>
                <div className="text-3xl font-bold text-primary-600 mb-2">$5</div>
                <div className="text-sm text-gray-500 mb-4">per user/month</div>
                <div className="text-sm text-gray-600">1-99 users</div>
              </div>

              <div className="p-6 text-center bg-blue-50">
                <h4 className="text-lg font-semibold text-gray-900 mb-2">Growth</h4>
                <div className="text-3xl font-bold text-primary-600 mb-2">$4</div>
                <div className="text-sm text-gray-500 mb-4">per user/month</div>
                <div className="text-sm text-gray-600">100-499 users</div>
                <div className="inline-flex items-center px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full mt-2">
                  20% off
                </div>
              </div>

              <div className="p-6 text-center">
                <h4 className="text-lg font-semibold text-gray-900 mb-2">Scale</h4>
                <div className="text-3xl font-bold text-primary-600 mb-2">$3.50</div>
                <div className="text-sm text-gray-500 mb-4">per user/month</div>
                <div className="text-sm text-gray-600">500-999 users</div>
                <div className="inline-flex items-center px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full mt-2">
                  30% off
                </div>
              </div>

              <div className="p-6 text-center bg-purple-50">
                <h4 className="text-lg font-semibold text-gray-900 mb-2">Enterprise</h4>
                <div className="text-3xl font-bold text-primary-600 mb-2">$3</div>
                <div className="text-sm text-gray-500 mb-4">per user/month</div>
                <div className="text-sm text-gray-600">1000+ users</div>
                <div className="inline-flex items-center px-2 py-1 bg-green-100 text-green-800 text-xs font-medium rounded-full mt-2">
                  40% off
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Pricing;