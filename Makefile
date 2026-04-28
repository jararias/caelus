
.PHONY: ipython3
ipython3:
	@uv run ipython --profile-dir=.ipython

.PHONY: init-venv
init-venv:
	@uv sync --reinstall
	@attr -s com.dropbox.ignored -V 1 .venv  # instruct dropbox to ignore the .venv folder

.PHONY: clean
clean:
	@rm -rf build
	@rm -rf dist
	@rm -rf *.egg-info
	@rm -rf .pytest_cache
	@rm -f MANIFEST
	@find . -name "__pycache__" -print0 | xargs -0 -I {} /bin/rm -rf "{}"
