from twitch import TwitchHelix
import logging.handlers
import os
import configparser
import sys
import pickle
import time
import traceback
import requests
from datetime import datetime
from datetime import timedelta


LOG_LEVEL = logging.DEBUG

LOG_FOLDER_NAME = "logs"
if not os.path.exists(LOG_FOLDER_NAME):
	os.makedirs(LOG_FOLDER_NAME)
LOG_FILENAME = LOG_FOLDER_NAME+"/"+"bot.log"
LOG_FILE_BACKUPCOUNT = 5
LOG_FILE_MAXSIZE = 1024 * 1024 * 16

log = logging.getLogger("bot")
log.setLevel(LOG_LEVEL)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s: %(message)s')
log_stderrHandler = logging.StreamHandler()
log_stderrHandler.setFormatter(log_formatter)
log.addHandler(log_stderrHandler)
if LOG_FILENAME is not None:
	log_fileHandler = logging.handlers.RotatingFileHandler(
		LOG_FILENAME,
		maxBytes=LOG_FILE_MAXSIZE,
		backupCount=LOG_FILE_BACKUPCOUNT,
		encoding='utf-8')
	log_fileHandler.setFormatter(log_formatter)
	log.addHandler(log_fileHandler)

STATE_FILENAME = "state.pickle"
CONFIG_SECTION = "StreamSearcher"

config = configparser.ConfigParser()
if 'APPDATA' in os.environ:  # Windows
	os_config_path = os.environ['APPDATA']
elif 'XDG_CONFIG_HOME' in os.environ:  # Modern Linux
	os_config_path = os.environ['XDG_CONFIG_HOME']
elif 'HOME' in os.environ:  # Legacy Linux
	os_config_path = os.path.join(os.environ['HOME'], '.config')
else:
	log.error("Couldn't find config")
	sys.exit()
os_config_path = os.path.join(os_config_path, 'praw.ini')
config.read(os_config_path)

if CONFIG_SECTION not in config:
	log.error("Couldn't find config section")
	sys.exit()

GAME = config[CONFIG_SECTION]['game']
TWITCH_TOKEN = config[CONFIG_SECTION]['twitch_token']
WEBHOOK = config[CONFIG_SECTION]['webhook']

term_string = config[CONFIG_SECTION]['search_terms']
search_terms = []
for term in term_string.split(","):
	search_terms.append(term.lower())

if not os.path.exists(STATE_FILENAME):
	streams = {}
else:
	with open(STATE_FILENAME, 'rb') as handle:
		streams = pickle.load(handle)

helix = TwitchHelix(TWITCH_TOKEN)
game = helix.get_games(names=[GAME])[0]
log.info(f"Found game {game.id}")
while True:
	try:
		log.debug("Starting loop")
		count = 0
		for stream in helix.get_streams(page_size=100, game_ids=game.id):
			count += 1

			if stream.user_id in streams:
				continue

			found = False
			title = stream.title.lower()
			for term in search_terms:
				if term in title:
					found = True
					break

			if found:
				log.info(f"Found stream {stream.user_name} : {stream.title}")
				bldr = []
				bldr.append("<https://www.twitch.tv/")
				bldr.append(stream.user_name)
				bldr.append("> | ")
				bldr.append(stream.title)
				bldr.append(" | Viewers: ")
				bldr.append(str(stream.viewer_count))

				vods = helix.get_videos(user_id=stream.user_id, page_size=1)
				if len(vods):
					log.info(f"Found VOD : {vods[0].url}")
					bldr.append(" | VOD: <")
					bldr.append(vods[0].url)
					bldr.append(">")

				try:
					requests.post(WEBHOOK, data={"content": ''.join(bldr)})
				except Exception:
					log.warning(f"Unable to post discord announcement")
					log.warning(traceback.format_exc())

				streams[stream.user_id] = datetime.utcnow()

			if count % 100 == 0:
				log.info(f"Searched {count} streams {stream.viewer_count}")

		log.debug(f"Searched {count} streams")

		for user_id in list(streams.keys()):
			if streams[user_id] < datetime.utcnow() - timedelta(hours=12):
				log.info(f"Deleting user_id from streams {user_id}")
				del streams[user_id]

		with open(STATE_FILENAME, 'wb') as handle:
			pickle.dump(streams, handle)
	except Exception as err:
		log.warning("Hit an error in main loop")
		log.warning(traceback.format_exc())

	time.sleep(15 * 60)
