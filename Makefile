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
build: check-main-branch check-half-orm-release check-repo-clean test clean_build
	@echo "✓ On main branch"
	@echo "✓ Repository is clean"
	@echo "Building package..."
	python -m build

# HEAD must be the commit `make release` tagged: what is uploaded is what the
# tag names, and nothing else.
.PHONY: check-publish-ready
check-publish-ready:
	@VERSION=$$(cat half_orm_dev/version.txt | tr -d '[:space:]'); \
	if [ "$$(git tag --points-at HEAD | grep -Fx "$$VERSION")" != "$$VERSION" ]; then \
		echo "Error: HEAD is not tagged $$VERSION. Run 'make release' first."; \
		exit 1; \
	fi; \
	echo "✓ HEAD is tagged $$VERSION"

# The tag is pushed before the upload, and must be: a release whose tag is not
# on GitHub is a release nobody can find the source of. (The same defect was
# fixed in half-orm's Makefile.)
.PHONY: publish
publish: check-publish-ready build
	@VERSION=$$(cat half_orm_dev/version.txt | tr -d '[:space:]'); \
	echo "Pushing tag $$VERSION..."; \
	git push origin "refs/tags/$$VERSION"
	@echo "Publishing to PyPI..."
	twine upload -r half-orm-dev dist/*

# Bump version, verify half-orm compatibility, commit and tag.
# half-orm follows Semantic Versioning: the dependency is half-orm>=MIN,<MAJOR+1
# and half_orm_dev's major version must be MAJOR. Both, and that the new
# version moves forward, are checked by scripts/check_half_orm_release.py
# before anything is written.
.PHONY: release
release: check-main-branch check-repo-clean
	@CURRENT=$$(cat half_orm_dev/version.txt | tr -d '[:space:]'); \
	echo "Current half-orm-dev version: $$CURRENT"; \
	CURRENT_MIN=$$(grep -oP '(?<=half-orm>=)[^,<"]+' pyproject.toml); \
	printf "Minimum half-orm version required [$$CURRENT_MIN]: "; \
	read MIN_HALF_ORM; \
	if [ -z "$$MIN_HALF_ORM" ]; then MIN_HALF_ORM="$$CURRENT_MIN"; fi; \
	if [ -z "$$MIN_HALF_ORM" ]; then echo "Aborted."; exit 1; fi; \
	printf "New half-orm-dev version: "; \
	read NEW_VERSION; \
	if [ -z "$$NEW_VERSION" ]; then echo "Aborted."; exit 1; fi; \
	echo "Checking half-orm PyPI release compatibility..."; \
	if ! python scripts/check_half_orm_release.py --min-half-orm "$$MIN_HALF_ORM" --dev-version "$$NEW_VERSION"; then \
		git checkout requirements.txt pyproject.toml codemeta.json; \
		echo "Nothing released."; \
		exit 1; \
	fi; \
	echo "$$NEW_VERSION" > half_orm_dev/version.txt; \
	git add half_orm_dev/version.txt requirements.txt pyproject.toml codemeta.json; \
	git commit -m "[release] $$NEW_VERSION"; \
	git tag "$$NEW_VERSION"; \
	echo "✓ Committed and tagged $$NEW_VERSION"

# Drop the PostgreSQL databases left behind by interrupted e2e runs
.PHONY: clean-e2e
clean-e2e:
	@python scripts/drop-stale-e2e-databases.py
