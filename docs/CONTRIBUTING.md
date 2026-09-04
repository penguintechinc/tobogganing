# 🤝 Contributing to Tobogganing

Thank you for your interest in contributing to Tobogganing! We welcome contributions from the community and appreciate your help in making this project better.

## 📋 Table of Contents

- [🚀 Getting Started](#-getting-started)
- [💻 Development Setup](#-development-setup)
- [🔄 Contribution Process](#-contribution-process)
- [📝 Code Standards](#-code-standards)
- [🧪 Testing](#-testing)
- [📚 Documentation](#-documentation)
- [🐛 Bug Reports](#-bug-reports)
- [💡 Feature Requests](#-feature-requests)
- [🔒 Security Issues](#-security-issues)
- [👥 Community](#-community)

## 🚀 Getting Started

### Prerequisites

- 🐍 **Python 3.12+** for Manager service
- 🐹 **Go 1.23+** for Headend server and native clients
- 🟢 **Node.js 18+** for website development
- 🐳 **Docker** for containerized development
- 📦 **Git** for version control

### 🍴 Fork and Clone

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/your-username/tobogganing.git
   cd tobogganing
   ```

## 💻 Development Setup

### 🔧 Environment Setup

#### Python Environment (Manager)
```bash
cd manager
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

#### Go Environment (Headend)
```bash
cd headend
go mod download
```

#### Node.js Environment (Website)
```bash
cd website
npm install
```

### 🐳 Docker Development

```bash
cd deploy/docker-compose
docker-compose -f docker-compose.dev.yml up -d
```

## 🔄 Contribution Process

### 1. 📋 Create an Issue
- 🐛 For **bug reports**, use the bug report template
- 💡 For **feature requests**, use the feature request template
- 📚 For **documentation**, create a documentation issue

### 2. 🌿 Create a Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

### 3. 💻 Make Changes
- ✅ Follow coding standards
- 🧪 Add tests for new functionality
- 📚 Update documentation as needed
- 🔍 Run linters and tests locally

### 4. 📤 Submit Pull Request
- 📝 Use clear, descriptive commit messages
- 📋 Fill out the pull request template
- 🔗 Link to related issues
- ✅ Ensure all CI checks pass

### 5. 👀 Code Review
- 🕐 Be patient during review process
- 💬 Address reviewer feedback
- ✨ Update code as requested
- 🎉 Celebrate when merged!

## 📝 Code Standards

### 🐍 Python (Manager Service)
- 📏 Follow **PEP 8** style guide
- 🏷️ Use **type hints** for all functions
- 📖 Write **docstrings** for classes and methods
- ⚡ Use **async/await** for I/O operations
- 🧪 Include **unit tests** for new code

```python
async def generate_certificate(
    node_id: str,
    node_type: str,
    validity_days: int = 365
) -> Dict[str, Any]:
    """Generate X.509 certificate for node authentication.

    Args:
        node_id: Unique node identifier
        node_type: Type of node (client/headend)
        validity_days: Certificate validity period

    Returns:
        Certificate data with private key

    Raises:
        CertificateError: If generation fails
    """
    pass
```

### 🐹 Go (Headend & Clients)
- 🎨 Follow **Go conventions** and use `gofmt`
- 🔄 Use **context** for cancellation
- ❌ Handle **errors** explicitly
- 📊 Use **structured logging**
- 🧪 Write **comprehensive tests**

```go
// AuthenticateClient verifies client credentials
func (a *Authenticator) AuthenticateClient(
    ctx context.Context,
    cert *x509.Certificate,
    token string,
) (*AuthResult, error) {
    if cert == nil {
        return nil, errors.New("certificate required")
    }
    // Implementation
}
```

### 🟢 TypeScript (Website)
- 📏 Follow **TypeScript best practices**
- ⚛️ Use **React Hooks** patterns
- ♿ Write **accessible** components
- 🎨 Use **Tailwind CSS** for styling
- 📚 Document **component props**

## 🧪 Testing

### Test Types
- 🔬 **Unit Tests**: Individual functions/methods
- 🔗 **Integration Tests**: Component interactions
- 🎭 **End-to-End Tests**: Complete user workflows
- 🔒 **Security Tests**: Authentication/authorization
- ⚡ **Performance Tests**: Load and stress testing

### Running Tests
```bash
# 🐍 Python tests
cd manager && source venv/bin/activate
pytest tests/ -v --cov=.

# 🐹 Go tests (Headend)
cd headend
go test -v -race ./...

# 🟢 Website tests
cd website
npm test
```

### Coverage Goals
- 🎯 **80%+** code coverage for new code
- 🛡️ **100%** coverage for security components
- 🔗 Integration tests for all API endpoints
- 🎭 E2E tests for critical user journeys

## 📚 Documentation

### Documentation Types
- 💻 **Code Comments**: Inline documentation
- 🔌 **API Docs**: REST API reference
- 📖 **User Guides**: Installation and usage
- 🏗️ **Developer Guides**: Architecture docs
- 🚀 **Deployment Guides**: Production setup

### Standards
- ✍️ Write docs **during** development
- 🔤 Use **clear, concise** language
- 💡 Include **examples** where helpful
- 🔄 Keep docs **synchronized** with code
- 🎨 Use **emojis and icons** for visual appeal

## 🐛 Bug Reports

When reporting bugs, include:

- 📋 **Summary**: Clear issue description
- 🖥️ **Environment**: OS, versions, deployment
- 🔄 **Steps**: Detailed reproduction steps
- ✅ **Expected**: What should happen
- ❌ **Actual**: What actually happens
- 📝 **Logs**: Error messages and output
- ⚙️ **Config**: Relevant configuration (sanitized)

## 💡 Feature Requests

For new features, include:

- 🎯 **Problem**: What issue does this solve?
- 💭 **Solution**: Proposed implementation
- 🔄 **Alternatives**: Other options considered
- 👥 **Users**: Who benefits from this?
- 🔧 **Technical**: Implementation approach

## 🔒 Security Issues

⚠️ **DO NOT** create public issues for security vulnerabilities!

Instead:
1. 📧 Email **security@tobogganing.com**
2. 📄 Include detailed vulnerability info
3. ⏰ Allow reasonable response time
4. 🤝 Follow responsible disclosure

## 👥 Community

### 💬 Communication
- 🐙 **GitHub Issues**: Bug reports and features
- 💭 **GitHub Discussions**: Questions and ideas
- 💬 **Discord**: Real-time community chat
- 📧 **Email**: Security and urgent matters

### 🤝 Code of Conduct
We are committed to a welcoming, inclusive environment for all contributors. Please be:
- 🤗 **Respectful** and considerate
- 🎯 **Constructive** in feedback
- 🌟 **Collaborative** and helpful
- 📚 **Patient** with newcomers

### 🏆 Recognition
Contributors are recognized through:
- 📜 Repository contributor list
- 📰 Release notes mentions
- 🎖️ Annual appreciation posts
- 🌟 Special contributor badges

## 📄 License

By contributing to Tobogganing, you agree that your contributions will be licensed under the **MIT License**.

---

🙏 **Thank you for contributing to Tobogganing!** Together, we're making secure networking accessible to everyone! 🚀
