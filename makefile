ifneq ("$(wildcard .env)","")
  include .env
  export $(shell sed 's/=.*//' .env)
endif

.PHONY: install
install:
	@rm -f poetry.lock
	@poetry install --with dev
	@poetry export --without-hashes -f requirements.txt -o requirements.txt

.PHONY: pypi
pypi:
	@echo "reseting to latest remote..."
	@git pull && git reset --hard origin/main
	@echo "re-installing package..."
	@make install
	@echo "starting PyPI bump process..."
	# check if the new VERSION is provided
	@if [ -z "$$VERSION" ]; then \
	    echo "no VERSION provided, auto-incrementing patch version..."; \
	    OLD_VERSION=$$(poetry version | awk '{print $$2}'); \
	    MAJOR=$$(echo $$OLD_VERSION | cut -d. -f1); \
	    MINOR=$$(echo $$OLD_VERSION | cut -d. -f2); \
	    PATCH=$$(echo $$OLD_VERSION | cut -d. -f3); \
	    VERSION=$$MAJOR.$$MINOR.$$((PATCH + 1)); \
	    echo "auto-incremented version to $$VERSION"; \
	    poetry version $$VERSION; \
	else \
	    echo "updating version to $$VERSION..."; \
	    poetry version $$VERSION; \
	fi
	# now, publish to PyPi
	@echo "publishing package to PyPI..."
	@if poetry publish --build; then \
		git add pyproject.toml poetry.lock requirements.txt; \
		git commit -m "bump pypi to version $$VERSION"; \
		git push; \
	    echo "package published successfully"; \
	else \
	    echo "failed to publish package"; \
	    exit 1; \
	fi
