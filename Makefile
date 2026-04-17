# Check that we're on the main branch
.PHONY: check-main-branch
check-main-branch:
	@CURRENT_BRANCH=$$(git rev-parse --abbrev-ref HEAD); \
	if [ "$$CURRENT_BRANCH" != "main" ]; then \
		echo "Error: Not on main branch (currently on $$CURRENT_BRANCH)"; \
		echo "Please switch to main branch: git checkout main"; \
		exit 1; \
	fi

# Check that the repository is clean (no uncommitted changes)
.PHONY: check-repo-clean
check-repo-clean:
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "Error: Repository has uncommitted changes:"; \
		git status --short; \
		echo ""; \
		echo "Please commit or stash your changes before building/deploying."; \
		exit 1; \
	fi

.PHONY: clean_build
clean_build:
	rm -rf dist

.PHONY: test
test:
	@echo "Running unit and integration tests..."
	pytest -x -m "not e2e"
	@echo "Running e2e tests..."
	pytest -x -m e2e tests/e2e
	@echo "✓ All tests passed"

# Check that a compatible half-orm release exists on PyPI
.PHONY: check-half-orm-release
check-half-orm-release:
	@echo "Checking half-orm PyPI release compatibility..."
	@python scripts/check_half_orm_release.py

.PHONY: build
build: check-main-branch check-repo-clean check-half-orm-release test clean_build
	@echo "✓ On main branch"
	@echo "✓ Repository is clean"
	@echo "Building package..."
	python -m build

.PHONY: publish
publish: build
	@echo "Publishing to PyPI..."
	twine upload -r half-orm-dev dist/*

# Bump version, verify half-orm compatibility, commit and tag
.PHONY: release
release: check-main-branch check-repo-clean
	@CURRENT=$$(cat half_orm_dev/version.txt | tr -d '[:space:]'); \
	echo "Current version: $$CURRENT"; \
	printf "New version: "; \
	read NEW_VERSION; \
	if [ -z "$$NEW_VERSION" ]; then echo "Aborted."; exit 1; fi; \
	echo "$$NEW_VERSION" > half_orm_dev/version.txt; \
	echo "Checking half-orm PyPI release compatibility for $$NEW_VERSION..."; \
	if ! python scripts/check_half_orm_release.py; then \
		echo "$$CURRENT" > half_orm_dev/version.txt; \
		echo "Version reverted to $$CURRENT"; \
		exit 1; \
	fi; \
	git add half_orm_dev/version.txt; \
	git commit -m "[release] $$NEW_VERSION"; \
	git tag "$$NEW_VERSION"; \
	echo "✓ Committed and tagged $$NEW_VERSION"
