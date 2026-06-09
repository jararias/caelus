-include .env
export UV_PUBLISH_TOKEN
export UV_PUBLISH_TEST_TOKEN

VERSION := $(shell grep -m 1 '^version[[:space:]]*=[[:space:]]*' pyproject.toml | cut -d'"' -f2 | cut -d"'" -f2)

.PHONY: ipython3
ipython3:
	@uv run ipython --profile-dir=.ipython

.PHONY: init-venv
init-venv:
	@echo "🚀 Re-installing the virtual environment with all extras"
	@uv sync --reinstall --all-extras
	@attr -s com.dropbox.ignored -V 1 .venv  # instruct dropbox to ignore the .venv folder
	@echo "✅ .venv re-installed and ignored in dropbox"

.PHONY: clean
clean:
	@echo "🚀 Cleaning project"
	@rm -rf build
	@rm -rf dist
	@rm -rf site
	@rm -rf *.egg-info
	@rm -rf .pytest_cache
	@rm -f MANIFEST
	@find . -name "__pycache__" -print0 | xargs -0 -I {} /bin/rm -rf "{}"
	@echo "✅ Cleaned"

.PHONY: publish-test
publish-test:
	@echo "🚀 Publishing version v$(VERSION) on test-pypi"
	@uv build
	@echo "✅ Package built"
	@uv run scripts/create_env.py
	@[ -f ".env" ] || { echo "❌ Error: the file .env does not exists."; exit 1; }
	@echo "✅ File .env created"
	@set -a; . ./.env; set +a; \
	  test -n "$$UV_PUBLISH_TEST_TOKEN" || (echo "❌ Error: UV_PUBLISH_TEST_TOKEN is not defined in .env"; exit 1)
	@set -a; . ./.env; set +a; uv publish --publish-url https://test.pypi.org/legacy/ --token $$UV_PUBLISH_TEST_TOKEN
	@echo "✅ Package published on test-pypi"
	@rm -f .env
	@echo "✅ File .env deleted"
	@rm -rf dist
	@echo "✅ dist directory deleted"

.PHONY: publish
publish:
	@echo "🚀 Publishing version v$(VERSION) on pypi"
	@uv build
	@echo "✅ Package built"
	@uv run scripts/create_env.py
	@[ -f ".env" ] || { echo "❌ Error: the file .env does not exists."; exit 1; }
	@echo "✅ File .env created"
	@set -a; . ./.env; set +a; \
	  test -n "$$UV_PUBLISH_TOKEN" || (echo "❌ Error: UV_PUBLISH_TOKEN no está definido (créalo en .env)"; exit 1)
	@set -a; . ./.env; set +a; uv publish
	@echo "✅ Package published on pypi"
	@rm -f .env
	@echo "✅ File .env deleted"
	@rm -rf dist
	@echo "✅ dist directory deleted"

.PHONY: check-gh
check-gh:
	@command -v gh >/dev/null 2>&1 || { echo "❌ Error: 'gh' cli no está instalada. Instálala primero."; exit 1; }
	@gh auth status >/dev/null 2>&1 || { echo "❌ Error: No has iniciado sesión en 'gh'. Ejecuta 'gh auth login'."; exit 1; }

.PHONY: release
release: check-gh
	@echo "🚀 Preparing release v$(VERSION)..."
	@git tag -a v$(VERSION) -m "Release v$(VERSION)"
	@git push origin v$(VERSION)
	@echo "✅ Release created and pushed"
	@gh release create v$(VERSION) --title "Release v$(VERSION)" --generate-notes --verify-tag
	@echo "✅ Release v$(VERSION) created on GitHub"
