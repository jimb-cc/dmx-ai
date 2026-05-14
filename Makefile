PI ?= pi@raspberrypi.local
DEST ?= /home/pi/dmx-ai

.PHONY: show sim design design-front deploy logs

# --- Show app (Pi / gig-time) ----------------------------------------------

show:
	cd show && python3 app.py

sim:
	cd show && python3 app.py --sim

# --- Design app (laptop / pre-show) ----------------------------------------

design:
	cd design && python3 server.py

design-front:
	cd design/frontend && npm run dev

# --- Deploy to the Pi -------------------------------------------------------
# Ships only what the Show app needs: show/, shared/, requirements.txt.
# design/ and node_modules/ never touch the Pi.

deploy:
	rsync -avz --delete \
	  --exclude '__pycache__' --exclude '.git' --exclude '*.pyc' \
	  --exclude 'docs/' --exclude '.claude/' --exclude '.DS_Store' \
	  --exclude 'design/' --exclude 'data/' --exclude 'node_modules/' \
	  ./ $(PI):$(DEST)/
	ssh $(PI) 'sudo systemctl restart dmx-lights || true'

logs:
	ssh $(PI) 'journalctl -u dmx-lights -f'
