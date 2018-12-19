.PHONY: build push build-test test clean

IMAGE_NAME := quay.io/app-sre/qontract-validator
IMAGE_TAG := $(shell git rev-parse --short=7 HEAD)

IMAGE_TEST := validator-test

build: clean
	@docker build -t $(IMAGE_NAME):latest -f dockerfiles/Dockerfile .
	@docker tag $(IMAGE_NAME):latest $(IMAGE_NAME):$(IMAGE_TAG)

push:
	@docker push $(IMAGE_NAME):latest
	@docker push $(IMAGE_NAME):$(IMAGE_TAG)

build-test: clean
	@docker build -t $(IMAGE_TEST) -f dockerfiles/Dockerfile.test .

test: build-test
	@docker run --rm $(IMAGE_TEST)

clean:
	@rm -rf .tox .eggs *.egg-info buid .pytest_cache
	@find . -name "__pycache__" -type d -print0 | xargs -0 rm -rf
	@find . -name "*.pyc" -delete
