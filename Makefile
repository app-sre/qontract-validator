.PHONY: build push build-test test clean

IMAGE_NAME := quay.io/app-sre/qontract-validator
IMAGE_TAG := $(shell git rev-parse --short=7 HEAD)

IMAGE_TEST := validator-test

ifneq (,$(wildcard $(CURDIR)/.docker))
	DOCKER_CONF := $(CURDIR)/.docker
else
	DOCKER_CONF := $(HOME)/.docker
endif

build: clean
	@docker build --target prod -t $(IMAGE_NAME):latest -f Dockerfile .
	@docker tag $(IMAGE_NAME):latest $(IMAGE_NAME):$(IMAGE_TAG)

push:
	@docker --config=$(DOCKER_CONF) push $(IMAGE_NAME):latest
	@docker --config=$(DOCKER_CONF) push $(IMAGE_NAME):$(IMAGE_TAG)

build-test: clean
	@docker build --target test -t $(IMAGE_TEST) -f Dockerfile .

test: build-test
	@docker run --rm $(IMAGE_TEST)

clean:
	@rm -rf .tox .eggs *.egg-info buid .pytest_cache
	@find . -name "__pycache__" -type d -print0 | xargs -0 rm -rf
	@find . -name "*.pyc" -delete
