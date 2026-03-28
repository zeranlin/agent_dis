.PHONY: check

check:
	bash scripts/check-harness.sh
	bash scripts/check-agent-quality.sh
