# Minimal Makefile for tasks pre-commit can't handle

.PHONY: help setup test clean build

help:  ## Show available commands
	@echo "🛠️  Development Commands:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "💡 Note: Code formatting/linting handled automatically by pre-commit hooks"

setup:  ## Complete development setup
	poetry install --with dev --extras metadata
	poetry run pre-commit install

test:  ## Run all tests
	poetry run python run_tests.py

test-cov:  ## Run tests with coverage
	poetry run python run_tests.py --coverage

clean:  ## Clean build artifacts and caches
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ .coverage htmlcov/ .mypy_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

build:  ## Build package
	poetry build

# Quick development workflow
dev: test  ## Run tests (main development command)
