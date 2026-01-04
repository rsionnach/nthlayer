# Contributing to NthLayer

First off, thank you for considering contributing to NthLayer! We're in early alpha and actively seeking feedback from the SRE/DevOps community.

## Ways to Contribute

### 1. Try It Out and Share Feedback

The most valuable contribution right now is **using NthLayer on a real service** and telling us what works and what doesn't:

- [Open a Discussion](https://github.com/rsionnach/nthlayer/discussions) to share your experience
- [Report bugs](https://github.com/rsionnach/nthlayer/issues/new?labels=bug) you encounter
- [Request features](https://github.com/rsionnach/nthlayer/issues/new?labels=enhancement) that would help your workflow

### 2. Code Contributions

We welcome pull requests! Here's how to get started:

```bash
# Install uv (https://docs.astral.sh/uv/)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone https://github.com/rsionnach/nthlayer.git
cd nthlayer
uv sync --extra dev      # Install dependencies from lockfile

# Install pre-commit hooks (required)
make pre-commit-install

# Run tests
make test

# Run linting
make lint
```

#### Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Ensure tests pass (`make test`)
5. Ensure linting passes (`make lint`)
6. Commit with a descriptive message
7. Push to your fork and open a PR

### 3. Documentation

Help us improve documentation:

- Fix typos or unclear explanations
- Add examples for your use case
- Improve the getting started guide

### 4. Technology Templates

Add support for new technologies:

- Kafka, RabbitMQ, Cassandra, etc.
- Cloud-specific metrics (AWS RDS, GCP Cloud SQL)
- Custom application metrics

See `src/nthlayer/dashboards/templates/` for existing templates.

## Development Guidelines

### Code Style

- Python 3.11+
- Type hints required
- Ruff for linting and formatting (enforced by pre-commit)
- Follow existing patterns in the codebase

### Commit Messages

```
<type>: <description>

<optional body>
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

### Testing

- Add tests for new features
- Ensure existing tests pass
- Integration tests in `tests/integration/`

## Questions?

- [GitHub Discussions](https://github.com/rsionnach/nthlayer/discussions) - General questions
- [GitHub Issues](https://github.com/rsionnach/nthlayer/issues) - Bug reports and feature requests

## Code of Conduct

Be respectful and constructive. We're all here to build better reliability tooling.

---

**Thank you for helping make NthLayer better!**
