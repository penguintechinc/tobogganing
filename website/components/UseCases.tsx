import React from 'react';
import { 
  BuildingOfficeIcon,
  HomeModernIcon,
  CloudIcon,
  ShieldCheckIcon,
  GlobeAltIcon,
  ServerIcon
} from '@heroicons/react/24/outline';

const useCases = [
  {
    title: 'Remote Workforce',
    description: 'Secure access for distributed teams working from home, co-working spaces, or on the road.',
    icon: HomeModernIcon,
    color: 'bg-blue-500',
    benefits: [
      'Zero Trust access to corporate resources',
      'Seamless user experience across devices',
      'Automatic certificate management',
      'Real-time security monitoring'
    ],
    companies: 'Ideal for companies with 50-5000+ remote employees'
  },
  {
    title: 'Multi-Office Enterprise',
    description: 'Connect multiple office locations with secure site-to-site VPN and centralized management.',
    icon: BuildingOfficeIcon,
    color: 'bg-green-500',
    benefits: [
      'Centralized policy management',
      'Multi-datacenter orchestration',
      'Automatic failover and recovery',
      'Compliance and audit logging'
    ],
    companies: 'Perfect for enterprises with multiple locations'
  },
  {
    title: 'Cloud-First Architecture',
    description: 'Secure connectivity to cloud workloads across AWS, Azure, Google Cloud, and hybrid environments.',
    icon: CloudIcon,
    color: 'bg-purple-500',
    benefits: [
      'Multi-cloud connectivity',
      'Auto-scaling with demand',
      'Infrastructure as code',
      'Cost optimization features'
    ],
    companies: 'Built for cloud-native organizations'
  },
  {
    title: 'Contractor & Partner Access',
    description: 'Provide secure, time-limited access to external contractors and business partners.',
    icon: ShieldCheckIcon,
    color: 'bg-red-500',
    benefits: [
      'Temporary access provisioning',
      'Fine-grained permissions',
      'Activity monitoring and logging',
      'Automatic access revocation'
    ],
    companies: 'Essential for businesses with external collaborators'
  },
  {
    title: 'Global Operations',
    description: 'Scale across continents with regional headend servers and optimized traffic routing.',
    icon: GlobeAltIcon,
    color: 'bg-yellow-500',
    benefits: [
      'Geographic load balancing',
      'Regional data compliance',
      'Low-latency connections',
      ' 24/7 global monitoring'
    ],
    companies: 'Designed for multinational corporations'
  },
  {
    title: 'DevOps & Development',
    description: 'Secure access to development environments, CI/CD pipelines, and production systems.',
    icon: ServerIcon,
    color: 'bg-indigo-500',
    benefits: [
      'Environment-specific access',
      'Integration with CI/CD tools',
      'Developer-friendly clients',
      'Infrastructure automation'
    ],
    companies: 'Optimized for technology teams'
  }
];

