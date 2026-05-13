PI ?= pi@raspberrypi.local
DEST ?= /home/pi/dmx-ai

.PHONY: sim run deploy logs

sim:
	python3 app.py --sim

run:
	python3 app.py

deploy:
	rsync -avz --delete \
	  --exclude '__pycache__' --exclude '.git' --exclude '*.pyc' \
	  --exclude 'docs/' --exclude '.claude/' --exclude '.DS_Store' \
	  ./ $(PI):$(DEST)/
	ssh $(PI) 'sudo systemctl restart dmx-lights || true'

logs:
	ssh $(PI) 'journalctl -u dmx-lights -f'
