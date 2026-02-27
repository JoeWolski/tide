.PHONY: readme-transcript readme-transcript-fast

readme-transcript:
	./scripts/readme/regenerate_transcript.py --readme README.md

readme-transcript-fast:
	./scripts/readme/regenerate_transcript.py --readme README.md --reuse-container --keep-container
