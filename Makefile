clean_build:
	rm -rf dist

build: clean_build
	python -m build

publish: build
	twine upload -r half-orm-dev dist/*
