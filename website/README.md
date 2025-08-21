# SASEWaddle Website

This is the official website and documentation portal for SASEWaddle, built with Next.js and deployed on Cloudflare Pages.

## Features

- **Marketing Website**: Product overview, features, and use cases
- **Documentation Portal**: Comprehensive guides and API reference
- **Download Center**: Binary releases and installation guides
- **Community Hub**: Links to Discord, GitHub, and forums
- **Performance Optimized**: Built for Cloudflare Edge with SSG
- **SEO Optimized**: Meta tags, structured data, and sitemap
- **Responsive Design**: Mobile-first design with Tailwind CSS
- **Accessibility**: WCAG 2.1 compliant with keyboard navigation

## Tech Stack

- **Framework**: Next.js 14 with App Router
- **Styling**: Tailwind CSS with custom design system
- **Icons**: Heroicons
- **Deployment**: Cloudflare Pages with Edge Runtime
- **Analytics**: Cloudflare Web Analytics
- **Fonts**: Inter and JetBrains Mono (Google Fonts)

## Development

### Prerequisites

- Node.js 18+ 
- npm or yarn
- Cloudflare account (for deployment)

### Getting Started

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Start development server**:
   ```bash
   npm run dev
   ```

3. **Open browser**:
   Navigate to [http://localhost:3000](http://localhost:3000)

### Environment Variables

Create a `.env.local` file in the root directory:

```env
NEXT_PUBLIC_SITE_URL=http://localhost:3000
NEXT_PUBLIC_GITHUB_URL=https://github.com/your-org/sasewaddle
NEXT_PUBLIC_DOCS_URL=http://localhost:3000/docs
```

### Project Structure

```
website/
├── components/          # React components
│   ├── Layout.tsx      # Main layout wrapper
│   ├── Header.tsx      # Navigation header
│   ├── Footer.tsx      # Site footer
│   ├── Hero.tsx        # Landing page hero
│   ├── Features.tsx    # Features section
│   ├── Architecture.tsx # Architecture overview
│   ├── UseCases.tsx    # Use cases and examples
│   └── CallToAction.tsx # CTA sections
├── pages/              # Next.js pages
│   ├── index.tsx       # Homepage
│   ├── downloads.tsx   # Download page
│   ├── docs/           # Documentation pages
│   ├── use-cases.tsx   # Use cases page
│   ├── community.tsx   # Community page
│   ├── _app.tsx        # App configuration
│   └── _document.tsx   # Document configuration
├── public/             # Static assets
├── styles/             # CSS files
├── lib/                # Utility functions
├── functions/          # Cloudflare Workers functions
├── next.config.js      # Next.js configuration
├── tailwind.config.js  # Tailwind configuration
├── wrangler.toml       # Cloudflare configuration
└── package.json        # Dependencies
```

## Building and Deployment

### Local Build

```bash
# Standard Next.js build
npm run build

# Build for Cloudflare Pages
npm run pages:build
```

### Cloudflare Pages Deployment

1. **Connect GitHub repository** to Cloudflare Pages

2. **Configure build settings**:
   - Build command: `npm run pages:build`
   - Build output directory: `.vercel/output/static`
   - Root directory: `website`

3. **Set environment variables** in Cloudflare dashboard

4. **Deploy**: Push to main branch triggers automatic deployment

### Manual Deployment

```bash
# Deploy to Cloudflare Pages
npm run pages:deploy
```

## Content Management

### Adding New Pages

1. Create page in `pages/` directory
2. Add navigation link in `components/Header.tsx`
3. Update sitemap in `public/sitemap.xml`

### Updating Documentation

Documentation pages are in `pages/docs/`. Each page should:
- Use the `Layout` component
- Include proper meta tags
- Follow content structure guidelines
- Link to related pages

### Adding Blog Posts

Blog functionality can be added by:
1. Creating `pages/blog/` directory
2. Adding markdown processing with `gray-matter` and `remark`
3. Creating blog layout components
4. Adding RSS feed generation

## SEO and Performance

### SEO Features

- Meta tags and Open Graph
- Structured data (JSON-LD)
- Canonical URLs
- XML sitemap
- Robots.txt
- Performance optimizations

### Performance Optimizations

- Static site generation (SSG)
- Image optimization with Next.js
- Font optimization and preloading
- CSS and JavaScript minification
- CDN distribution via Cloudflare
- Service worker for caching

### Monitoring

- Cloudflare Web Analytics
- Core Web Vitals tracking
- Error monitoring with Sentry (optional)
- Performance monitoring

## Accessibility

The website follows WCAG 2.1 guidelines:

- Semantic HTML structure
- Keyboard navigation support
- Screen reader compatibility
- Color contrast compliance
- Focus management
- Alt text for images
- Skip navigation links

## Contributing

### Code Style

- Use TypeScript for all components
- Follow ESLint configuration
- Use Prettier for code formatting
- Follow Tailwind CSS conventions
- Write accessible HTML

### Content Guidelines

- Use clear, concise language
- Include code examples where helpful
- Optimize images before adding
- Test on mobile devices
- Validate HTML and accessibility

### Submitting Changes

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test locally
5. Submit a pull request

## Troubleshooting

### Common Issues

1. **Build fails on Cloudflare**:
   - Check Node.js version compatibility
   - Verify environment variables
   - Review build logs for specific errors

2. **Images not loading**:
   - Ensure images are in `public/` directory
   - Check image paths are correct
   - Verify image optimization settings

3. **Styles not applying**:
   - Check Tailwind CSS configuration
   - Verify CSS imports in `_app.tsx`
   - Clear browser cache

### Getting Help

- Check GitHub Issues
- Join our Discord community
- Review Cloudflare Pages documentation
- Next.js documentation

## License

The website source code is available under the MIT License. Content and documentation are licensed under Creative Commons.

## Security

- Report security issues to security@sasewaddle.com
- All dependencies are regularly updated
- Security headers are configured
- CSP policy implemented
- No sensitive data in client-side code