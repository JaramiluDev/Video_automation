# ==============================================================================
# Makefile - Automatización de Comandos Docker & Calidad de Código
# ==============================================================================
# Variables configurables
COMPOSE ?= docker compose
SERVICE = video-app

.PHONY: help up down test lint format build logs

help: ## Muestra esta ayuda con todos los comandos disponibles
	@echo "Uso: make <comando>"
	@echo ""
	@echo "Comandos disponibles:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: ## Levanta los contenedores del proyecto en segundo plano
	$(COMPOSE) up -d

down: ## Detiene y remueve los contenedores y redes asociadas
	$(COMPOSE) down

test: ## Ejecuta la suite de pruebas unitarias con pytest dentro del contenedor
	$(COMPOSE) run --rm $(SERVICE) pytest

lint: ## Analiza el código en busca de errores y estilo con ruff check
	$(COMPOSE) run --rm $(SERVICE) ruff check .

format: ## Aplica formato automático de código con ruff format
	$(COMPOSE) run --rm $(SERVICE) ruff format .

build: ## Reconstruye las imágenes de Docker Compose sin caché
	$(COMPOSE) build

logs: ## Muestra los logs en tiempo real del contenedor principal
	$(COMPOSE) logs -f $(SERVICE)
