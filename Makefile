.PHONY: test serve-ui serve-api

test:
	python -m pytest -q service/tests

serve-ui:
	python -m http.server 8080 --directory studio-web

serve-api:
	uvicorn service.app.main:app --host 127.0.0.1 --port 8000
