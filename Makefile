.PHONY: data preprocess notebooks clean install

install:
	uv sync

data:
	uv run python src/data/download.py

preprocess:
	uv run python src/data/preprocess.py

notebooks:
	uv run jupyter nbconvert --to notebook --execute --inplace notebooks/*.ipynb

clean:
	rm -rf data/raw/* data/processed/* outputs/figures/* outputs/models/*
	find . -name "*.pyc" -delete
	find . -name "__pycache__" -type d -exec rm -rf {} +