const UseCases: React.FC = () => {
  return (
    <div className="bg-white py-20 sm:py-24">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Header */}
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-gray-900 mb-4">
            Use Cases & Solutions
          </h2>
          <p className="text-xl text-gray-600 max-w-3xl mx-auto">
            SASEWaddle adapts to your organization's needs, whether you're securing remote workers,
            connecting offices, or protecting cloud infrastructure.
          </p>
        </div>

        {/* Use Cases Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-16">
          {useCases.map((useCase, index) => (
            <div
              key={useCase.title}
              className="bg-gradient-to-br from-gray-50 to-white rounded-2xl p-8 border border-gray-200 hover:border-primary-300 hover:shadow-lg transition-all duration-300"
            >
              {/* Header */}
              <div className="flex items-center mb-6">
                <div className={`${useCase.color} rounded-xl p-3 mr-4`}>
                  <useCase.icon className="h-6 w-6 text-white" />
                </div>
                <div>
                  <h3 className="text-xl font-semibold text-gray-900">{useCase.title}</h3>
                  <p className="text-sm text-gray-600">{useCase.companies}</p>
                </div>
              </div>

              {/* Description */}
              <p className="text-gray-600 mb-6 leading-relaxed">
                {useCase.description}
              </p>

              {/* Benefits */}
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-gray-900 mb-3">Key Benefits:</h4>
                <ul className="space-y-2">
                  {useCase.benefits.map((benefit, benefitIndex) => (
                    <li key={benefitIndex} className="flex items-start">
                      <div className="w-1.5 h-1.5 bg-primary-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
                      <span className="text-sm text-gray-600">{benefit}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>

        {/* Industry Examples */}
        <div className="bg-gradient-to-r from-primary-50 to-blue-50 rounded-3xl p-8 lg:p-12">
          <div className="text-center mb-12">
            <h3 className="text-2xl font-bold text-gray-900 mb-4">Industry Applications</h3>
            <p className="text-gray-600 max-w-2xl mx-auto">
              See how organizations across different industries use SASEWaddle to secure their networks
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
            <div className="text-center">
              <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-200 mb-4">
                <div className="w-12 h-12 bg-blue-100 rounded-lg flex items-center justify-center mx-auto mb-3">
                  <span className="text-blue-600 font-bold text-lg">💼</span>
                </div>
                <h4 className="font-semibold text-gray-900 mb-2">Financial Services</h4>
                <p className="text-sm text-gray-600">
                  Compliance-ready with audit trails and encryption
                </p>
              </div>
            </div>

            <div className="text-center">
              <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-200 mb-4">
                <div className="w-12 h-12 bg-green-100 rounded-lg flex items-center justify-center mx-auto mb-3">
                  <span className="text-green-600 font-bold text-lg">🏥</span>
                </div>
                <h4 className="font-semibold text-gray-900 mb-2">Healthcare</h4>
                <p className="text-sm text-gray-600">
                  HIPAA-compliant with data protection features
                </p>
              </div>
            </div>

            <div className="text-center">
              <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-200 mb-4">
                <div className="w-12 h-12 bg-purple-100 rounded-lg flex items-center justify-center mx-auto mb-3">
                  <span className="text-purple-600 font-bold text-lg">🏭</span>
                </div>
                <h4 className="font-semibold text-gray-900 mb-2">Manufacturing</h4>
                <p className="text-sm text-gray-600">
                  Secure OT/IT convergence and remote monitoring
                </p>
              </div>
            </div>

            <div className="text-center">
              <div className="bg-white rounded-xl p-6 shadow-sm border border-gray-200 mb-4">
                <div className="w-12 h-12 bg-red-100 rounded-lg flex items-center justify-center mx-auto mb-3">
                  <span className="text-red-600 font-bold text-lg">🎓</span>
                </div>
                <h4 className="font-semibold text-gray-900 mb-2">Education</h4>
                <p className="text-sm text-gray-600">
                  Student and faculty access with role-based permissions
                </p>
              </div>
            </div>
          </div>

          {/* ROI Section */}
          <div className="mt-12 bg-white rounded-2xl p-8 border border-gray-200">
            <div className="text-center mb-8">
              <h4 className="text-xl font-bold text-gray-900 mb-2">Return on Investment</h4>
              <p className="text-gray-600">
                Organizations typically see significant benefits within the first quarter
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
              <div>
                <div className="text-3xl font-bold text-primary-600 mb-2">60%</div>
                <div className="text-sm text-gray-900 font-semibold mb-1">Reduction in VPN Costs</div>
                <div className="text-xs text-gray-600">Compared to traditional VPN solutions</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-green-600 mb-2">90%</div>
                <div className="text-sm text-gray-900 font-semibold mb-1">Faster Deployment</div>
                <div className="text-xs text-gray-600">Infrastructure as code automation</div>
              </div>
              <div>
                <div className="text-3xl font-bold text-purple-600 mb-2">50%</div>
                <div className="text-sm text-gray-900 font-semibold mb-1">Less Admin Overhead</div>
                <div className="text-xs text-gray-600">Automated certificate management</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default UseCases;