# NetBox FMS Plugin - Development Makefile
#
# All Django management commands run from the NetBox source directory
# with the proper settings module.

NETBOX_DIR  := /opt/netbox/netbox
MANAGE      := cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python manage.py
PYTEST      := cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -m pytest
PLUGIN_PKG  := netbox_fms

.DEFAULT_GOAL := help

# ---------------------------------------------------------------------------
# Linting & formatting
# ---------------------------------------------------------------------------

.PHONY: lint
lint: ## Run ruff linter with auto-fix
	ruff check --fix $(PLUGIN_PKG)/

.PHONY: format
format: ## Run ruff formatter
	ruff format $(PLUGIN_PKG)/

.PHONY: check
check: ## Run ruff checks without modifying files
	ruff check $(PLUGIN_PKG)/
	ruff format --check --exclude migrations $(PLUGIN_PKG)/

# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

.PHONY: test
test: ## Run full test suite with coverage
	$(PYTEST) $(CURDIR)/tests/ -v

.PHONY: test-fast
test-fast: ## Run tests without coverage
	$(PYTEST) $(CURDIR)/tests/ -v --no-cov

.PHONY: test-one
test-one: ## Run a single test (usage: make test-one T=tests/test_models.py::TestClass::test_method)
	$(PYTEST) $(CURDIR)/$(T) -v --no-cov

.PHONY: test-k
test-k: ## Run tests matching keyword (usage: make test-k K=fiber_cable)
	$(PYTEST) $(CURDIR)/tests/ -v --no-cov -k "$(K)"

# ---------------------------------------------------------------------------
# Django management
# ---------------------------------------------------------------------------

.PHONY: migrations
migrations: ## Generate new migrations
	$(MANAGE) makemigrations $(PLUGIN_PKG)

.PHONY: migrate
migrate: ## Apply all migrations
	$(MANAGE) migrate

.PHONY: migrate-fresh
migrate-fresh: ## Re-apply plugin migrations from scratch
	$(MANAGE) migrate $(PLUGIN_PKG) zero
	$(MANAGE) migrate $(PLUGIN_PKG)

.PHONY: showmigrations
showmigrations: ## Show migration status
	$(MANAGE) showmigrations $(PLUGIN_PKG)

.PHONY: shell
shell: ## Open Django shell_plus (or shell)
	$(MANAGE) shell_plus 2>/dev/null || $(MANAGE) shell

.PHONY: runserver
runserver: ## Start NetBox development server on port 8080
	$(MANAGE) runserver 0.0.0.0:8080

.PHONY: superuser
superuser: ## Create superuser admin:admin (skip if exists)
	@cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from django.contrib.auth import get_user_model; User = get_user_model(); print('admin user already exists') if User.objects.filter(username='admin').exists() else (User.objects.create_superuser('admin', 'admin@example.com', 'admin'), print('created superuser admin:admin'))"

.PHONY: sample-data
sample-data: ## Load sample FMS data (use FLUSH=1 to reset first)
	$(MANAGE) create_sample_data $(if $(FLUSH),--flush)

.PHONY: collectstatic
collectstatic: ## Collect static files
	$(MANAGE) collectstatic --no-input

# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

.PHONY: verify
verify: ## Verify all plugin modules import cleanly
	@cd $(NETBOX_DIR) && DJANGO_SETTINGS_MODULE=netbox.settings python -c "import django; django.setup(); from $(PLUGIN_PKG).models import *; from $(PLUGIN_PKG).forms import *; from $(PLUGIN_PKG).filters import *; from $(PLUGIN_PKG).tables import *; from $(PLUGIN_PKG).api.serializers import *; from $(PLUGIN_PKG).api.views import *; print('All modules imported successfully')"

.PHONY: validate
validate: check verify ## Run all checks (lint + import verification)

# ---------------------------------------------------------------------------
# Build & release
# ---------------------------------------------------------------------------

.PHONY: build
build: ## Build source and wheel distributions
	python -m build

.PHONY: clean
clean: ## Remove build artifacts
	rm -rf build/ dist/ *.egg-info $(PLUGIN_PKG).egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.PHONY: bump-patch
bump-patch: ## Bump patch version (0.1.x)
	bumpver update --patch

.PHONY: bump-minor
bump-minor: ## Bump minor version (0.x.0)
	bumpver update --minor

.PHONY: bump-major
bump-major: ## Bump major version (x.0.0)
	bumpver update --major

# ---------------------------------------------------------------------------
# TypeScript / frontend
# ---------------------------------------------------------------------------

.PHONY: ts-install
ts-install: ## Install TypeScript build dependencies
	cd netbox_fms/static/netbox_fms && npm install

.PHONY: ts-build
ts-build: ts-install ## Build TypeScript splice editor bundle
	cd netbox_fms/static/netbox_fms && npm run build

.PHONY: ts-watch
ts-watch: ## Watch and rebuild TypeScript on changes
	cd netbox_fms/static/netbox_fms && npm run watch

.PHONY: ts-typecheck
ts-typecheck: ## Run TypeScript type checking
	cd netbox_fms/static/netbox_fms && npm run typecheck

# ---------------------------------------------------------------------------
# Help
# ---------------------------------------------------------------------------

.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-18s\033[0m %s\n", $$1, $$2}'
