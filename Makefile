.PHONY: test check

test:
	python3 -m unittest discover -s tests -p 'test_*.py'

check:
	$(MAKE) test
	bash scripts/check-harness.sh
	bash scripts/check-agent-quality.sh
